/**
 * @file ubcp_frame.c
 * @brief UBCP v2.0 帧解析与构建实现
 *
 * 实现流式帧解析器（在线反转义 + CRC）和帧构建器（转义 + CRC + SOF/EOF）。
 */

#include <string.h>
#include "ubcp_frame.h"
#include "ubcp_crc16.h"

/* ========================================================================
 * 内部辅助函数
 * ======================================================================== */

/**
 * @brief 向输出缓冲区写入一个字节（带转义）
 * @return 写入的字节数（1 或 2）
 */
static size_t write_escaped(uint8_t *buf, size_t pos, size_t max, uint8_t byte)
{
    if (byte == UBCP_EOF) {
        if (pos + 2 > max) return 0;
        buf[pos]     = UBCP_ESC;
        buf[pos + 1] = UBCP_ESC_EOF;
        return 2;
    } else if (byte == UBCP_ESC) {
        if (pos + 2 > max) return 0;
        buf[pos]     = UBCP_ESC;
        buf[pos + 1] = UBCP_ESC_ESC;
        return 2;
    } else {
        if (pos + 1 > max) return 0;
        buf[pos] = byte;
        return 1;
    }
}

/* ========================================================================
 * 帧解析器实现
 * ======================================================================== */

void ubcp_parser_init(ubcp_parser_t *parser, uint8_t *buf, size_t buf_size)
{
    parser->buf      = buf;
    parser->buf_size = buf_size;
    ubcp_parser_reset(parser);
}

void ubcp_parser_reset(ubcp_parser_t *parser)
{
    parser->state      = UBCP_PARSE_WAIT_SOF_0;
    parser->is_escaped = false;
    parser->crc        = 0xFFFF;
    parser->buf_pos    = 0;
}

ubcp_parse_result_t ubcp_parser_feed(ubcp_parser_t *parser, uint8_t byte)
{
    switch (parser->state) {

    case UBCP_PARSE_WAIT_SOF_0:
        if (byte == UBCP_SOF_0) {
            parser->state = UBCP_PARSE_WAIT_SOF_1;
        }
        return UBCP_PARSE_NEED_MORE;

    case UBCP_PARSE_WAIT_SOF_1:
        if (byte == UBCP_SOF_1) {
            /* SOF 确认，进入接收状态 */
            parser->state      = UBCP_PARSE_RECEIVING;
            parser->is_escaped = false;
            parser->crc        = 0xFFFF;
            parser->buf_pos    = 0;
        } else if (byte == UBCP_SOF_0) {
            /* 连续 0xAA，保持等待 0x55 */
        } else {
            parser->state = UBCP_PARSE_WAIT_SOF_0;
        }
        return UBCP_PARSE_NEED_MORE;

    case UBCP_PARSE_RECEIVING:
        /* 检测帧尾 EOF（未转义的 0x7E） */
        if (!parser->is_escaped && byte == UBCP_EOF) {
            /*
             * 收到 EOF，帧结束。
             * 缓冲区中包含：[Header 8B] [Timestamp 0/4B] [Payload NB] [CRC16 2B]
             * 注意：Header 实际是 Version 到 PayloadLen (8字节)，不含 SOF(2B)。
             * 所以缓冲区从 Version 开始，共 8 字节头部。
             */
            if (parser->buf_pos < 8 + 2) { /* 最少 8 字节头 + 2 字节 CRC */
                ubcp_parser_reset(parser);
                return UBCP_PARSE_ERR_TOO_SHORT;
            }

            /*
             * CRC 校验：
             * 在线 CRC 已经把所有数据（包括尾部的 CRC16 本身）都算进去了。
             * 对于 CRC-16/CCITT-FALSE，如果数据+CRC 一起算，结果应为 0。
             */
            if (parser->crc != 0x0000) {
                ubcp_parser_reset(parser);
                return UBCP_PARSE_ERR_CRC;
            }

            return UBCP_PARSE_FRAME_OK;
        }

        /* 处理转义 */
        if (parser->is_escaped) {
            parser->is_escaped = false;
            if (byte == UBCP_ESC_EOF) {
                byte = UBCP_EOF;
            } else if (byte == UBCP_ESC_ESC) {
                byte = UBCP_ESC;
            } else {
                /* 非法转义序列 */
                ubcp_parser_reset(parser);
                return UBCP_PARSE_ERR_ESCAPE;
            }
        } else if (byte == UBCP_ESC) {
            parser->is_escaped = true;
            return UBCP_PARSE_NEED_MORE;
        }

        /* 注意：在 RECEIVING 状态下，即使遇到 0xAA 0x55 也当作普通数据 */

        /* 写入逻辑缓冲区 */
        if (parser->buf_pos >= parser->buf_size) {
            ubcp_parser_reset(parser);
            return UBCP_PARSE_ERR_OVERFLOW;
        }
        parser->buf[parser->buf_pos++] = byte;

        /* 在线 CRC 更新 */
        parser->crc = ubcp_crc16_update(parser->crc, byte);

        return UBCP_PARSE_NEED_MORE;
    }

    return UBCP_PARSE_NEED_MORE;
}

