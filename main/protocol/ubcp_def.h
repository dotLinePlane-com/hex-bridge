/**
 * @file ubcp_def.h
 * @brief UBCP v2.0 协议常量定义
 *
 * 包含所有命令码、错误码、标志位等协议级常量。
 * 与 files/design/protocol/ 文档保持一致。
 */

#pragma once

#include <stdint.h>

/* ========================================================================
 * 帧标识
 * ======================================================================== */

#define UBCP_SOF_0                  0xAA    /**< 帧头第一字节 */
#define UBCP_SOF_1                  0x55    /**< 帧头第二字节 */
#define UBCP_EOF                    0x7E    /**< 帧尾 */
#define UBCP_ESC                    0x7D    /**< 转义前缀 */
#define UBCP_ESC_EOF                0x5E    /**< 0x7E 转义后缀 → 0x7D 0x5E */
#define UBCP_ESC_ESC                0x5D    /**< 0x7D 转义后缀 → 0x7D 0x5D */

#define UBCP_VERSION                0x02    /**< 当前协议版本 */

/* ========================================================================
 * 固定头部大小
 * ======================================================================== */

#define UBCP_HEADER_SIZE            10      /**< 固定头部字节数 */
#define UBCP_TIMESTAMP_SIZE         4       /**< 可选时间戳字节数 */
#define UBCP_CRC_SIZE               2       /**< CRC16 字节数 */
#define UBCP_EOF_SIZE               1       /**< 帧尾字节数 */
#define UBCP_SOF_SIZE               2       /**< 帧头字节数 */

/* ========================================================================
 * Flags 位定义 (Byte 3)
 * ======================================================================== */

#define UBCP_FLAG_DIR               (1 << 7)    /**< 方向：0=主机→设备, 1=设备→主机 */
#define UBCP_FLAG_ACK               (1 << 6)    /**< 响应请求：1=需要响应 */
#define UBCP_FLAG_TS                (1 << 5)    /**< 时间戳：1=存在时间戳字段 */
#define UBCP_FLAG_EVT               (1 << 4)    /**< 事件：1=异步事件上报 */
#define UBCP_FLAG_FRAG              (1 << 3)    /**< 分片：1=分片帧 */

/* ========================================================================
 * 序列号特殊值
 * ======================================================================== */

#define UBCP_SEQ_INVALID            0x0000  /**< 无效序列号 */
#define UBCP_SEQ_BROADCAST          0xFFFF  /**< 广播序列号 */

/* ========================================================================
 * 通道号特殊值
 * ======================================================================== */

#define UBCP_CHANNEL_BROADCAST      0xFF    /**< 广播通道 */

#define UBCP_DEV_TYPE_UART          1       /**< 扩展串口 */
#define UBCP_DEV_TYPE_CAN           2       /**< CAN / CAN FD 总线 */
#define UBCP_DEV_TYPE_SPI           3       /**< SPI 总线 */
#define UBCP_DEV_TYPE_I2C           4       /**< I2C 总线 */
#define UBCP_DEV_TYPE_GPIO          5       /**< GPIO 引脚组 */

#define UBCP_CH_UART_EXT1           1       /**< 物理扩展串口 1 (UART2) */
#define UBCP_CH_UART_EXT2           2       /**< 物理扩展串口 2 (预留) */
#define UBCP_CH_CAN_EXT1            3       /**< 物理扩展 CAN 1 */
#define UBCP_CH_SPI_EXT1            4       /**< 物理扩展 SPI 1 */

/* ========================================================================
 * 命令码定义 — 系统管理 (0x00-0x0F)
 * ======================================================================== */

#define UBCP_CMD_PING               0x00
#define UBCP_CMD_GET_INFO           0x01
#define UBCP_CMD_GET_CONFIG         0x02
#define UBCP_CMD_SET_CONFIG         0x03
#define UBCP_CMD_RESET              0x04
#define UBCP_CMD_FLOW_CONTROL       0x05
#define UBCP_CMD_SYS_BOOT_EVENT     0x06
#define UBCP_CMD_GET_TOPOLOGY       0x07

/* ========================================================================
 * ResetReason 定义 (SYS_BOOT_EVENT 载荷)
 * 映射自 ESP-IDF v6.0.1 esp_reset_reason_t
 * ======================================================================== */

