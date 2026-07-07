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
| 被测设备 | HEX-Bridge (ESP32, 固件 v0.1.0) |
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

## 两种测试模式

### 模式 A: pyserial 直接测试 (原有脚本)

COM35 和 COM24 均由 `pyserial` 库直接控制，脚本独立运行：

```bash
python3 script/test/test_uart.py --com24 COM24 --ext-baud 115200
```

| 脚本 | 说明 |
|:---|:---|
| `script/test/test_uart.py` | pyserial 模式，COM24 直接读写 |

### 模式 B: Serial Monitor MCP 测试 (新脚本，`_mcp` 后缀)

**实际工作流程**:

1. 测试执行阶段 — pyserial 控制 COM24，执行全部 30 个用例
2. 操作记录 — 所有 COM24 写操作 + 文本标记写入 `%TEMP%/mcp24_replay.jsonl`
3. 结果展示 — 测试完成后 Kilo 打开 COM24 (MCP 工具)，通过 `serial-monitor-mcp_send_serial_data` 逐条重放标记
4. 用户可见 — Serial Monitor UI 显示完整测试流程（每个用例的步骤、注入数据、PASS/FAIL 结果）

```bash
# 独立运行（pyserial 回退模式，无需 MCP）
python3 script/test/test_uart_mcp.py --com24 COM24 --ext-baud 115200

# MCP 重放（Kilo 执行: 测试 → 重放标记到 UI）
kilo: serial-monitor-mcp_open COM24 → run test → replay markers → close
```

**IPC 桥接 (可选基础设施)**:

设置 `__MCP24_ACTIVE__=1` 后，COM24 操作通过文件管道 (`mcp24_req.txt`/`mcp24_res.txt`) 转发，Kilo 调用 MCP 工具执行。当前受 `bash` 同步限制，推荐使用上述重放模式。

```
┌──────────────────┐      IPC (文件管道)       ┌──────────────────┐
│  test_uart_mcp.py │ ──── mcp24_req.txt ────→ │   Kilo Agent      │
│  (COM35: pyserial) │ ←── mcp24_res.txt ──── │   (MCP 工具执行)   │
│  (COM24: MCP桥接)  │                          │                    │
└──────────────────┘                          └───────┬────────────┘
                                                     │
                                          ┌──────────▼────────────┐
                                          │ serial-monitor-mcp:   │
                                          │ open/send/read/close  │
                                          │ COM24 实时显示        │
                                          └───────────────────────┘
```

| 脚本 | 说明 |
|:---|:---|
| `script/test/mcp24_bridge.py` | COM24 桥接层: pyserial 模式 + MCP IPC 模式 + JSONL 操作日志 |
| `script/test/test_uart_mcp.py` | MCP 模式测试脚本，支持 pyserial 独立运行和 MCP IPC 模式 |

---

## 前置条件

1. 固件已烧录并运行
2. 外部串口设备已连接到 HEX-Bridge UART2
3. COM24 已连接到外部设备侧（监控 UART2 数据流通）
4. 测试前必须完成 **握手流程**：
   - 通过 COM35 发送 `PING (0x00)` → 确认设备在线
   - 通过 COM35 发送 `GET_INFO (0x01)` → 确认设备身份和版本
5. (MCP 模式) Serial Monitor 插件已安装，MCP 工具可用

## 测试分类

| 文档 | 范围 | 用例数 |
|:---|:---|:---|
| [01-System-Tests.md](01-System-Tests.md) | 系统管理 (PING, GET_INFO, GET/SET_CONFIG, RESET, FLOW_CONTROL) | 8 |
| [02-UART-Tests.md](02-UART-Tests.md) | UART 扩展模块 (0xA0-0xAF) 全部 8 命令 + 流控 | 30 |
| [03-Protocol-Tests.md](03-Protocol-Tests.md) | 帧协议层 (转义/CRC/边界) | 8 |

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
