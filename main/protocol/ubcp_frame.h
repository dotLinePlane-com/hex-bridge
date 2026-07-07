/**
 * @file ubcp_frame.h
 * @brief UBCP v2.0 帧结构体定义与 API 声明
 *
 * 提供帧的内存表示、帧构建、帧解析（流式状态机）等接口。
 */

#pragma once

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"
#include "ubcp_def.h"

/* ========================================================================
 * 帧结构体（解析后的逻辑帧）
 * ======================================================================== */

/**
 * @brief UBCP 帧的内存表示
 *
 * 这是解析后/待构建的逻辑帧，不包含 SOF/EOF/转义/CRC。
 * payload 指向的内存由调用者管理。
 */
typedef struct {
    /* --- 固定头部 (10 字节) --- */
    uint8_t     version;        /**< 协议版本 (UBCP_VERSION) */
    uint8_t     flags;          /**< 标志位 (DIR|ACK|TS|EVT|FRAG|保留) */
    uint16_t    seq_num;        /**< 序列号 */
    uint8_t     cmd_code;       /**< 命令码 */
    uint8_t     channel_id;     /**< 通道号 */
    uint16_t    payload_len;    /**< 载荷长度 */

    /* --- 可选时间戳 --- */
    bool        has_timestamp;  /**< 是否包含时间戳 */
    uint32_t    timestamp;      /**< 时间戳（微秒） */

    /* --- 载荷 --- */
    uint8_t    *payload;        /**< 载荷数据指针（不拥有内存） */
} ubcp_frame_t;

/* ========================================================================
 * 帧解析器（流式状态机）
 * ======================================================================== */

/**
 * @brief 帧解析器状态
 */
typedef enum {
    UBCP_PARSE_WAIT_SOF_0 = 0,     /**< 等待 SOF 第一字节 (0xAA) */
    UBCP_PARSE_WAIT_SOF_1,          /**< 等待 SOF 第二字节 (0x55) */
    UBCP_PARSE_RECEIVING,           /**< 正在接收数据（反转义中） */
} ubcp_parse_state_t;

/**
 * @brief 帧解析器上下文
 *
 * 支持流式逐字节输入，在线反转义 + CRC 计算。
 * 使用者需为 buf 分配内存（建议 HEX_UBCP_FRAME_BUF_SIZE）。
 */
typedef struct {
    ubcp_parse_state_t  state;      /**< 当前解析状态 */
    bool                is_escaped; /**< 是否正在处理转义序列 */
    uint16_t            crc;        /**< 在线计算的 CRC16 */
    uint8_t            *buf;        /**< 逻辑帧缓冲区（反转义后的数据） */
    size_t              buf_size;   /**< 缓冲区最大容量 */
    size_t              buf_pos;    /**< 当前写入位置 */
} ubcp_parser_t;

/**
 * @brief 帧解析结果
 */
typedef enum {
    UBCP_PARSE_NEED_MORE = 0,   /**< 需要更多数据 */
    UBCP_PARSE_FRAME_OK,        /**< 解析出一个完整帧 */
    UBCP_PARSE_ERR_CRC,         /**< CRC 校验失败 */
    UBCP_PARSE_ERR_OVERFLOW,    /**< 缓冲区溢出 */
    UBCP_PARSE_ERR_ESCAPE,      /**< 转义序列错误 */
    UBCP_PARSE_ERR_TOO_SHORT,   /**< 数据太短，不足以构成帧 */
} ubcp_parse_result_t;

/* ========================================================================
 * API 声明
 * ======================================================================== */

/**
 * @brief 初始化帧解析器
 * @param parser    解析器上下文
 * @param buf       逻辑帧缓冲区
 * @param buf_size  缓冲区大小（字节）
 */
void ubcp_parser_init(ubcp_parser_t *parser, uint8_t *buf, size_t buf_size);

/**
 * @brief 重置解析器状态（准备接收下一帧）
 * @param parser    解析器上下文
 */
void ubcp_parser_reset(ubcp_parser_t *parser);

/**
 * @brief 向解析器输入一个字节
 *
 * 流式调用：每收到一个字节调用一次。当返回 UBCP_PARSE_FRAME_OK 时，
 * 可调用 ubcp_parser_get_frame() 获取解析结果。
 *
 * @param parser    解析器上下文
 * @param byte      输入字节
 * @return 解析结果
 */
ubcp_parse_result_t ubcp_parser_feed(ubcp_parser_t *parser, uint8_t byte);

/**
 * @brief 从解析器缓冲区中提取帧结构体
 *
 * 仅在 ubcp_parser_feed() 返回 UBCP_PARSE_FRAME_OK 后调用有效。
 * 输出帧的 payload 指针指向解析器内部缓冲区，调用者不可释放，
 * 且在下次 ubcp_parser_reset() 后失效。
 *
 * @param parser    解析器上下文
 * @param frame     输出帧结构体
 * @return ESP_OK 或错误码
 */
esp_err_t ubcp_parser_get_frame(const ubcp_parser_t *parser, ubcp_frame_t *frame);

/**
 * @brief 构建一个完整的线路帧（包含 SOF、转义、CRC、EOF）
 *
 * 将逻辑帧编码为可直接写入 UART 的字节流。
 *
 * @param frame     输入帧结构体
 * @param out_buf   输出缓冲区
 * @param out_size  输出缓冲区大小
 * @param out_len   实际写入的字节数
 * @return ESP_OK 或 ESP_ERR_INVALID_SIZE（缓冲区不足）
 */
esp_err_t ubcp_frame_build(const ubcp_frame_t *frame,
                           uint8_t *out_buf, size_t out_size, size_t *out_len);

/**
 * @brief 快速构建一个响应帧
 *
 * 基于请求帧创建响应帧：设置 DIR=1，复制 SeqNum/CmdCode/ChannelID。
 *
 * @param req       请求帧
 * @param resp      输出响应帧（调用者需设置 payload/payload_len）
 */
void ubcp_frame_make_response(const ubcp_frame_t *req, ubcp_frame_t *resp);

/**
 * @brief 快速构建一个事件帧
 *
 * 创建设备主动上报的事件帧：DIR=1, EVT=1, SeqNum 由设备分配。
 *
 * @param evt       输出事件帧
 * @param cmd_code  命令码
 * @param channel   通道号
 * @param seq       设备事件序列号
 */
void ubcp_frame_make_event(ubcp_frame_t *evt, uint8_t cmd_code,
                           uint8_t channel, uint16_t seq);
