# HEX-Bridge

[English](./README.md) | **中文**

**基于 ESP32 的多接口桥接设备 — 通过统一串行协议为 AI Agent 赋予硬件 I/O 能力。**

上位机 MCP Server 通过 UART 与固件通信，协议采用 UBCP (Unified Binary Communication Protocol) v2.0。桥接器对外暴露 CAN FD、SPI、I2C、UART、GPIO、Wi-Fi STA (TCP/UDP/WebSocket)、OTA 固件升级和批量传输——让 AI 编码 Agent 从纯软件工具进化为可直接操控物理目标板的手和眼。

---

## 编译环境

| 项目 | 版本 / 信息 |
|:---|:---|
| **IDE** | 点线面 Code |
| **SDK** | ESP-IDF v6.0.1 |
| **工具链** | xtensa-esp-elf 15.2.0 (20251204) |
| **Python** | 3.11 (ESP-IDF Python 虚拟环境) |
| **构建系统** | CMake 4.0 + Ninja 1.12 |
| **RTOS** | FreeRTOS (随 ESP-IDF 预装) |
| **C 标准** | C11 (使用 picoLIBC，无 newlib 依赖) |

---

## 硬件

### 芯片

| 项目 | 规格 |
|:---|:---|
| **MCU** | Espressif ESP32 (Xtensa 32-bit LX6 双核) |
| **CPU 主频** | 最高 240 MHz |
| **SRAM** | 520 KB 片内 + 8 MB 片外 PSRAM |
| **Flash** | 16 MB (SPI) |
| **FreeRTOS 堆** | ~300 KB 可用 |

### 引脚

| 外设 | 引脚 | 说明 |
|:---|:---|:---|
| CAN FD (MCP2518FD) | SCK=14, MOSI=13, MISO=36, CS=15, INT=39 | SPI 接口，CS 为 Strapping 引脚（需 10 kΩ 上拉） |
| I2C (EEPROM 24C02) | SCL=12, SDA=33 | GPIO12=MTDI，需 4.7 kΩ 上拉确保启动电平 |
| Wi-Fi STA | ESP32 内置无线接口 | 2.4 GHz、IPv4，通过 UART1 配网 |
| UART1 (MCP) | TX=4, RX=34 | RX 为 GPI，需外接 10 kΩ 上拉 |
| UART2 (扩展) | TX=32, RX=35 | RX 为 GPI，需外接 10 kΩ 上拉 |
| UART0 (调试) | TX=1, RX=3 | ESP32 默认调试串口 |

---

## 架构

```
┌──────────────┐     UBCP v2.0      ┌──────────────┐
│  MCP Server  │◄────(UART 115200)──►│  HEX-Bridge  │──┬─── CAN FD (MCP2518FD)
│  (上位机)     │                    │   (ESP32)    │  ├─── SPI
└──────────────┘                    └──────────────┘  ├─── I2C
                                                       ├─── UART ×2 (扩展 + 调试)
                                                       ├─── GPIO
                                                       └─── Wi-Fi STA (2.4 GHz)
```

- **UART1** — MCP 通信通道，115200 bps (GPIO4 TX / GPIO34 RX)
- **UART2** — 扩展串口 (GPIO32 TX / GPIO35 RX)
- **UART0** — 调试控制台，115200 bps (GPIO1 TX / GPIO3 RX)

固件基于 FreeRTOS，采用消息总线 + 模块化任务架构。各外设模块以 `hex_module_t` 注册，携带所属命令码范围。入站帧经解析、CRC 校验后按命令码路由至目标模块——无硬编码分发逻辑。

---

## 规划能力

