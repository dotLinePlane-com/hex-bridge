# 03. UART 扩展串口功能与 RFC 2217 桥接规划

> **状态**: 固件已实现 (57/57 测试通过) / 上位机 RFC 2217 桥接规划已就绪
> **命令码范围**: `0xA0-0xAF`

---

## 1. 功能描述

通过 ESP32 的 `UART2` 硬件外设为 HEX-Bridge 提供独立的扩展串口通道（`UBCP_CH_UART_EXT1 = 1`），支持完整的串口生命周期管理、4 种固件级接收断帧模式、水位流控（XON/XOFF），并规划通过**上位机侧本地 RFC 2217 协议桥**（`本地 RFC 2217 TCP 端口 ↔ 远端 ESP32 UBCP TCP/Serial`）无缝兼容第三方标准串口软件与远程无线调试。

---

## 2. 子功能

| 子功能 | 命令码 / 模块 | 说明 |
|:---|:---|:---|
| 通道开关 | `0xA0` (`UART_OPEN`), `0xA1` (`UART_CLOSE`) | 动态安装/卸载 UART2 驱动，指定 4 种接收模式（被动、行、定长、超时） |
| 参数配置 | `0xA2` (`UART_CONFIG`) | 波特率（9600~5000000）、数据位（5~8）、停止位（1/1.5/2）、校验位（None/Odd/Even）、流控 |
| 数据收发 | `0xA3` (`UART_SEND`), `0xA4` (`UART_RECV`) | 批量数据发送与带 `RxFlags`（溢出/校验错/帧错/Break）的异步事件上报 |
| 线路控制与状态 | `0xA5` (`UART_SET_BREAK`), `0xA6` (`UART_STATUS`), `0xA7` (`UART_FLUSH`) | 发送指定时长 Break 信号、查询收发计数与缓冲区用量、清空/排空（Drain）收发缓冲 |
| **上位机 RFC 2217 桥** | `script/cli/hex-bridge-rfc2217-bridge.py` (规划) | 在 PC 本地监听 RFC 2217 端口（如 `127.0.0.1:2217`），对内转换为 UBCP `0xA0-0xA7` 帧（支持本地串口或 Wi-Fi/以太网远程 UBCP 链路） |

---

## 3. 硬件依赖

- **外设端口**: `UART2` (`UART_NUM_2`)
- **引脚分配**:
  - `TXD2`: **GPIO 32**（双向安全引脚，与原 GPIO 2/12 互换以规避 Strapping 引脚影响烧录）
  - `RXD2`: **GPIO 35**（仅输入 GPI，外部必须接 **10kΩ 上拉电阻**至 3.3V，防止悬空产生假接收或帧错误）
- **缓冲区配置**: RX 环形缓冲区 `2048` 字节，TX 环形缓冲区 `1024` 字节

> 完整引脚分配见 [ESP32 引脚分配方案](../sch/esp32-pinout-design.md)。

---

## 4. 设计文档索引

| 层级 | 文档 | 路径 |
|:---|:---|:---|
| 协议定义 | UART 接口命令协议 | `../protocol/07-UART.md` |
| 固件设计 | UART 扩展模块与上位机 RFC 2217 桥接设计 | `../firmware/04-UART-Module.md` |
| 架构复用 | 网桥多路复用与远程 MCP 传输设计 | `../firmware/05-Bridge-Design.md` |
| 测试用例 | UART 模块测试用例 (57 项) | `../test/02-UART-Tests.md` |
| 测试报告 | UART 测试报告 | `../test-report/UART-Test-Report.md` |

