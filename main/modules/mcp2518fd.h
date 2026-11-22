/**
 * @file mcp2518fd.h
 * @brief MCP2518FD CAN FD 控制器 SPI 驱动
 *
 * 基于 Microchip 官方驱动 (drv_canfdspi) 移植到 ESP-IDF SPI Master。
 * 提供寄存器访问、收发、过滤器、位时序、中断等底层操作。
 *
 * 硬件连接 (hex_config.h)：
 *   SCK=GPIO14, MOSI=GPIO13, MISO=GPIO36, CS=GPIO15, INT=GPIO39
 *   SPI Mode 0, 10 MHz, 系统时钟 40 MHz (20MHz 晶振 + PLL)
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MCP2518FD_INS_RESET         0x00
#define MCP2518FD_INS_READ          0x03
#define MCP2518FD_INS_READ_CRC      0x0B
#define MCP2518FD_INS_WRITE         0x02
#define MCP2518FD_INS_WRITE_CRC     0x0A
#define MCP2518FD_INS_WRITE_SAFE    0x0C

/* ========================================================================
 * 寄存器地址
 * ======================================================================== */

#define MCP2518FD_REG_CiCON         0x000
#define MCP2518FD_REG_CiNBTCFG      0x004
#define MCP2518FD_REG_CiDBTCFG      0x008
#define MCP2518FD_REG_CiTDC         0x00C
#define MCP2518FD_REG_CiTBC         0x010
#define MCP2518FD_REG_CiTSCON       0x014
#define MCP2518FD_REG_CiVEC         0x018
#define MCP2518FD_REG_CiINT         0x01C
#define MCP2518FD_REG_CiRXIF        0x020
#define MCP2518FD_REG_CiTXIF        0x024
#define MCP2518FD_REG_CiRXOVIF      0x028
#define MCP2518FD_REG_CiTXATIF      0x02C
#define MCP2518FD_REG_CiTXREQ       0x030
#define MCP2518FD_REG_CiTREC        0x034
#define MCP2518FD_REG_CiBDIAG0      0x038
#define MCP2518FD_REG_CiBDIAG1      0x03C
#define MCP2518FD_REG_CiTEFCON      0x040
#define MCP2518FD_REG_CiTEFSTA      0x044
#define MCP2518FD_REG_CiTEFUA       0x048
#define MCP2518FD_REG_CiTXQCON      0x050
#define MCP2518FD_REG_CiTXQSTA      0x054
#define MCP2518FD_REG_CiTXQUA       0x058

/* FIFO 寄存器偏移 (每个 FIFO 3 个字 = 12 字节) */
#define MCP2518FD_FIFO_OFFSET       12

/* 过滤器寄存器 */
#define MCP2518FD_REG_CiFLTCON      0x1D0   /* 32 字节，每过滤器 1 字节 */
#define MCP2518FD_REG_CiFLTOBJ      0x1F0   /* FLTOBJ0 */
#define MCP2518FD_REG_CiMASK        0x1F4   /* MASK0 */
#define MCP2518FD_FILTER_OFFSET     8       /* 每过滤器 8 字节 */

/* MCP2518FD 特定寄存器 */
#define MCP2518FD_REG_OSC           0xE00
#define MCP2518FD_REG_IOCON         0xE04
#define MCP2518FD_REG_DEVID         0xE14

/* RAM 区域 */
#define MCP2518FD_RAM_START         0x400
#define MCP2518FD_RAM_SIZE          2048

/* ========================================================================
 * 通道枚举
 * ======================================================================== */

#define MCP2518FD_CH_TXQ            0   /* 发送队列 */
#define MCP2518FD_CH_FIFO1          1   /* 接收 FIFO1 */
#define MCP2518FD_CH_FIFO2          2   /* 接收 FIFO2 */

#define MCP2518FD_FILTER_COUNT      32

/* ========================================================================
 * 工作模式 (CiCON.REQOP)
 * ======================================================================== */

#define MCP2518FD_MODE_NORMAL       0x00
#define MCP2518FD_MODE_SLEEP        0x01
#define MCP2518FD_MODE_INTERNAL_LOOP 0x02
#define MCP2518FD_MODE_LISTEN_ONLY  0x03
#define MCP2518FD_MODE_CONFIG       0x04
#define MCP2518FD_MODE_EXTERNAL_LOOP 0x05
#define MCP2518FD_MODE_CLASSIC      0x06
#define MCP2518FD_MODE_RESTRICTED   0x07

