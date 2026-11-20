# HEX-Bridge

[English](./README.md) | **中文**

HEX-Bridge 是运行于经典 ESP32 开发板上的固件，通过 UBCP v2.0 为上位机工具提供硬件接口，同时实现独立的 CMSIS-DAP over TCP SWD 网络探针。

当前固件支持 MCP2518FD CAN FD、外接 UART、Wi-Fi 网络功能，以及 HEX-Bridge 网络调试探针。SPI、I2C、通用 GPIO、批量传输和 OTA 命令模块尚未实现。SPI 目前用于 ESP32 与 CAN 控制器之间的内部通信。

## 当前功能

| 功能 | 接口 | 状态 |
|:---|:---|:---|
| UBCP 控制 | UART1，或 Wi-Fi TCP `9500` 单客户端 | 已实现。TCP 客户端连接后接管 UBCP 会话；Wi-Fi 断开后恢复 UART1。 |
| CAN / CAN FD | MCP2518FD（SPI） | 已实现。UBCP 命令支持通道控制、时序配置、收发、滤波、状态和总线事件。 |
| 外接 UART | UART2 | 已实现。支持串口参数配置、收发、状态、清空缓冲和 Break 控制。 |
| Wi-Fi STA | ESP32 内置 2.4 GHz 无线接口 | 已实现。支持 IPv4 DHCP/静态配置、DNS、通过 UBCP 配网和断线重连；TCP、UDP、WebSocket 服务由 UBCP 管理。 |
| DAPLink | TCP `4441` 上的 CMSIS-DAP | 已实现 SWD。它是 ESP32 上的网络探针，不是 Nucleo 板载 ST-LINK，也不是 USB HID DAPLink。 |
| 外接 SPI、I2C、GPIO、批量传输、OTA | 预留命令范围 | 尚未实现为上位机可访问的功能模块。 |

实现细节见[固件设计索引](files/design/firmware/README.md)、[Wi-Fi 设计](files/design/firmware/06-WiFi-STA.md)和[DAPLink 设计与实测记录](files/design/firmware/08-DAPLink.md)。

## 架构

```text
上位机 MCP 客户端 ── UART1 上的 UBCP（115200）────┐
              └── Wi-Fi TCP 上的 UBCP（9500）─────┤
                                                  ▼
                                              HEX-Bridge
                                              ESP32 固件
                                                ├─ MCP2518FD CAN FD
                                                ├─ 外接 UART2
                                                ├─ Wi-Fi TCP / UDP / WebSocket 服务
                                                └─ TCP 4441 上的 CMSIS-DAP
                                                       │ SWD
                                                       └─ 目标 MCU
```

UBCP 默认经 UART1 通信。TCP `9500` 客户端连接后取得唯一的 UBCP 主机控制会话；同一时间只允许一个 UBCP 传输端处于活动状态。独立的 DAP 服务会在 Wi-Fi 获得可用 IP 后监听 TCP `4441`，并只允许一个调试客户端。

## 硬件连接

| 功能 | ESP32 引脚 | 说明 |
|:---|:---|:---|
| UBCP UART1 | TX GPIO4，RX GPIO34 | 默认 115200 bps；GPIO34 仅输入，RX 需按板级设计提供偏置。 |
| 外接 UART2 | TX GPIO32，RX GPIO35 | 默认 115200 bps；GPIO35 仅输入。 |
| MCP2518FD SPI | SCK GPIO14，MOSI GPIO13，MISO GPIO36，CS GPIO15，INT GPIO39 | SPI 用于 CAN 模块；注意 ESP32 启动绑带引脚要求。 |
| DAPLink SWD | SWCLK GPIO25，SWDIO GPIO26 | 接 3.3 V 目标并共地。GPIO27 复位支持默认关闭。 |
| Wi-Fi | ESP32 内置无线接口 | 2.4 GHz STA 模式。 |

## DAPLink 实测

探针在 TCP `4441` 上使用 HEX-Bridge TCP framing 承载 CMSIS-DAP，只声明支持 SWD；不提供 JTAG、SWO、USB HID/Bulk 或硬件复位线。GPIO SWD 时钟默认约 100 kHz，请求上限为 250 kHz；实际 GPIO 时序可能更慢。

2026-11-20 使用 OpenOCD `v0.12.0-esp32-20260424` 实测目标 NUCLEO-F103RB（MB1136 C-04，STM32F103RBT6）。探针读到 DP IDCODE `0x1BA01477`，并完成目标检查、halt、PC/SP 寄存器读取、resume，以及 `demo-firmware/demo.bin` 下载和校验。请求 SWD 250 kHz 时，560 字节镜像的 OpenOCD 编程与校验命令耗时 2.728 秒，约 205 B/s；该值包含目标 Flash 擦除和读回校验。此结果只适用于记录中的工具版本和接线，不代表通用兼容认证，也不是 TCP 原始吞吐。

Nucleo 板载 ST-LINK 是另一个独立探针。HEX-Bridge 直连目标 MCU 时，应接 GPIO25→CN7 pin 15（PA14/SWCLK）、GPIO26→CN7 pin 13（PA13/SWDIO）、GND→CN7 pin 8。其他限制及验证证据见 DAPLink 设计记录。

## 编译

使用 ESP-IDF 6.0.x 为经典 ESP32 构建（当前项目工作台使用 v6.0.2）：

```sh
idf.py set-target esp32
idf.py build
```

默认输出目录为 `build/`，应用镜像为 `build/hex-bridge.bin`。运行 `idf.py` 前需先完成当前主机对应的 ESP-IDF 环境导出。

## 固件与协议版本

- UBCP 协议：v2.0。
- System 模块报告的应用固件版本：`0.1.0`。
- DAP `Info` 固件字段：`2.0.0`，与应用固件版本字段相互独立。
- 目标芯片：经典 ESP32（`esp32`）。

## 测试与文档

- [DAPLink 实现与实板测试记录](files/design/firmware/08-DAPLink.md)
- [Wi-Fi STA 设计](files/design/firmware/06-WiFi-STA.md)
- [CAN FD 协议](files/design/protocol/04-CAN.md)
- [CAN 测试计划与报告](files/design/test/05-CAN-Tests.md)
- [固件设计索引](files/design/firmware/README.md)
