# HEX-Bridge

[English](./README.md) | **中文**

HEX-Bridge 是运行于经典 ESP32 开发板上的固件，通过 UBCP v2.0 为上位机工具提供硬件接口，同时实现独立的 CMSIS-DAP over TCP SWD 网络探针。

当前固件支持 SPI 主机和从机、基于 MCP2518FD 的经典 CAN 和 CAN FD、UART2、Wi-Fi 网络及 HEX-Bridge 网络调试探针。设备配置 v5 可分别设置 SPI2 和 SPI3 的主从角色。默认接线下，外接 SPI 使用 SPI2，MCP2518FD 使用 SPI3。

## 从这里开始（Windows）

```powershell
git clone https://github.com/dotLinePlane-com/hex-bridge.git
cd hex-bridge
```

| 你的目标 | 需要准备 | 阅读顺序 |
|---|---|---|
| 拿到板子，让 AI Agent 调用它 | Windows x64、预编译更新器、Python 3.10+、支持本地 stdio MCP 的 Agent | [A · 直接烧录](#flash) → [C · 接入 Agent](#agent) |
| 修改固件、自己编译或制作更新器 | 经典 ESP32、ESP-IDF v6.0.2 及配套工具链 | [B · 从源码构建](#build-source) → [C · 接入 Agent](#agent) |

<a id="flash"></a>
### A · 使用预编译固件

1. 在 `tool/firmware-updater/release/` 查找 `HEX-Bridge-Updater-<版本>.exe`。该目录是本地打包输出，普通 clone 可能没有 EXE。请查看对应版本的发行附件；若无附件，请向维护者索取预编译更新器。[项目 Releases](https://github.com/dotLinePlane-com/hex-bridge/releases)
2. 连接板上的 **UART0 下载口**，在 Windows 设备管理器中确认 COM 号。双击 EXE，核对内置版本，选择该串口并点击「更新固件」。台架使用 COM5，其他电脑以实际枚举结果为准。
3. 等待显示 **100% / 更新完成**。接下来使用 **UART1 控制口**连接 Agent。USB 插好却看不到 COM 口时，检查数据线和板载 USB 转串口驱动。[更新器使用说明](tool/firmware-updater/README.md)

<a id="build-source"></a>
### B · 配置开发工具并从源码构建

在 Windows 安装 ESP-IDF **v6.0.2** 及经典 ESP32 工具链。打开该版本的 ESP-IDF PowerShell 后可直接执行下面的 `idf.py` 命令。使用普通 PowerShell 时，从仓库根目录执行下例。

将 `IDF_PATH` 替换为实际包含 `export.ps1` 的 ESP-IDF 源码目录。若安装时自定义了工具目录，再取消第二行注释，将 `IDF_TOOLS_PATH` 指向安装时使用的工具根目录。这些设置作用于当前终端。

```powershell
$env:IDF_PATH = "C:\Espressif\frameworks\esp-idf-v6.0.2"
# $env:IDF_TOOLS_PATH = "C:\Espressif\tools"
& "$env:IDF_PATH\export.ps1"
idf.py --version
idf.py build
idf.py -p COM5 -b 460800 flash
```

编译成功后，应用镜像位于 `build/hex-bridge.bin`。烧录前将 COM5 换成实际 UART0 下载口；`idf.py flash` 会按构建清单写入引导程序、分区表和应用。查看启动日志可运行 `idf.py -p COM5 monitor`，用 `Ctrl+]` 退出。

**制作可分发的 EXE（可选）**。准备带 Tk 的 Python 3.11 和 Windows Python Launcher。需要新版本号时先修改根目录 `version.txt`。在已设置 `IDF_PATH` 的 PowerShell 中运行 `.\tool\firmware-updater\release.cmd`。生成的 EXE 位于 `tool/firmware-updater/release/`，可以交给路径 A 的用户。

<a id="agent"></a>
### C · 安装 MCP Server 并验证设备

1. 连接板上的 **UART1 控制口**。在仓库根目录的 PowerShell 中执行以下命令，使用 Python 3.10 或更高版本。若 clone 中缺少 wheel，将安装命令末尾的 wheel 路径替换为 `.\mcp`，即可从本地源码安装主机端服务，无需编译 ESP32 固件。

```powershell
$venv = Join-Path $env:LOCALAPPDATA "HEX-Bridge\mcp-venv"
python -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --upgrade .\mcp\dist\hexbridge_mcp-0.1.0-py3-none-any.whl
(Get-Item "$venv\Scripts\hexbridge-mcp.exe").FullName
```

2. 在 Agent 中添加本地 **stdio** MCP Server，名称填 `hex-bridge`，启动命令填上一步输出的绝对路径。以下示例适用于采用 `mcpServers` 格式的客户端。替换账户路径和 COM4，按设备 UART1 配置填写波特率（默认 115200）。

```json
{
  "mcpServers": {
    "hex-bridge": {
      "command": "C:/Users/USER/AppData/Local/HEX-Bridge/mcp-venv/Scripts/hexbridge-mcp.exe",
      "args": ["--serial", "COM4", "--baud", "115200"]
    }
  }
}
```

3. 重新加载 Agent 的 MCP 配置，输入：“请使用 hex-bridge，先调用 `catalog` 列出工具支持的命令，再调用 `device_info` 读取板卡型号和版本。”前者验证服务已启动，后者收到设备响应才说明端到端连接成功。若仅前者成功，请核对 UART1 端口和波特率、关闭占用串口的程序，并断开正在接管控制会话的 Wi-Fi TCP 客户端。[Wi-Fi 接入与更多调用示例](mcp/README.md)

## 当前功能

Harness 可安装主机端 MCP Server，通过串口或 Wi-Fi 调用设备。见 [MCP 安装与配置](mcp/README.md)和[固件功能映射](files/design/host/01-Harness-MCP.md)。

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
| I²C 主机 | I2C0 / I2C1（通道 8 / 9） | Profile v6 可分别选脚和启停。支持 100/400 kHz、7/10 位地址收发、重复起始和 7 位扫描。 |
| 数字 GPIO | 最多 14 条逻辑路（组通道 10 / 11） | 各路可配置输入、推挽或开漏输出、偏置与消抖中断，支持组内批量读写。并用数量取决于引脚占用。 |
| 批量传输、OTA | 预留命令范围 | 上位机可访问的业务模块有待实现。 |

通过配置 CLI 或桌面的 I²C/GPIO 页配置引脚，使用[业务 CLI](script/cli/hex-bridge-io.py) 在同一连接内执行读写。见[阶段 2 实板验收记录](files/design/test-report/Stage2-I2C-GPIO.md)。

实现细节见[固件设计索引](files/design/firmware/README.md)、[Wi-Fi 设计](files/design/firmware/06-WiFi-STA.md)和[DAPLink 设计与实测记录](files/design/firmware/08-DAPLink.md)。

## 可选外设规划

阶段 1 已实现 SPI 路由配置，原始 v2 实现的验证情况见[阶段 1 交付记录](files/design/test-report/Stage1-Peripheral-Delivery.md)。 各固件版本声明支持的实例、通道及引脚配置。每份配置必须保留 UART1 控制或 Wi-Fi 上 TCP 9500 的 UBCP 管理服务。

| 阶段 | 计划支持 |
|---|---|
| 3 · 波形与计数 | 最多 16 个 LEDC PWM 通道逐路选择，支持电机 PWM（MCPWM）及 8 个可独立选择的 PCNT 计数单元。并用数量取决于引脚及共享硬件资源。 |
| 4 · 有线网络 | 在具备兼容 PHY、参考时钟和 RMII 布线的板型上开放可选以太网 MAC。 |
| 5 · 片上经典 CAN | TWAI 配合外部 CAN 收发器使用，可与 MCP2518FD 分别启停。 |

旧版 v1 描述开放 9 个可配置 GPIO；v2 将原 SPI2 六脚纳入可分配池，共 15 个。启用的单线主机预留 SCLK/MOSI/MISO，Quad 额外预留 IO2/IO3，四根数据线均须双向。占用由配置的最大线宽决定，临时单线传输不会释放 Quad 引脚。默认接线且原九条业务信号全开时，外接单线 SPI 为 13 占用、GPIO22/23 空闲；Quad 为 15 占用；关闭外接 SPI 及其无其他使用者的主机后为 9 占用。启用但无挂载设备的主机仍预留总线脚。旧配置迁移保留外接 SPI2 的 Quad 路由及原 CAN 设置；会丢失 v2 字段的 v1 写操作被拒绝。详见[外设功能与配置设计](files/design/function/08-device-profile.md)和[当前板型默认接线](files/sch/esp32-pinout-design.md)。

## 架构

```text
上位机 MCP 客户端 ── UART1 上的 UBCP（115200）────┐
              └── Wi-Fi TCP 上的 UBCP（9500）─────┤
                                                  ▼
                                              HEX-Bridge
                                              ESP32 固件
                                                ├─ MCP2518FD CAN FD
                                                ├─ 外接 SPI（SPI2 / SPI3，主机或从机）
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
| 外接 SPI（默认 SPI2） | SCLK GPIO18，MOSI/IO0 GPIO19，MISO/IO1 GPIO21，CS GPIO27 | Quad 模式另用 IO2 GPIO22 和 IO3 GPIO23。外设与开发板共地。 |
| MCP2518FD SPI | SCK GPIO14，MOSI GPIO13，MISO GPIO36，CS GPIO15，INT GPIO39 | SPI 用于 CAN 模块；注意 ESP32 启动绑带引脚要求。 |
| DAPLink SWD | SWCLK GPIO25，SWDIO GPIO26 | 接 3.3 V 目标并共地。GPIO27 复位支持默认关闭。 |
| Wi-Fi | ESP32 内置无线接口 | 2.4 GHz STA 模式。 |

## DAPLink 实测

探针在 TCP `4441` 上使用 HEX-Bridge TCP framing 承载 CMSIS-DAP，只声明支持 SWD；不提供 JTAG、SWO、USB HID/Bulk 或硬件复位线。GPIO SWD 时钟默认约 100 kHz，请求上限为 250 kHz；实际 GPIO 时序可能更慢。

2026-11-20 使用 OpenOCD `v0.12.0-esp32-20260424` 实测目标 NUCLEO-F103RB（MB1136 C-04，STM32F103RBT6）。探针读到 DP IDCODE `0x1BA01477`，并完成目标检查、halt、PC/SP 寄存器读取、resume，以及 `demo-firmware/demo.bin` 下载和校验。请求 SWD 250 kHz 时，560 字节镜像的 OpenOCD 编程与校验命令耗时 2.728 秒，约 205 B/s；该值包含目标 Flash 擦除和读回校验。此结果只适用于记录中的工具版本和接线，不代表通用兼容认证，也不是 TCP 原始吞吐。

Nucleo 板载 ST-LINK 是另一个独立探针。HEX-Bridge 直连目标 MCU 时，应接 GPIO25→CN7 pin 15（PA14/SWCLK）、GPIO26→CN7 pin 13（PA13/SWDIO）、GND→CN7 pin 8。其他限制及验证证据见 DAPLink 设计记录。

## 固件与协议版本

- UBCP 协议：v2.0。
- System 模块报告的应用固件版本：`0.1.0`。
- DAP `Info` 固件字段：`2.0.0`，与应用固件版本字段相互独立。
- 目标芯片：经典 ESP32（`esp32`）。

## 测试与文档

关闭 CAN FD 后，HXB1 上的 SPI3 主机（通道 4）与 SPI2 从机（通道 6）完成单线 Mode 0 同板回环，8 笔传输全部通过。100 kHz 和 1 MHz 两档均验证了双向数据，从机报告的实际长度分别为 16、8、24 和 512 位。详见[SPI 回环接线与实板测试记录](files/design/test/06-SPI-Tests.md)。

- [SPI 命令与通道分配](files/design/protocol/05-SPI.md)
- [阶段 1 外设交付证据](files/design/test-report/Stage1-Peripheral-Delivery.md)
- [DAPLink 实现与实板测试记录](files/design/firmware/08-DAPLink.md)
- [Wi-Fi STA 设计](files/design/firmware/06-WiFi-STA.md)
- [CAN FD 协议](files/design/protocol/04-CAN.md)
- [CAN 测试计划与报告](files/design/test/05-CAN-Tests.md)
- [固件设计索引](files/design/firmware/README.md)