/* ========================================================================
 * CiINT 中断标志 (低 16 位) / 使能 (高 16 位)
 * ======================================================================== */

#define MCP2518FD_INT_TXIF          (1 << 0)
#define MCP2518FD_INT_RXIF          (1 << 1)
#define MCP2518FD_INT_TBCIF         (1 << 2)
#define MCP2518FD_INT_MODIF         (1 << 3)
#define MCP2518FD_INT_TEFIF         (1 << 4)
#define MCP2518FD_INT_ECCIF         (1 << 8)
#define MCP2518FD_INT_SPICRCIF      (1 << 9)
#define MCP2518FD_INT_TXATIF        (1 << 10)
#define MCP2518FD_INT_RXOVIF        (1 << 11)
#define MCP2518FD_INT_SERRIF        (1 << 12)
#define MCP2518FD_INT_CERRIF        (1 << 13)
#define MCP2518FD_INT_WAKIF         (1 << 14)
#define MCP2518FD_INT_IVMIF         (1 << 15)

/* ========================================================================
 * CiTREC 错误状态标志 (byte 2)
 * ======================================================================== */

#define MCP2518FD_ERR_RXWARN        (1 << 0)   /* EWARN */
#define MCP2518FD_ERR_RXWARN2       (1 << 1)   /* RXWARN */
#define MCP2518FD_ERR_TXWARN        (1 << 2)   /* TXWARN */
#define MCP2518FD_ERR_RXPASSIVE     (1 << 3)   /* RXBP */
#define MCP2518FD_ERR_TXPASSIVE     (1 << 4)   /* TXBP */
#define MCP2518FD_ERR_TXBO          (1 << 5)   /* TXBO */

/* ========================================================================
 * CiBDIAG1 错误标志
 * ======================================================================== */

#define MCP2518FD_BD_NBIT0          (1 << 16)
#define MCP2518FD_BD_NBIT1          (1 << 17)
#define MCP2518FD_BD_NACK           (1 << 18)
#define MCP2518FD_BD_NFORM          (1 << 19)
#define MCP2518FD_BD_NSTUFF         (1 << 20)
#define MCP2518FD_BD_NCRC           (1 << 21)
#define MCP2518FD_BD_TXBO           (1 << 23)
#define MCP2518FD_BD_DBIT0          (1 << 24)
#define MCP2518FD_BD_DBIT1          (1 << 25)
#define MCP2518FD_BD_DACK           (1 << 26)
#define MCP2518FD_BD_DFORM          (1 << 27)
#define MCP2518FD_BD_DSTUFF         (1 << 28)
#define MCP2518FD_BD_DCRC           (1 << 29)

/* ========================================================================
 * 报文对象
 * ======================================================================== */

#define MCP2518FD_MAX_DATA_BYTES    64
#define MCP2518FD_OBJ_HEADER        8

/** 发送报文对象 (T0 字 + T1 字 + 数据) */
typedef struct {
    uint32_t id;        /* T0: SID<10:0> | EID<17:0><<11 | SID11<<29 */
    uint32_t ctrl;      /* T1: DLC<3:0> IDE RTR BRS FDF ESI SEQ<22:0><<9 */
    uint8_t  data[MCP2518FD_MAX_DATA_BYTES];
} mcp2518fd_tx_obj_t;

/** 接收报文对象 (R0 字 + R1 字 + 数据) */
typedef struct {
    uint32_t id;        /* R0 */
    uint32_t ctrl;      /* R1: DLC<3:0> IDE RTR BRS FDF ESI FILTHIT<4:0><<11 */
    uint8_t  data[MCP2518FD_MAX_DATA_BYTES];
} mcp2518fd_rx_obj_t;

/* ========================================================================
 * 位时序表
 * ======================================================================== */

/** 仲裁段 (Nominal) 位时序参数 */
typedef struct {
    uint8_t brp;
    uint8_t tseg1;
    uint8_t tseg2;
    uint8_t sjw;
} mcp2518fd_nom_timing_t;

/** FD 数据段位时序参数 */
typedef struct {
    uint8_t brp;
    uint8_t tseg1;
    uint8_t tseg2;
    uint8_t sjw;
    uint8_t tdc_offset;     /* TDCO 偏移 (TQ) */
    bool    tdc_enable;     /* 是否启用 TDC */
} mcp2518fd_data_timing_t;