esp_err_t ubcp_parser_get_frame(const ubcp_parser_t *parser, ubcp_frame_t *frame)
{
    const uint8_t *buf = parser->buf;
    size_t len = parser->buf_pos;

    /* 缓冲区布局 (不含 SOF/EOF，已反转义)：
     * [0]    Version
     * [1]    Flags
     * [2-3]  SeqNum (大端)
     * [4]    CmdCode
     * [5]    ChannelID
     * [6-7]  PayloadLen (大端)
     * --- 固定头部结束 (8 字节) ---
     * [8-11] Timestamp (可选, 4 字节, 大端)
     * [...]  Payload
     * [N-2, N-1] CRC16 (大端，已校验，不需要再处理)
     */

    if (len < 8 + 2) { /* 至少 8 字节头 + 2 字节 CRC */
        return ESP_ERR_INVALID_SIZE;
    }

    frame->version     = buf[0];
    frame->flags       = buf[1];
    frame->seq_num     = ((uint16_t)buf[2] << 8) | buf[3];
    frame->cmd_code    = buf[4];
    frame->channel_id  = buf[5];
    frame->payload_len = ((uint16_t)buf[6] << 8) | buf[7];

    /* 时间戳 */
    frame->has_timestamp = (frame->flags & UBCP_FLAG_TS) != 0;
    size_t header_total = 8; /* 不含 SOF */

    if (frame->has_timestamp) {
        if (len < 8 + 4 + 2) {
            return ESP_ERR_INVALID_SIZE;
        }
        frame->timestamp = ((uint32_t)buf[8] << 24) |
                           ((uint32_t)buf[9] << 16) |
                           ((uint32_t)buf[10] << 8) |
                           (uint32_t)buf[11];
        header_total = 12;
    } else {
        frame->timestamp = 0;
    }

    /* 载荷 */
    size_t payload_start = header_total;
    size_t crc_start     = len - 2; /* 最后 2 字节是 CRC */
    size_t actual_payload = crc_start - payload_start;

    if (actual_payload != frame->payload_len) {
        /* 载荷长度与声明不匹配 */
        return ESP_ERR_INVALID_SIZE;
    }

    if (frame->payload_len > 0) {
        /* 指向解析器内部缓冲区，不拥有内存 */
        frame->payload = (uint8_t *)&buf[payload_start];
    } else {
        frame->payload = NULL;
    }

    return ESP_OK;
}

/* ========================================================================
 * 帧构建器实现
 * ======================================================================== */

