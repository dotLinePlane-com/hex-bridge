# HEX-Bridge 测试用例

> 固件功能验证的黑盒集成测试用例，通过 MCP 通信口（UART1, 921600 bps）发�?UBCP v2.0 帧进行测试�?
---

## 测试拓朴

```
┌──────────────�?                ┌─────────────────�?�?  PC (COM4) │── MCP/UBCP ────→│   HEX-Bridge     �?�? 测试客户�?  �?  921600 bps   �?  ESP32          �?�?             │←── MCP/UBCP ────�?  UART1 (GP4/34) �?└──────────────�?                �?                 �?                                 �? UART2 (GP32/35) �?┌──────────────�?                �?  115200/8N1     �?�?  PC (COM3) │──── 串口 ──────→│   (扩展�?       �?�? 监控/注入    �?                └────────┬─────────�?└──────────────�?                         �?TX/RX
                                          �?                                 ┌─────────────────�?                                 �? 外部串口设备     �?                                 �? (被测外设)      �?                                 └─────────────────�?
COM5: ESP32 调试日志输出 (UART0, 115200 bps)
```

**数据流说�?*:

| 方向 | 路径 |
|:---|:---|
| MCP 命令 | PC(COM4) �?UART1 �?HEX-Bridge |
| MCP 响应/事件 | HEX-Bridge �?UART1 �?PC(COM4) |
| UART_SEND 数据 | PC(COM4) �?MCP �?HEX-Bridge �?UART2 �?外部设备 |
| UART_RECV 事件 | 外部设备 �?UART2 �?HEX-Bridge �?MCP �?PC(COM4) |
| 监控 UART2 �?| PC(COM3) 直接监听外部设备�?|
| 注入外部数据 | PC(COM3) 模拟外部设备�?UART2 发数�?|

---

## 测试环境

| 项目 | 要求 |
|:---|:---|
| 被测设备 | HEX-Bridge (ESP32, 固件 v0.2.0) |
| MCP 通信�?| COM4, UART1 (GPIO4 TX / GPIO34 RX), 921600 bps, 8N1 |
| 扩展�?| COM3, UART2 (GPIO32 TX / GPIO35 RX), 默认 115200 bps, 8N1 |
| 调试输出 | COM5, UART0 (GPIO1 TX / GPIO3 RX), 115200 bps |
| 协议版本 | UBCP v2.0 (`0x02`) |
| 外部设备 | 已连�?UART2 的外部串口设�?|

## 串口分配

| 串口 | 用�?| 参数 |
|:---|:---|:---|
| COM4 | MCP 通信 | 921600 bps, 8N1, 无流�?|
| COM3 | 扩展口监�?注入 | 与外部设备匹配的波特�?|
| COM5 | 调试输出 | 115200 bps, 8N1 |

---

## 测试脚本

COM4 �?COM3 均由 `pyserial` 库直接控制，脚本独立运行�?
```bash
python script/test/test_uart.py --COM3 COM3 --ext-baud 115200
```

| 脚本 | 说明 |
|:---|:---|
| `script/test/test_uart.py` | UART 模块测试 (57 用例, UART-01 ~ UART-57) |
| `script/test/test_network.py` | 网络模块测试 (67 用例, DRV/TCP/UDP/WS/STRESS) |
| `script/test/test_can.py` | CAN 模块测试 — Phase 1: PCAN 独立验证 / Phase 2: MCP 集成 (待 MCP 支持) |
| `script/test/ubcp_client.py` | UBCP v2.0 帧构建/解析库 |
| `script/test/mcp_transport.py` | COM4 串口传输封装 (921600 bps) |
| `script/test/pcan_basic.py` | PCANBasic.dll ctypes 封装 (CAN 2.0 + CAN FD) |

---

## 前置条件

1. 固件已烧录并运行
2. 外部串口设备已连接到 HEX-Bridge UART2
3. COM3 已连接到外部设备侧（监控 UART2 数据流通）
4. 测试前必须完�?**握手流程**�?   - 通过 COM4 发�?`PING (0x00)` �?确认设备在线
   - 通过 COM4 发�?`GET_INFO (0x01)` �?确认设备身份和版�?
## 测试分类

| 文档 | 范围 | 用例�?| 状�?|
|:---|:---|:---|:---|
| [01-System-Tests.md](01-System-Tests.md) | 系统管理 (PING, GET_INFO, GET/SET_CONFIG, RESET, FLOW_CONTROL, SYS_BOOT_EVENT) | 9 | �?已实�?|
| [02-UART-Tests.md](02-UART-Tests.md) | UART 扩展模块 (0xA0-0xAF) 全部 8 命令 + 流控 | 57 | �?57/57 PASS |
| [03-Protocol-Tests.md](03-Protocol-Tests.md) | 帧协议层 (转义/CRC/边界) | 8 | 待验�?|
| [04-UART-MCP-Tests.md](04-UART-MCP-Tests.md) | MCP Serial Monitor 分屏通信 (hex-bridge 透明桥接) | 12 | 待验�?|
| [09-Network-Tests.md](09-Network-Tests.md) | 以太网 TCP/UDP/WebSocket 模块 | 80 | 70/70 PASS (auto) |
| [05-CAN-Tests.md](05-CAN-Tests.md) | CAN FD 模块 (Phase 1: 12 + Phase 2: 72) | 84 | ✅ 脚本已实现 |

## 帧构建约�?
测试用例中的 Payload 使用 hex 编码（如 `0x00` 表示字节�?0），帧字节序均为**大端**�?
### 请求帧模�?(主机 �?设备)

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

### 响应帧模�?(设备 �?主机)

```
SOF: 0xAA 0x55
Header (10B):
  Version  : 0x02
  Flags    : 0x80 (DIR=1)
  SeqNum   : <回填请求�?SeqNum>
  CmdCode  : <回填请求�?CmdCode>
  ChannelID: <回填请求�?ChannelID>
  PayloadLen: <2B, 大端>
Payload  : <NB, 首字节为 Status>
CRC16    : <2B>
EOF      : 0x7E
```

### 事件帧模�?(设备 �?主机)

```
Flags: 0x90 (DIR=1, EVT=1)
SeqNum: 设备独立递增
```

## 判定标准

| 级别 | 说明 |
|:---|:---|
| **PASS** | 响应完全匹配预期（状态码、载荷字段值与协议规范一致） |
| **FAIL** | 未收到响应、帧解析失败、状态码错误、载荷字段值与预期不符 |
| **N/A**  | 环境不具备或功能未实�?|

## 设备端自检

| 测试�?| 所需硬件 |
|:---|:---|
| UART_OPEN/CONFIG/FLUSH/STATUS | �?|
| UART_SEND 数据发�?| 外部串口设备已连接；可在 COM3 监控发送内�?|
| UART_RECV 数据接收 | 外部设备主动发送数据，�?PC(COM3) 注入模拟 |
| UART_SET_BREAK | 外部设备需支持 Break 检测，或通过 COM3 可观察到 RX 断线 |
| UART 错误检�?(Parity/Frame) | PC(COM3) 以错误波特率/校验位发�?|