/* ========================================================================
 * SPI 驱动 API
 * ======================================================================== */

/**
 * @brief 初始化 SPI 总线并添加 MCP2518FD 设备
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_init(void);
/** Call after CAN worker tasks have stopped. Releases only this device reference. */
esp_err_t mcp2518fd_deinit(void);
/** Trial boot only: verifies chip communication without a CAN peer. Resets chip. */
esp_err_t mcp2518fd_probe(void);

/**
 * @brief 获取器件 ID (DEVID 寄存器)
 * @param dev_id 输出器件 ID (低 4 位 REV, 高 4 位 DEV)
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_get_dev_id(uint8_t *dev_id);

/* --- 寄存器访问 --- */

esp_err_t mcp2518fd_read_byte(uint16_t addr, uint8_t *rxd);
esp_err_t mcp2518fd_write_byte(uint16_t addr, uint8_t txd);
esp_err_t mcp2518fd_read_word(uint16_t addr, uint32_t *rxd);
esp_err_t mcp2518fd_write_word(uint16_t addr, uint32_t txd);
esp_err_t mcp2518fd_read_bytes(uint16_t addr, uint8_t *rxd, uint16_t n);
esp_err_t mcp2518fd_write_bytes(uint16_t addr, const uint8_t *txd, uint16_t n);

/* --- 复位与模式 --- */

esp_err_t mcp2518fd_reset(void);
esp_err_t mcp2518fd_opmode_select(uint8_t mode);
uint8_t   mcp2518fd_opmode_get(void);

/* --- 振荡器 --- */

/**
 * @brief 使能振荡器并等待 OSCRDY 就绪
 * @return ESP_OK 或 ESP_ERR_TIMEOUT
 */
esp_err_t mcp2518fd_osc_enable(void);

/* --- 配置 --- */

/**
 * @brief 使能收发器待机 (XSTBY) 引脚控制
 *
 * 启用 IOCON.XSTBYEN，将 INT0/GPIO0/XSTBY (pin 9) 用作 ATA6563 等
 * CAN 收发器的 STBY 控制。GPIO0 配置为输出并拉低，使收发器进入
 * 正常工作模式（非 standby）。
 *
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_xstby_enable(void);

/**
 * @brief 配置仲裁段与 FD 数据段位时序
 * @param nom   仲裁段时序 (NULL 表示不修改)
 * @param data  FD 数据段时序 (NULL 表示不修改/经典 CAN)
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_bit_time_config(const mcp2518fd_nom_timing_t *nom,
                                    const mcp2518fd_data_timing_t *data);

/**
 * @brief 配置发送队列 (TXQ)
 * @param fifo_size 帧数 (1-32)
 * @param payload_size 载荷大小: 8/12/16/20/24/32/48/64
 * @param priority  优先级 0-31
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_txq_config(uint8_t fifo_size, uint8_t payload_size,
                               uint8_t priority);

/**
 * @brief 配置接收 FIFO
 * @param channel      MCP2518FD_CH_FIFO1 或 FIFO2
 * @param fifo_size    帧数 (1-32)
 * @param payload_size 载荷大小
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_rx_fifo_config(uint8_t channel, uint8_t fifo_size,
                                   uint8_t payload_size);

/* --- 过滤器 --- */

/**
 * @brief 配置过滤器对象 (FLTOBJ)
 * @param filter 过滤器编号 0-31
 * @param sid    11 位标准 ID
 * @param eid    18 位扩展 ID (高 18 位)
 * @param exide  1=扩展帧过滤器
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_filter_object_config(uint8_t filter, uint16_t sid,
                                         uint32_t eid, bool exide);

/**
 * @brief 配置过滤器掩码 (MASK)
 * @param filter 过滤器编号 0-31
 * @param msid   11 位标准 ID 掩码
 * @param meid   18 位扩展 ID 掩码
 * @param mide   1=IDE 位参与比较 (0=同时匹配标准/扩展帧)
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_filter_mask_config(uint8_t filter, uint16_t msid,
                                       uint32_t meid, bool mide);

/**
 * @brief 将过滤器链接到 FIFO 并启用/禁用
 * @param filter  过滤器编号 0-31
 * @param channel 目标 FIFO (1 或 2)
 * @param enable  1=启用, 0=禁用
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_filter_to_fifo_link(uint8_t filter, uint8_t channel,
                                        bool enable);

/* --- 发送 --- */