#define UBCP_RESET_POWERON          0x01    /**< ESP_RST_POWERON */
#define UBCP_RESET_SW               0x03    /**< ESP_RST_SW (esp_restart) */
#define UBCP_RESET_DEEPSLEEP        0x05    /**< ESP_RST_DEEPSLEEP */
#define UBCP_RESET_INT_WDT          0x06    /**< ESP_RST_INT_WDT */
#define UBCP_RESET_TASK_WDT         0x07    /**< ESP_RST_TASK_WDT */
#define UBCP_RESET_WDT              0x08    /**< ESP_RST_WDT */
#define UBCP_RESET_BROWNOUT         0x0D    /**< ESP_RST_BROWNOUT */
#define UBCP_RESET_PANIC            0x0E    /**< ESP_RST_PANIC */
#define UBCP_RESET_UNKNOWN          0xFF    /**< 未知复位原因 */

/* ========================================================================
 * BootStatus 定义 (SYS_BOOT_EVENT 载荷)
 * ======================================================================== */

#define UBCP_BOOT_STATUS_NORMAL     0x00
#define UBCP_BOOT_STATUS_OTA_ROLLBACK 0x01

/* ========================================================================
 * 系统全局配置组 (ConfigGroup=0x00) ConfigKey 定义
 * ======================================================================== */

#define UBCP_CFGKEY_DEVICE_NAME             0x01    /**< DeviceName, str, 默认 "HXB-Device" */
#define UBCP_CFGKEY_HEARTBEAT_INTERVAL      0x02    /**< HeartbeatInterval, u16, 默认 5000ms */
#define UBCP_CFGKEY_FLOW_CONTROL_ENABLE     0x03    /**< FlowControlEnable, u8, 默认 0x01 (启用) */
#define UBCP_CFGKEY_UART_CHANNEL_COUNT      0x10    /**< UartChannelCount, u8, 只读, 默认 1 */
#define UBCP_CFGKEY_CAN_CHANNEL_COUNT       0x11    /**< CanChannelCount, u8, 只读, 默认 2 */
#define UBCP_CFGKEY_MCP_BAUD_RATE          0x12    /**< McpBaudRate, u32, 可读写, 默认 921600 */

#define UBCP_CFGKEY_READONLY_MASK           0x10    /**< ConfigKey >= 0x10 为只读 */

/* ========================================================================
 * 命令码定义 — CAN (0x10-0x1F)
 * ======================================================================== */

#define UBCP_CMD_CAN_OPEN           0x10
#define UBCP_CMD_CAN_CLOSE          0x11
#define UBCP_CMD_CAN_CONFIG         0x12
#define UBCP_CMD_CAN_SEND           0x13
#define UBCP_CMD_CAN_RECV           0x14
#define UBCP_CMD_CAN_FILTER         0x15
#define UBCP_CMD_CAN_STATUS         0x16

/* ========================================================================
 * 命令码定义 — SPI (0x20-0x2F)
 * ======================================================================== */

#define UBCP_CMD_SPI_OPEN           0x20
#define UBCP_CMD_SPI_CLOSE          0x21
#define UBCP_CMD_SPI_CONFIG         0x22
#define UBCP_CMD_SPI_TRANSFER       0x23
#define UBCP_CMD_SPI_WRITE          0x24
#define UBCP_CMD_SPI_READ           0x25
#define UBCP_CMD_SPI_CS_CONTROL     0x26

/* ========================================================================
 * 命令码定义 — I2C (0x30-0x3F)
 * ======================================================================== */

#define UBCP_CMD_I2C_OPEN           0x30
#define UBCP_CMD_I2C_CLOSE          0x31
#define UBCP_CMD_I2C_CONFIG         0x32
#define UBCP_CMD_I2C_WRITE          0x33
#define UBCP_CMD_I2C_READ           0x34
#define UBCP_CMD_I2C_WRITE_READ     0x35
#define UBCP_CMD_I2C_SCAN           0x36

/* ========================================================================
 * 命令码定义 — 网络配置 (0x40-0x4F)
 * ======================================================================== */

#define UBCP_CMD_NET_CONFIG         0x40
#define UBCP_CMD_NET_STATUS         0x41
#define UBCP_CMD_NET_DNS            0x42
#define UBCP_CMD_NET_LINK_EVENT     0x43
#define UBCP_CMD_NET_LIST_CONNS     0x44

/* ========================================================================
 * 命令码定义 — TCP (0x50-0x5F)
 * ======================================================================== */

