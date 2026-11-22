# HEX-Bridge

[English](./README.md) | **中文**

HEX-Bridge 是运行于经典 ESP32 开发板上的固件，通过 UBCP v2.0 为上位机工具提供硬件接口，同时实现独立的 CMSIS-DAP over TCP SWD 网络探针。

当前固件支持外接 SPI 主机、MCP2518FD 经典 CAN 和 CAN FD、UART2、Wi-Fi 网络功能，以及 HEX-Bridge 网络调试探针。设备配置 v2 允许外接 SPI 与 MCP2518FD 分别选择 SPI2 或 SPI3，默认仍为外接 SPI2、CAN 使用 SPI3。

## 当前功能

设备支持通过 UBCP 配置功能开关和业务引脚。UART1 电脑控制口（GPIO4/34）与 UART0 下载口（GPIO1/3）固定保留。共享 Python CLI 和 Tkinter 工具支持导出、预检、保存、重启试用及确认。每份配置保留 UART1，或保留 Wi-Fi STA、TCP 9500 管理服务及已保存的可用配网参数；普通 TCP 业务不充当管理入口。当前或已确认的回退配置仅靠 Wi-Fi 管理时拒绝 WIFI_FORGET；必要驱动完成初始化后才接受确认，并检查控制会话及需要验证的入口。操作命令和首次升级分区要求见[设备配置扩展协议](files/design/protocol/17-Device-Profile.md)。

| 功能 | 接口 | 状态 |
|:---|:---|:---|
| UBCP 控制 | UART1，或 Wi-Fi TCP `9500` 单客户端 | TCP 客户端连接后接管 UBCP 会话。Wi-Fi 断开时，已启用的 UART1 恢复控制。 |
| CAN / CAN FD | MCP2518FD（SPI） | 已实现。UBCP 命令支持通道控制、时序配置、收发、滤波、状态和总线事件。 |
| 外接 UART | UART2（通道 1）、可选 UART1（通道 2） | Profile v4 可关闭 UART1 串口控制，再启用 GPIO4/34 上的普通收发，通过 Wi-Fi TCP 9500 管理。两路串口独立配置、收发、查询状态、清空缓冲及发送 Break。 |
| Wi-Fi STA | ESP32 内置 2.4 GHz 无线接口 | 已实现。支持 IPv4 DHCP/静态配置、DNS、通过 UBCP 配网和断线重连；TCP、UDP、WebSocket 服务由 UBCP 管理。 |
| DAPLink | TCP `4441` 上的 CMSIS-DAP | 已实现 SWD。它是 ESP32 上的网络探针，不是 Nucleo 板载 ST-LINK，也不是 USB HID DAPLink。 |
| 外接 SPI 主机 | 可选 SPI2 / SPI3 | Profile v3 支持两个可独立打开的普通设备（通道 4、5）。可关闭 CAN FD 并同时使用两条主机，各设备可选择 CS；无 CS 设备独占所属主机。共享主机时使用独立的自动片选。 |
| SPI 从机 | SPI2（通道 6）、SPI3（通道 7） | Profile v5 可逐控制器选择主／从。作为从机时预置 1–64 字节，外部主机通过时钟和片选发起单线 Mode 0 事务，再领取实际收到的位数和数据。 |
| I2C、GPIO、批量传输、OTA | 预留命令范围 | 上位机可访问的业务模块有待实现。 |

实现细节见[固件设计索引](files/design/firmware/README.md)、[Wi-Fi 设计](files/design/firmware/06-WiFi-STA.md)和[DAPLink 设计与实测记录](files/design/firmware/08-DAPLink.md)。

## 可选外设规划

阶段 1 在现有驱动上实现配置 v2；主机验证和剩余实板项目见[阶段 1 交付证据](files/design/test-report/Stage1-Peripheral-Delivery.md)。各固件版本声明支持的实例、通道及引脚配置。每份配置必须保留 UART1 控制或 Wi-Fi 上 TCP 9500 的 UBCP 管理服务。

| 阶段 | 计划支持 |
|---|---|
| 1 · 已有接口 | 延续 UART1 控制、UART2、Wi-Fi、DAP/SWD 和 MCP2518FD。SPI2、SPI3 可独立选择和改配；外接 SPI 业务和 MCP2518FD 均可选择任一主机，外接 CAN FD 默认使用 SPI3。 |
| 2 · 数字接口与总线 | 可选数字 GPIO、独立的 I2C0/I2C1，以及配合外部收发器使用的片上经典 CAN（TWAI）。TWAI 与 MCP2518FD CAN FD 分别启停。 |
| 3 · 波形与计数 | 最多 16 个 LEDC PWM 通道逐路选择，支持电机 PWM（MCPWM）及 8 个可独立选择的 PCNT 计数单元。并用数量取决于引脚及共享硬件资源。 |
| 4 · 有线网络 | 在具备兼容 PHY、参考时钟和 RMII 布线的板型上开放可选以太网 MAC。 |

旧版 v1 描述开放 9 个可配置 GPIO；v2 将原 SPI2 六脚纳入可分配池，共 15 个。启用的单线主机预留 SCLK/MOSI/MISO，Quad 额外预留 IO2/IO3，四根数据线均须双向。占用由配置的最大线宽决定，临时单线传输不会释放 Quad 引脚。默认接线且原九条业务信号全开时，外接单线 SPI 为 13 占用、GPIO22/23 空闲；Quad 为 15 占用；关闭外接 SPI 及其无其他使用者的主机后为 9 占用。启用但无挂载设备的主机仍预留总线脚。旧配置迁移保留外接 SPI2 的 Quad 路由及原 CAN 设置；会丢失 v2 字段的 v1 写操作被拒绝。详见[外设功能与配置设计](files/design/function/08-device-profile.md)和[当前板型默认接线](files/sch/esp32-pinout-design.md)。

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

- [阶段 1 外设交付证据](files/design/test-report/Stage1-Peripheral-Delivery.md)
- [DAPLink 实现与实板测试记录](files/design/firmware/08-DAPLink.md)
- [Wi-Fi STA 设计](files/design/firmware/06-WiFi-STA.md)
- [CAN FD 协议](files/design/protocol/04-CAN.md)
- [CAN 测试计划与报告](files/design/test/05-CAN-Tests.md)
- [固件设计索引](files/design/firmware/README.md)