/**
 * @brief 发送一帧 (TXQ)
 * @param tx_obj 报文对象 (id/ctrl 已编码, data 已填充)
 * @param data_len 实际数据字节数
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_txq_load(const mcp2518fd_tx_obj_t *tx_obj,
                             uint8_t data_len);

/**
 * @brief 检查 TXQ 是否未满
 * @return true=未满, false=已满
 */
bool mcp2518fd_txq_not_full(void);

/**
 * @brief 重置 TXQ 状态 (配置模式下调用)
 *
 * 将 TXQ 写指针归零并清除 TXREQ，使硬件读指针与写指针重新同步。
 * 在模式切换 (Config -> Normal) 前调用，避免残留报文导致发送错位。
 *
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_txq_reset(void);

/**
 * @brief 等待 TXQ 排空
 * @param timeout_ms 超时 (ms)
 * @return ESP_OK 排空或 ESP_ERR_TIMEOUT
 */
esp_err_t mcp2518fd_txq_wait_empty(uint32_t timeout_ms);

/**
 * @brief 读取 TXQ 待发送帧数
 * @return 待发送帧数
 */
uint8_t mcp2518fd_txq_usage(void);

/* --- 接收 --- */

/**
 * @brief 检查接收 FIFO 是否有数据
 * @param channel FIFO1 或 FIFO2
 * @return true=非空
 */
bool mcp2518fd_rx_not_empty(uint8_t channel);

/**
 * @brief 从接收 FIFO 读取一帧
 * @param channel   FIFO1 或 FIFO2
 * @param rx_obj    输出报文对象
 * @param data_len  输出实际数据字节数
 * @return ESP_OK 或错误码
 */
esp_err_t mcp2518fd_rx_read(uint8_t channel, mcp2518fd_rx_obj_t *rx_obj,
                            uint8_t *data_len);

/**
 * @brief 读取接收 FIFO 中已存帧数
 * @param channel FIFO1 或 FIFO2
 * @return 已存帧数
 */
uint8_t mcp2518fd_rx_usage(uint8_t channel);

/* --- 状态 --- */

/**
 * @brief 读取 TEC/REC 错误计数
 * @param tec 发送错误计数
 * @param rec 接收错误计数
 */
esp_err_t mcp2518fd_tec_rec_get(uint8_t *tec, uint8_t *rec);

/**
 * @brief 读取错误状态标志 (CiTREC byte2)
 * @return 状态标志位
 */
uint8_t mcp2518fd_error_state_get(void);

/**
 * @brief 读取总线诊断 (CiBDIAG0/1 各一次，保证同步)
 * @param bd0 输出 BDIAG0 值
 * @param bd1 输出 BDIAG1 值
 */
esp_err_t mcp2518fd_bus_diagnostics_get(uint32_t *bd0, uint32_t *bd1);

/**
 * @brief 读取中断标志 (CiINT 低 16 位)
 * @param flags 输出中断标志
 */
esp_err_t mcp2518fd_int_flags_get(uint16_t *flags);

/**
 * @brief 清除中断标志 (写 0 清除)
 * @param flags 要清除的标志
 */
esp_err_t mcp2518fd_int_flags_clear(uint16_t flags);

/**
 * @brief 使能中断
 * @param flags 中断使能位
 */
esp_err_t mcp2518fd_int_enable(uint16_t flags);

/**
 * @brief 读取 ICODE (中断代码)
 * @return ICODE 值
 */
uint8_t mcp2518fd_icode_get(void);

/* --- DLC 转换 --- */

uint8_t mcp2518fd_dlc_to_bytes(uint8_t dlc);
uint8_t mcp2518fd_bytes_to_dlc(uint8_t n);

/* --- 位时序查找表 --- */

/**
 * @brief 获取仲裁段位时序 (按 BaudRateIndex 0-8)
 * @param index 波特率索引
 * @return 时序参数指针，无效索引返回 NULL
 */
const mcp2518fd_nom_timing_t *mcp2518fd_nom_timing_get(uint8_t index);

/**
 * @brief 获取 FD 数据段位时序 (按 FdBaudRateIndex 0-5)
 * @param index FD 波特率索引
 * @return 时序参数指针，无效索引返回 NULL
 */
const mcp2518fd_data_timing_t *mcp2518fd_data_timing_get(uint8_t index);

#ifdef __cplusplus
}
#endif

