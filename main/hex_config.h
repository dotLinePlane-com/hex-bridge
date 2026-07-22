/**
 * @file hex_config.h
 * @brief HEX-Bridge 全局硬件配置
 *
 * 所有硬件引脚映射、缓冲区大小、默认参数集中定义于此。
 * 修改硬件配置时只需编辑本文件。
 */

#pragma once

#include "driver/gpio.h"
#include "driver/uart.h"

/* ========================================================================
 * 调试控制
 * ======================================================================== */

/** 调试 UART (UART0) 开关。设为 0 可在量产固件中关闭调试输出 */
#define HEX_DEBUG_UART_ENABLE       1

/* ========================================================================
 * UART1 — MCP 通信口 (与上位机通信)
 * ======================================================================== */

#define HEX_MCP_UART_NUM            UART_NUM_1
#define HEX_MCP_UART_TX_PIN         GPIO_NUM_4
#define HEX_MCP_UART_RX_PIN         GPIO_NUM_34   /* GPI 仅输入，需外接 10kΩ 上拉 */
#define HEX_MCP_UART_BAUD           115200        /* 115200 bps (临时测试) */
#define HEX_MCP_UART_RX_BUF_SIZE    (4096)         /* UART 驱动接收环形缓冲区 */
#define HEX_MCP_UART_TX_BUF_SIZE    (2048)         /* UART 驱动发送环形缓冲区 */

/* ========================================================================
 * UART2 — 扩展口 (用户外设串口)
 * ======================================================================== */

#define HEX_EXT_UART_NUM            UART_NUM_2
#define HEX_EXT_UART_TX_PIN         GPIO_NUM_32    /* GPIO32，与 I2C SCL 互换，避免 GPIO2/GPIO12 Strapping 问题 */
#define HEX_EXT_UART_RX_PIN         GPIO_NUM_35    /* GPI 仅输入，需外接 10kΩ 上拉 */
#define HEX_EXT_UART_DEFAULT_BAUD   115200
#define HEX_EXT_UART_RX_BUF_SIZE    (2048)
#define HEX_EXT_UART_TX_BUF_SIZE    (1024)

/* ========================================================================
 * CAN FD — MCP2518FD (SPI 接口)
 * ======================================================================== */

#define HEX_CAN_SPI_SCK_PIN         GPIO_NUM_14
#define HEX_CAN_SPI_MOSI_PIN        GPIO_NUM_13
#define HEX_CAN_SPI_MISO_PIN        GPIO_NUM_36    /* GPI 仅输入，需外接 10kΩ 上拉 */
#define HEX_CAN_SPI_CS_PIN          GPIO_NUM_15    /* Strapping 引脚，需外接 10kΩ 上拉 */
#define HEX_CAN_INT_PIN             GPIO_NUM_39    /* GPI 仅输入，需外接 10kΩ 上拉 */

/* ========================================================================
 * I2C — EEPROM (24C02)
 * ======================================================================== */

#define HEX_I2C_SCL_PIN             GPIO_NUM_12    /* GPIO12=MTDI，I2C 开漏+4.7kΩ上拉确保复位高电平 */
#define HEX_I2C_SDA_PIN             GPIO_NUM_33

/* ========================================================================
 * 以太网 — LAN8720 (RMII)
 * ======================================================================== */

#define HEX_ETH_PHY_RST_PIN         GPIO_NUM_5     /* 默认下拉，上电后软件拉高激活 */
#define HEX_ETH_MDC_PIN             GPIO_NUM_23
#define HEX_ETH_MDIO_PIN            GPIO_NUM_18

/* ========================================================================
 * UBCP 协议参数
 * ======================================================================== */

/** 最大载荷长度（字节） */
#define HEX_UBCP_MAX_PAYLOAD        2048

/** 帧接收逻辑缓冲区大小（头部 + 时间戳 + 最大载荷） */
#define HEX_UBCP_FRAME_BUF_SIZE     (10 + 4 + HEX_UBCP_MAX_PAYLOAD)

/** MCP 发送队列深度 */
#define HEX_MCP_TX_QUEUE_DEPTH      16

/** MCP 接收分发队列深度 */
#define HEX_MCP_RX_QUEUE_DEPTH      8

/* ========================================================================
 * FreeRTOS 任务参数
 * ======================================================================== */

#define HEX_MCP_RECV_TASK_STACK     (6144)
#define HEX_MCP_RECV_TASK_PRIO      (10)
#define HEX_MCP_SEND_TASK_STACK     (6144)
#define HEX_MCP_SEND_TASK_PRIO      (10)
#define HEX_UART_RX_TASK_STACK      (6144)
#define HEX_UART_RX_TASK_PRIO       (8)

/* ========================================================================
 * 流控参数
 * ======================================================================== */

/** RX 缓冲区高水位 — 超过此百分比发送 XOFF */
#define HEX_FLOW_XOFF_PCT           80

/** RX 缓冲区低水位 — 低于此百分比发送 XON */
#define HEX_FLOW_XON_PCT            50

/* ========================================================================
 * 设备信息
 * ======================================================================== */

#define HEX_FW_VERSION_MAJOR        0
#define HEX_FW_VERSION_MINOR        1
#define HEX_FW_VERSION_PATCH        0
#define HEX_MODEL_ID                "HXB1"
#define HEX_PROTO_VERSION           0x02