| 模块 | 命令范围 | 说明 |
|:---|:---|:---|
| **系统管理** | `0x00-0x0F` | PING、设备信息、配置读写、复位、流控、拓扑查询、启动事件 |
| **CAN / CAN FD** | `0x10-0x1F` | 通道开关、波特率配置（仲裁段 + FD 数据段）、收发帧（≤64 B）、滤波器、总线状态 |
| **SPI** | `0x20-0x2F` | 设备开关、模式/时钟/位序配置、全双工传输、半双工只写/只读、手动 CS 控制 |
| **I2C** | `0x30-0x3F` | 总线开关、速率配置（100k/400k/1M）、7/10 位地址读写、组合写-读（repeated start）、总线扫描 |
| **网络配置** | `0x40-0x4F` | DHCP/静态 IP、状态查询、DNS 解析、链路事件上报、全局连接列表 |
| **TCP** | `0x50-0x5F` | Server 开关（最多 4）、Client 连接/断开（最多 16）、收发/接入事件、list/kick/conn-status |
| **UDP** | `0x60-0x6F` | Server 开关（最多 4）、Client 创建/删除（最多 8）、经 Server/Client 发包、接收事件 |
| **WebSocket** | `0x70-0x7F` | Server 开关（最多 4，16 连接）、Client 连接/断开、发送（文本/二进制）、收发/接入/ping-pong 事件、list/kick |
| **GPIO** | `0x80-0x8F` | 引脚方向、输出/输入、上下拉、中断使能与触发配置、掩码写入、全量读取 |
| **批量传输** | `0x90-0x9F` | 开始/停止批量会话、数据帧传输（滑动窗口 ACK/NACK + 重传） |
| **UART 扩展** | `0xA0-0xAF` | 串口开关、参数配置（波特率/数据位/校验/流控）、数据发送、4 种接收模式、Break、flush、状态 |
| **OTA** | `0xB0-0xBF` | 开始（SHA-256）、数据块 CRC Chunk 校验、结束与校验、进度查询、回滚 |

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
| **传输层 (MCP)** | ✅ 完成 | UART1 115200 bps 收发与帧组装 |
| **系统管理 (0x00-0x0F)** | ✅ 基础 | PING、GET_INFO、GET/SET_CONFIG、RESET、FLOW_CONTROL、SYS_BOOT_EVENT、TOPOLOGY |
| **UART 扩展 (0xA0-0xAF)** | ✅ 完整 | 全部 8 条命令，57 条用例 — 57/57 PASS |
| **网络 (0x40-0x7F)** | Wi-Fi STA | DHCP、静态 IPv4、DNS 和 UART1 配网。[网络规约](files/design/protocol/08-Network.md) |
| 　 ├─ 网络配置 (0x40-0x4F) | ✅ | NET_CONFIG、NET_STATUS、NET_DNS、NET_LINK_EVENT、NET_LIST_CONNS |
| 　 ├─ TCP (0x50-0x5F) | ✅ | 12 条命令：Server/Client、select() 事件循环、list/kick/conn-status |
| 　 ├─ UDP (0x60-0x6F) | ✅ | 7 条命令：Server/Client、select() 事件循环 |
| 　 └─ WebSocket (0x70-0x7F) | ✅ | 10 条命令：WS 帧编解码、SHA-1 握手、list/kick |
| **CAN / CAN FD** | ✅ 完整 | MCP2518FD (SPI, 20MHz 晶振), 12 条命令 — PCAN 104/0/23, CANable 98/0/1, 手动 43/0/0 |
| **SPI** | ☐ 待实现 | — |
| **I2C** | ☐ 待实现 | 24C02 EEPROM，引脚已分配 |
| **GPIO** | ☐ 待实现 | — |
| **批量传输** | ☐ 待实现 | — |
| **OTA** | ☐ 待实现 | 双分区 + SHA-256 校验 |

---

## CAN / CAN FD 模块

### 实现

MCP2518FD CAN FD 控制器经 SPI（10 MHz, Mode 0）驱动，外接 20 MHz 晶振（系统时钟 20 MHz，禁用 PLL）。完整覆盖协议规范 `files/design/protocol/04-CAN.md` 全部命令：

| 命令 | 命令码 | 说明 |
|:---|:---|:---|
| CAN_OPEN | `0x10` | 打开通道（正常 / 只听 / 环回模式） |
| CAN_CLOSE | `0x11` | 关闭通道（先排空 TX） |
| CAN_CONFIG | `0x12` | 波特率配置：仲裁段 10k–1M、FD 数据段 1M–5M、自定义 Mode-B 时序 |
| CAN_SEND | `0x13` | 发送经典 / CAN FD / BRS / RTR 帧（≤64 B） |
| CAN_RECV | `0x14` | 接收事件（异步）含 RxFlags 与时间戳 |
| CAN_FILTER | `0x15` | 单个过滤器（标准 / 扩展 / 两者） |
| CAN_STATUS | `0x16` | 总线状态、TEC/REC、队列占用、错误计数 |
| CAN_BUS_EVENT | `0x17` | 总线状态变化事件（正常/被动/离线） |
| CAN_ERROR_EVENT | `0x18` | 错误帧详情（CRC/格式/ACK/位/填充）— 500 ms 限速 |
| CAN_SLEEP | `0x19` | 进入休眠 |
| CAN_WAKEUP | `0x1A` | 唤醒并恢复模式 |
| CAN_FILTER_BATCH | `0x1B` | 批量配置过滤器 |

### 测试覆盖

| 测试套件 | 结果 | 说明 |
|:---|:---|:---|
| PCAN-USB（`test_can.py --phase 0`） | **104 PASS / 0 FAIL / 23 SKIP** | 94 用例（Phase 1: 12 + Phase 2: 82）；SKIP 为 FD（PCAN 经典）与需手动干预用例 |
| CANable 2.0（`test_canable.py`） | **98 PASS / 0 FAIL / 1 SKIP** | 经典 + CAN FD（64B、BRS、DLC 映射）；SKIP = canable2 slcan 不转发 FD+BRS 接收帧 |
| 手动（总线断开，`test_can.py --phase 3`） | **43 PASS / 0 FAIL / 0 SKIP** | 错误事件、TX 队列满、OneShot、休眠/唤醒、只听禁止发送 |

测试报告：`files/design/test-report/CAN-Test-Report.md`

---

固件版本 `0.1.0`，型号 `HXB1`，目标芯片 `esp32`。
