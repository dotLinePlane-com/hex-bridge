# HEX-Bridge 测试用例

> 固件功能验证的黑盒集成测试用例，通过 MCP 通信口（UART1, 921600 bps）发送 UBCP v2.0 帧进行测试。

---

## 测试拓朴

```
┌──────────────┐                 ┌─────────────────┐
│   PC (COM35) │── MCP/UBCP ────→│   HEX-Bridge     │
│  测试客户端   │   921600 bps   │   ESP32          │
│              │←── MCP/UBCP ────│   UART1 (GP4/34) │
└──────────────┘                 │                  │
                                 │  UART2 (GP32/35) │
┌──────────────┐                 │   115200/8N1     │
│   PC (COM24) │──── 串口 ──────→│   (扩展口)       │
│  监控/注入    │                 └────────┬─────────┘
└──────────────┘                          │ TX/RX
                                          ▼
                                 ┌─────────────────┐
                                 │  外部串口设备     │
                                 │  (被测外设)      │
                                 └─────────────────┘

COM34: ESP32 调试日志输出 (UART0, 115200 bps)
```

**数据流说明**:

| 方向 | 路径 |
|:---|:---|
| MCP 命令 | PC(COM35) → UART1 → HEX-Bridge |
| MCP 响应/事件 | HEX-Bridge → UART1 → PC(COM35) |
| UART_SEND 数据 | PC(COM35) → MCP → HEX-Bridge → UART2 → 外部设备 |
| UART_RECV 事件 | 外部设备 → UART2 → HEX-Bridge → MCP → PC(COM35) |
| 监控 UART2 发 | PC(COM24) 直接监听外部设备侧 |
| 注入外部数据 | PC(COM24) 模拟外部设备向 UART2 发数据 |

---

## 测试环境

| 项目 | 要求 |
|:---|:---|
| 被测设备 | HEX-Bridge (ESP32, 固件 v0.2.0) |
| MCP 通信口 | COM35, UART1 (GPIO4 TX / GPIO34 RX), 921600 bps, 8N1 |
| 扩展口 | COM24, UART2 (GPIO32 TX / GPIO35 RX), 默认 115200 bps, 8N1 |
| 调试输出 | COM34, UART0 (GPIO1 TX / GPIO3 RX), 115200 bps |
| 协议版本 | UBCP v2.0 (`0x02`) |
| 外部设备 | 已连接 UART2 的外部串口设备 |

## 串口分配

| 串口 | 用途 | 参数 |
|:---|:---|:---|
| COM35 | MCP 通信 | 921600 bps, 8N1, 无流控 |
| COM24 | 扩展口监控/注入 | 与外部设备匹配的波特率 |
| COM34 | 调试输出 | 115200 bps, 8N1 |

---

## 测试脚本

COM35 和 COM24 均由 `pyserial` 库直接控制，脚本独立运行：

```bash
python script/test/test_uart.py --com24 COM24 --ext-baud 115200
```

| 脚本 | 说明 |
|:---|:---|
| `script/test/test_uart.py` | UART 模块测试 (57 用例, UART-01 ~ UART-57) |
| `script/test/test_network.py` | 网络模块测试 (67 用例, DRV/TCP/UDP/WS/STRESS) |
| `script/test/ubcp_client.py` | UBCP v2.0 帧构建/解析库 |
| `script/test/mcp_transport.py` | COM35 串口传输封装 (921600 bps) |

---

## 前置条件

1. 固件已烧录并运行
2. 外部串口设备已连接到 HEX-Bridge UART2
3. COM24 已连接到外部设备侧（监控 UART2 数据流通）
4. 测试前必须完成 **握手流程**：
   - 通过 COM35 发送 `PING (0x00)` → 确认设备在线
   - 通过 COM35 发送 `GET_INFO (0x01)` → 确认设备身份和版本

## 测试分类

| 文档 | 范围 | 用例数 |
|:---|:---|:---|
| [01-System-Tests.md](01-System-Tests.md) | 系统管理 (PING, GET_INFO, GET/SET_CONFIG, RESET, FLOW_CONTROL, SYS_BOOT_EVENT) | 9 |
| [02-UART-Tests.md](02-UART-Tests.md) | UART 扩展模块 (0xA0-0xAF) 全部 8 命令 + 流控 | 57 |
| [03-Protocol-Tests.md](03-Protocol-Tests.md) | 帧协议层 (转义/CRC/边界) | 8 |
| [04-UART-MCP-Tests.md](04-UART-MCP-Tests.md) | MCP Serial Monitor 分屏通信 (hex-bridge 透明桥接) | 12 |
| [09-Network-Tests.md](09-Network-Tests.md) | 以太网（LAN8720）+ TCP/UDP/WebSocket 模块 | 67 |

## 帧构建约定

测试用例中的 Payload 使用 hex 编码（如 `0x00` 表示字节值 0），帧字节序均为**大端**。

### 请求帧模板 (主机 → 设备)

```
SOF: 0xAA 0x55
Header (10B):
  Version  : 0x02
  Flags    : 0x40 (DIR=0, ACK=1)
  SeqNum   : <2B, 递增, 大端>
  CmdCode  : <1B>
  ChannelID: <1B>
  PayloadLen: <2B, 大端>
Payload  : <NB>
CRC16    : <2B, 大端>
EOF      : 0x7E
```

### 响应帧模板 (设备 → 主机)

```
SOF: 0xAA 0x55
Header (10B):
  Version  : 0x02
  Flags    : 0x80 (DIR=1)
  SeqNum   : <回填请求的 SeqNum>
  CmdCode  : <回填请求的 CmdCode>
  ChannelID: <回填请求的 ChannelID>
  PayloadLen: <2B, 大端>
Payload  : <NB, 首字节为 Status>
CRC16    : <2B>
EOF      : 0x7E
```

### 事件帧模板 (设备 → 主机)

```
Flags: 0x90 (DIR=1, EVT=1)
SeqNum: 设备独立递增
```

## 判定标准

| 级别 | 说明 |
|:---|:---|
| **PASS** | 响应完全匹配预期（状态码、载荷字段值与协议规范一致） |
| **FAIL** | 未收到响应、帧解析失败、状态码错误、载荷字段值与预期不符 |
| **N/A**  | 环境不具备或功能未实现 |

## 设备端自检

| 测试项 | 所需硬件 |
|:---|:---|
| UART_OPEN/CONFIG/FLUSH/STATUS | 无 |
| UART_SEND 数据发送 | 外部串口设备已连接；可在 COM24 监控发送内容 |
| UART_RECV 数据接收 | 外部设备主动发送数据，或 PC(COM24) 注入模拟 |
| UART_SET_BREAK | 外部设备需支持 Break 检测，或通过 COM24 可观察到 RX 断线 |
| UART 错误检测 (Parity/Frame) | PC(COM24) 以错误波特率/校验位发送 |
