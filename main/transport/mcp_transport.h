/**
 * @file mcp_transport.h
 * @brief MCP 传输层接口
 *
 * 管理 UART1 (MCP 通信口) 的收发：
 * - 接收任务：从 UART1 流式读取字节 → 帧解析 → msg_bus 分发
 * - 发送接口：将线路帧数据写入 UART1
 */

#pragma once

#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

/**
 * @brief 初始化 MCP 传输层
 *
 * 配置 UART1 硬件，创建接收和发送任务。
 *
 * @param baud_rate  波特率，0 表示使用编译期默认值 HEX_MCP_UART_BAUD
 * @return ESP_OK 或错误码
 */
esp_err_t mcp_transport_init(uint32_t baud_rate);

/**
 * @brief 发送原始线路帧数据到 UART1
 *
 * 线程安全，可从任意任务调用。
 * 使用互斥锁保证发送的原子性。
 *
 * @param data  线路帧数据（已包含 SOF、转义、CRC、EOF）
 * @param len   数据长度
 * @return ESP_OK 或 ESP_ERR_TIMEOUT
 */
esp_err_t mcp_transport_send(const uint8_t *data, size_t len);

/**
 * @brief 停止 MCP 传输层
 *
 * 停止接收/发送任务，卸载 UART 驱动。
 */
void mcp_transport_stop(void);
