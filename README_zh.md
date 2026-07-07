# HEX-Bridge

[English](./README.md) | **中文**

**基于 ESP32 的多接口桥接设备 — 通过统一串行协议为 AI Agent 赋予硬件 I/O 能力。**

上位机 MCP Server 通过 UART 与固件通信，协议采用 UBCP (Unified Binary Communication Protocol) v2.0。桥接器对外暴露 CAN FD、SPI、I2C、UART、GPIO、以太网 (TCP/UDP/WebSocket)、OTA 固件升级和批量传输——让 AI 编码 Agent 从纯软件工具进化为可直接操控物理目标板的手和眼。

---

## 架构

```
┌──────────────┐     UBCP v2.0      ┌──────────────┐
│  MCP Server  │◄────(UART 921600)──►│  HEX-Bridge  │──┬─── CAN FD (MCP2518FD)
│  (上位机)     │                    │   (ESP32)    │  ├─── SPI
└──────────────┘                    └──────────────┘  ├─── I2C
                                                       ├─── UART ×2 (扩展 + 调试)
                                                       ├─── GPIO
                                                       └─── 以太网 (100M)
```

- **UART1** — MCP 通信通道，921600 bps (GPIO4 TX / GPIO34 RX)
- **UART2** — 扩展串口 (GPIO32 TX / GPIO35 RX)
- **UART0** — 调试控制台，115200 bps (GPIO1 TX / GPIO3 RX)

固件基于 FreeRTOS，采用消息总线 + 模块化任务架构。各外设模块以 `hex_module_t` 注册，携带所属命令码范围。入站帧经解析、CRC 校验后按命令码路由至目标模块——无硬编码分发逻辑。

---

## 规划能力

| 模块 | 命令范围 | 说明 |
|:---|:---|:---|
| **系统管理** | `0x00-0x0F` | PING、设备信息、配置读写、复位、流控 |
| **CAN / CAN FD** | `0x10-0x1F` | 通道开关、波特率配置（仲裁段 + FD 数据段）、收发帧（≤64 B）、滤波器、总线状态 |
| **SPI** | `0x20-0x2F` | 设备开关、模式/时钟/位序配置、全双工传输、半双工只写/只读、手动 CS 控制 |
| **I2C** | `0x30-0x3F` | 总线开关、速率配置（100k/400k/1M）、7/10 位地址读写、组合写-读（repeated start）、总线扫描 |
| **网络配置** | `0x40-0x4F` | 静态 IP / DHCP、状态查询、DNS 解析、链路状态事件上报 |
| **TCP** | `0x50-0x5F` | Server 开关、Client 连接/断开、数据收发、接入/断开事件 |
| **UDP** | `0x60-0x6F` | Server 开关、Client 创建/删除、经 Server 或 Client 发包、接收事件 |
| **WebSocket** | `0x70-0x7F` | Server 开关、Client 连接/断开、消息收发（文本/二进制/ping/pong）、断开事件 |
| **GPIO** | `0x80-0x8F` | 引脚方向、输出/输入、上下拉、中断使能与触发条件、掩码批量写入、全量读取（限流 50 Hz/引脚） |
| **批量传输** | `0x90-0x9F` | 开始/停止批量会话、数据帧传输（滑动窗口 ACK/NACK + 重传） |
| **UART 扩展** | `0xA0-0xAF` | 串口开关、参数配置（波特率/数据位/校验/流控）、数据发送、4 种接收模式（被动/行/定长/超时）、Break 信号、状态查询、缓冲区刷新 |
| **OTA** | `0xB0-0xBF` | 升级会话开始（SHA-256）、数据块 CRC Chunk 校验与重传、结束与校验、进度查询与上报、固件回滚、双分区信息 |

---

## 协议

UBCP v2.0 帧格式：

```
SOF(AA 55) | Ver | Flags | SeqNum(2B) | CmdCode | ChannelID | PayloadLen(2B) | [Timestamp 4B] | Payload(≤2048B) | CRC16(2B) | EOF(7E)
```

- 固定 10 字节头部 + 可变长载荷
- CRC-16/CCITT-FALSE（多项式 `0x1021`，初始值 `0xFFFF`）
- 字节转义：`0x7E`→`0x7D 0x5E`，`0x7D`→`0x7D 0x5D`
- 全部多字节字段为大端序
- 异步事件（`DIR=1, EVT=1`）用于非请求数据上报（CAN 帧、UART 接收、GPIO 中断）

流式字节级解析器，单缓冲区在线 CRC 计算。滤除伪 SOF 而不重置接收缓冲区。无双重缓冲——协议状态内存占用约 22 KB，远低于 ESP32 可用堆内存 ~300 KB。

---

## 开发进度

| 模块 | 状态 | 备注 |
|:---|:---|:---|
| **协议层** | ✅ 完成 | 帧解析、CRC、字节转义处理 |
| **消息总线** | ✅ 完成 | 命令码路由分发 |
| **传输层 (MCP)** | ✅ 完成 | UART1 921600 bps 收发与帧组装 |
| **系统管理 (0x00-0x0F)** | ✅ 基础 | PING、GET_INFO 已实现 |
| **UART 扩展 (0xA0-0xAF)** | ✅ 完整 | 全部 8 条命令，57 条用例 — 173 pass / 0 fail / 2 skip |
| **CAN FD** | ☐ 待实现 | MCP2518FD 经 SPI，引脚已分配 |
| **SPI** | ☐ 待实现 | — |
| **I2C** | ☐ 待实现 | 24C02 EEPROM，引脚已分配 |
| **网络 / TCP / UDP / WS** | ☐ 待实现 | LAN8720 RMII PHY，引脚已分配 |
| **GPIO** | ☐ 待实现 | — |
| **批量传输** | ☐ 待实现 | — |
| **OTA** | ☐ 待实现 | 双分区 + SHA-256 校验 |

---

## 硬件

| 外设 | 引脚 | 说明 |
|:---|:---|:---|
| CAN FD (MCP2518FD) | SCK=14, MOSI=13, MISO=36, CS=15, INT=39 | SPI 接口，CS 为 Strapping 引脚（需 10 kΩ 上拉） |
| I2C (EEPROM 24C02) | SCL=12, SDA=33 | GPIO12=MTDI，需 4.7 kΩ 上拉确保启动电平 |
| 以太网 (LAN8720) | RMII 固定引脚, PHY_RST=5 | MDC=23, MDIO=18 |
| UART1 (MCP) | TX=4, RX=34 | RX 为 GPI，需外接 10 kΩ 上拉 |
| UART2 (扩展) | TX=32, RX=35 | RX 为 GPI，需外接 10 kΩ 上拉 |
| UART0 (调试) | TX=1, RX=3 | ESP32 默认调试串口 |

---

## 编译与烧录

```bash
# 编译
idf.py build

# 烧录（将 COMx 替换为实际端口）
idf.py -p COM35 flash

# 监视调试输出
idf.py -p COM34 monitor
```

固件版本 `0.1.0`，型号 `HXB1`，目标芯片 `esp32`。