esp_err_t ubcp_frame_build(const ubcp_frame_t *frame,
                           uint8_t *out_buf, size_t out_size, size_t *out_len)
{
    /*
     * 构建线路帧：SOF + 转义(Header + [Timestamp] + Payload + CRC16) + EOF
     * 最坏情况：每个字节都需转义（x2），但实际不太可能。
     * 保守估算：out_size >= SOF(2) + (头部+载荷+CRC)*2 + EOF(1)
     */

    /* 1. 构造原始数据（未转义） */
    uint8_t raw_header[12]; /* 最多 8(头) + 4(时间戳) = 12 字节 */
    size_t raw_header_len = 8;

    raw_header[0] = frame->version;
    raw_header[1] = frame->flags;
    raw_header[2] = (uint8_t)(frame->seq_num >> 8);
    raw_header[3] = (uint8_t)(frame->seq_num & 0xFF);
    raw_header[4] = frame->cmd_code;
    raw_header[5] = frame->channel_id;
    raw_header[6] = (uint8_t)(frame->payload_len >> 8);
    raw_header[7] = (uint8_t)(frame->payload_len & 0xFF);

    if (frame->has_timestamp) {
        raw_header[8]  = (uint8_t)(frame->timestamp >> 24);
        raw_header[9]  = (uint8_t)(frame->timestamp >> 16);
        raw_header[10] = (uint8_t)(frame->timestamp >> 8);
        raw_header[11] = (uint8_t)(frame->timestamp & 0xFF);
        raw_header_len = 12;
    }

    /* 2. 计算 CRC16（范围：Header + Timestamp + Payload） */
    uint16_t crc = ubcp_crc16_calc(raw_header, raw_header_len);
    if (frame->payload && frame->payload_len > 0) {
        for (uint16_t i = 0; i < frame->payload_len; i++) {
            crc = ubcp_crc16_update(crc, frame->payload[i]);
        }
    }

    /* 3. 写入 SOF（不转义） */
    size_t pos = 0;
    if (pos + 2 > out_size) return ESP_ERR_INVALID_SIZE;
    out_buf[pos++] = UBCP_SOF_0;
    out_buf[pos++] = UBCP_SOF_1;

    /* 4. 写入头部（转义） */
    for (size_t i = 0; i < raw_header_len; i++) {
        size_t written = write_escaped(out_buf, pos, out_size, raw_header[i]);
        if (written == 0) return ESP_ERR_INVALID_SIZE;
        pos += written;
    }

    /* 5. 写入载荷（转义） */
    if (frame->payload && frame->payload_len > 0) {
        for (uint16_t i = 0; i < frame->payload_len; i++) {
            size_t written = write_escaped(out_buf, pos, out_size, frame->payload[i]);
            if (written == 0) return ESP_ERR_INVALID_SIZE;
            pos += written;
        }
    }

    /* 6. 写入 CRC16（转义，大端） */
    uint8_t crc_hi = (uint8_t)(crc >> 8);
    uint8_t crc_lo = (uint8_t)(crc & 0xFF);
    size_t w;
    w = write_escaped(out_buf, pos, out_size, crc_hi);
    if (w == 0) return ESP_ERR_INVALID_SIZE;
    pos += w;
    w = write_escaped(out_buf, pos, out_size, crc_lo);
    if (w == 0) return ESP_ERR_INVALID_SIZE;
    pos += w;

    /* 7. 写入 EOF（不转义） */
    if (pos + 1 > out_size) return ESP_ERR_INVALID_SIZE;
    out_buf[pos++] = UBCP_EOF;

    *out_len = pos;
    return ESP_OK;
}

void ubcp_frame_make_response(const ubcp_frame_t *req, ubcp_frame_t *resp)
{
    memset(resp, 0, sizeof(ubcp_frame_t));
    resp->version       = UBCP_VERSION;
    resp->flags         = UBCP_FLAG_DIR; /* DIR=1 (设备→主机), 其余为 0 */
    resp->seq_num       = req->seq_num;  /* 回填请求的序列号 */
    resp->cmd_code      = req->cmd_code;
    resp->channel_id    = req->channel_id;
    resp->has_timestamp = false;
    resp->payload       = NULL;
    resp->payload_len   = 0;
}

void ubcp_frame_make_event(ubcp_frame_t *evt, uint8_t cmd_code,
                           uint8_t channel, uint16_t seq)
{
    memset(evt, 0, sizeof(ubcp_frame_t));
    evt->version       = UBCP_VERSION;
    evt->flags         = UBCP_FLAG_DIR | UBCP_FLAG_EVT; /* DIR=1, EVT=1 */
    evt->seq_num       = seq;
    evt->cmd_code      = cmd_code;
    evt->channel_id    = channel;
    evt->has_timestamp = false;
    evt->payload       = NULL;
    evt->payload_len   = 0;
}