#define UBCP_CMD_TCP_SERVER_OPEN    0x50
#define UBCP_CMD_TCP_SERVER_CLOSE   0x51
#define UBCP_CMD_TCP_CLIENT_CONN    0x52
#define UBCP_CMD_TCP_CLIENT_DISC    0x53
#define UBCP_CMD_TCP_SEND           0x54
#define UBCP_CMD_TCP_RECV           0x55
#define UBCP_CMD_TCP_ACCEPT         0x56
#define UBCP_CMD_TCP_CLOSE          0x57
#define UBCP_CMD_TCP_DISC_EVENT     0x58
#define UBCP_CMD_TCP_LIST_CLIENTS   0x59
#define UBCP_CMD_TCP_KICK_CLIENT    0x5A
#define UBCP_CMD_TCP_CONN_STATUS    0x5B

/* ========================================================================
 * 命令码定义 — UDP (0x60-0x6F)
 * ======================================================================== */

#define UBCP_CMD_UDP_SERVER_OPEN    0x60
#define UBCP_CMD_UDP_SERVER_CLOSE   0x61
#define UBCP_CMD_UDP_CLIENT_CREATE  0x62
#define UBCP_CMD_UDP_CLIENT_DELETE  0x63
#define UBCP_CMD_UDP_SERVER_SEND    0x64
#define UBCP_CMD_UDP_CLIENT_SEND    0x65
#define UBCP_CMD_UDP_RECV           0x66

/* ========================================================================
 * 命令码定义 — WebSocket (0x70-0x7F)
 * ======================================================================== */

#define UBCP_CMD_WS_SERVER_OPEN     0x70
#define UBCP_CMD_WS_SERVER_CLOSE    0x71
#define UBCP_CMD_WS_CLIENT_CONN     0x72
#define UBCP_CMD_WS_CLIENT_DISC     0x73
#define UBCP_CMD_WS_SEND            0x74
#define UBCP_CMD_WS_RECV            0x75
#define UBCP_CMD_WS_ACCEPT          0x76
#define UBCP_CMD_WS_DISC_EVENT      0x77
#define UBCP_CMD_WS_LIST_CLIENTS    0x78
#define UBCP_CMD_WS_KICK_CLIENT     0x79

/* ========================================================================
 * 命令码定义 — GPIO (0x80-0x8F)
 * ======================================================================== */

#define UBCP_CMD_GPIO_SET_DIR       0x80
#define UBCP_CMD_GPIO_WRITE         0x81
#define UBCP_CMD_GPIO_READ          0x82
#define UBCP_CMD_GPIO_SET_PULL      0x83
#define UBCP_CMD_GPIO_INT_EN        0x84
#define UBCP_CMD_GPIO_INT_EVENT     0x85
#define UBCP_CMD_GPIO_WRITE_MASK    0x86
#define UBCP_CMD_GPIO_READ_ALL      0x87

/* ========================================================================
 * 命令码定义 — 批量传输 (0x90-0x9F)
 * ======================================================================== */

#define UBCP_CMD_BULK_START         0x90
#define UBCP_CMD_BULK_DATA          0x91
#define UBCP_CMD_BULK_ACK           0x92
#define UBCP_CMD_BULK_STOP          0x93

/* ========================================================================
 * 命令码定义 — UART (0xA0-0xAF)
 * ======================================================================== */

#define UBCP_CMD_UART_OPEN          0xA0
#define UBCP_CMD_UART_CLOSE         0xA1
#define UBCP_CMD_UART_CONFIG        0xA2
#define UBCP_CMD_UART_SEND          0xA3
#define UBCP_CMD_UART_RECV          0xA4
#define UBCP_CMD_UART_SET_BREAK     0xA5
#define UBCP_CMD_UART_STATUS        0xA6
#define UBCP_CMD_UART_FLUSH         0xA7

/* ========================================================================
 * 命令码定义 — OTA (0xB0-0xBF)
 * ======================================================================== */

#define UBCP_CMD_OTA_BEGIN          0xB0
#define UBCP_CMD_OTA_DATA           0xB1
#define UBCP_CMD_OTA_END            0xB2
#define UBCP_CMD_OTA_STATUS         0xB3
#define UBCP_CMD_OTA_ROLLBACK       0xB4
#define UBCP_CMD_OTA_GET_PARTITION  0xB5
#define UBCP_CMD_OTA_PROGRESS       0xB6

/* ========================================================================
 * 命令码范围（用于模块路由）
 * ======================================================================== */

#define UBCP_CMD_RANGE_SYSTEM_START 0x00
#define UBCP_CMD_RANGE_SYSTEM_END   0x0F
#define UBCP_CMD_RANGE_CAN_START    0x10
#define UBCP_CMD_RANGE_CAN_END      0x1F
#define UBCP_CMD_RANGE_SPI_START    0x20
#define UBCP_CMD_RANGE_SPI_END      0x2F
#define UBCP_CMD_RANGE_I2C_START    0x30
#define UBCP_CMD_RANGE_I2C_END      0x3F
#define UBCP_CMD_RANGE_NET_START    0x40
#define UBCP_CMD_RANGE_NET_END      0x4F
#define UBCP_CMD_RANGE_TCP_START    0x50
#define UBCP_CMD_RANGE_TCP_END      0x5F
#define UBCP_CMD_RANGE_UDP_START    0x60
#define UBCP_CMD_RANGE_UDP_END      0x6F
#define UBCP_CMD_RANGE_WS_START     0x70
#define UBCP_CMD_RANGE_WS_END       0x7F
#define UBCP_CMD_RANGE_GPIO_START   0x80
#define UBCP_CMD_RANGE_GPIO_END     0x8F
#define UBCP_CMD_RANGE_BULK_START   0x90
#define UBCP_CMD_RANGE_BULK_END     0x9F
#define UBCP_CMD_RANGE_UART_START   0xA0
#define UBCP_CMD_RANGE_UART_END     0xAF
#define UBCP_CMD_RANGE_OTA_START    0xB0
#define UBCP_CMD_RANGE_OTA_END      0xBF

/* ========================================================================
 * 通用错误码 (0x00-0x0F)
 * ======================================================================== */

#define UBCP_ERR_SUCCESS            0x00
#define UBCP_ERR_UNKNOWN            0x01
#define UBCP_ERR_PARAM              0x02
#define UBCP_ERR_TIMEOUT            0x03
#define UBCP_ERR_BUSY               0x04
#define UBCP_ERR_NOT_OPEN           0x05
#define UBCP_ERR_NOT_SUPPORT        0x06
#define UBCP_ERR_BUFFER_FULL        0x07
#define UBCP_ERR_CRC                0x08
#define UBCP_ERR_FRAME              0x09
#define UBCP_ERR_CHANNEL_INVALID    0x0A
#define UBCP_ERR_ALREADY_OPEN       0x0B
#define UBCP_ERR_PERMISSION         0x0C
#define UBCP_ERR_OVERFLOW           0x0D
#define UBCP_ERR_SEQ_MISMATCH       0x0E
#define UBCP_ERR_VERSION            0x0F
#define UBCP_ERR_TYPE_MISMATCH      0x16
#define UBCP_ERR_HAL_FAIL           0x17

/* ========================================================================
 * UART 错误码 (0xA0-0xAF)
 * ======================================================================== */

#define UBCP_ERR_UART_PARITY        0xA0
#define UBCP_ERR_UART_FRAME         0xA1
#define UBCP_ERR_UART_OVERFLOW      0xA2
#define UBCP_ERR_UART_BAUD          0xA3
#define UBCP_ERR_UART_BREAK         0xA4

/* ========================================================================
 * Capabilities 位图 (GET_INFO 响应)
 * ======================================================================== */

#define UBCP_CAP_CAN                (1 << 0)
#define UBCP_CAP_CAN_FD             (1 << 1)
#define UBCP_CAP_SPI                (1 << 2)
#define UBCP_CAP_I2C                (1 << 3)
#define UBCP_CAP_UART               (1 << 4)
#define UBCP_CAP_ETH                (1 << 5)
#define UBCP_CAP_TCP                (1 << 6)
#define UBCP_CAP_UDP                (1 << 7)
#define UBCP_CAP_WEBSOCKET          (1 << 8)
#define UBCP_CAP_GPIO               (1 << 9)
#define UBCP_CAP_BULK               (1 << 10)
#define UBCP_CAP_OTA                (1 << 11)

/* ========================================================================
 * UART RxMode 定义
 * ======================================================================== */

#define UBCP_UART_RXMODE_PASSIVE    0x00    /**< 被动上报模式 */
#define UBCP_UART_RXMODE_LINE       0x01    /**< 行模式 */
#define UBCP_UART_RXMODE_FIXED      0x02    /**< 定长模式 */
#define UBCP_UART_RXMODE_TIMEOUT    0x03    /**< 超时模式 */

/* ========================================================================
 * UART FlushType 定义
 * ======================================================================== */

#define UBCP_UART_FLUSH_RX          0x00
#define UBCP_UART_FLUSH_TX          0x01
#define UBCP_UART_FLUSH_ALL         0x02
#define UBCP_UART_FLUSH_DRAIN       0x03

/* ========================================================================
 * 最大载荷长度
 * ======================================================================== */

#define UBCP_MAX_PAYLOAD_LEN        2048
