# HEX-Bridge UART MCP 测试 — 测试报告

> **测试日期**: 2026-07-12 | **固件版本**: v0.1.0 | **被测设备**: HXB1 (SN: 2F8F8288)

---

## 1. 测试概要

| 项目 | 值 |
|:---|:---|
| 被测模块 | MCP Serial Monitor 分屏通信 (HEX-Bridge 透明桥接) |
| 测试用例数 | 12 |
| 测试结果 | **9 PASS / 3 FAIL / 0 SKIP** |
| 测试方式 | MCP 工具直接调用 (Serial Monitor 插件) |
| 芯片型号 | ESP32-D0WD-V3 (revision v3.1) |
| IDF 版本 | ESP-IDF v6.0.1 |

---

## 2. 测试环境

### 2.1 硬件连接

```
┌──────────────────────────────────────┐
│       MCP Serial Monitor (分屏)       │
│                                      │
│  instanceId=1            instanceId=2│
│  COM_HEXBRIDGE:COM35:CH1   COM24     │
│  (HEX-Bridge 虚拟端口)     (物理串口)  │
│  115200 bps               115200 bps │
└──────────┬───────────────────┬───────┘
           │                   │
    UBCP 透明封装          物理串口直连
           │                   │
           ▼                   ▼
   ┌───────────────┐   ┌─────────────┐
   │  HEX-Bridge    │   │ CH340 回环   │
   │  ESP32         │   │ (外部设备)   │
   │               │   │             │
   │ UART1 (GP4/34)│   └──────┬──────┘
   │  ← MCP 通信 →  │         │
   │ UART2 (GP32/35)│── TX/RX ┘
   │  扩展口         │
   └───────────────┘
```

> **注**: COM35 是 HEX-Bridge 虚拟端口 (`COM_HEXBRIDGE:COM35:CH1`)，非物理串口。由 Serial Monitor 插件创建，UBCP v2.0 协议在用户端透明不可见。

### 2.2 串口分配

| 串口 | 类型 | 用途 | 参数 |
|:---|:---|:---|:---|
| `COM_HEXBRIDGE:COM35:CH1` | 虚拟 | HEX-Bridge 桥接端 (instanceId=1) | 115200, 8N1 |
| COM24 | 物理 (CH340) | UART2 扩展口监控 (instanceId=2) | 115200, 8N1 |

### 2.3 软件环境

| 组件 | 说明 |
|:---|:---|
| Serial Monitor 插件 | 内置 MCP 工具 + HEX-Bridge 集成 |
| 协议 | UBCP v2.0 (插件透明处理) |
| 外部设备 | CH340 USB-UART 回环 (COM24) |

---

## 3. 测试结果汇总

| 编号 | 用例名称 | 结果 | 关键数据 |
|:---|:---|:---|:---|
| MCP-01 | 设备发现 | ✅ PASS | 发现 1 设备: HXB1, SN=2F8F8288, fw=v0.1.0 |
| MCP-02 | 设备信息 | ✅ PASS | model=HXB1, protoVersion=2, maxPayload=2048 |
| MCP-03 | 分屏初始化 | ✅ PASS | 两个实例均 connected |
| MCP-04 | string 发送 → COM24 | ✅ PASS | "Hello"(5B) → COM24 正确接收 |
| MCP-05 | hex 发送 → COM24 | ✅ PASS | `01 02 03 FF 00`(5B) → COM24 正确接收 (含边界值) |
| MCP-06 | COM24 注入 → 桥接接收 | ❌ FAIL | "World" 注入硬件层接收, 但 `read_serial_buffer` RX 为空 |
| MCP-07 | 双向回环 PING/PONG | ❌ FAIL | 正向 PASS ("PING"→COM24), 反向 FAIL (PONG 未显示) |
| MCP-08 | 256 字节大数据块 | ✅ PASS | 256B 分 8 块接收 (32B×8), 00→FF 递增无丢 |
| MCP-09 | 实例独立性 | ✅ PASS | COM24 关闭/重开后 COM35 仍 connected |
| MCP-10 | 状态统计验证 | ✅ PASS | COM35 tx=286, COM24 rx=272/tx=24 |
| MCP-11 | Break 信号 | ✅ PASS | 50ms Break 发送成功, 设备恢复正常 |
| MCP-12 | Flush 缓冲区 | ✅ PASS | RX flush 执行成功, statusCode=0 |

---

## 4. 分项测试详情

### 4.1 MCP-01: 设备发现

```
serial-monitor-mcp_hex_bridge_discover
```

**结果**: 发现 1 个设备

| 字段 | 值 |
|:---|:---|
| mcpPort | COM35 |
| virtualPath | COM_HEXBRIDGE:COM35:CH1 |
| modelId | HXB1 |
| serialNum | 2F8F8288 |
| fwVersion | 0.1.0 |
| protoVersion | 2 |
| capabilities | 4095 |
| maxPayload | 2048 |

---

### 4.2 MCP-02: 设备信息

```
serial-monitor-mcp_hex_bridge_device_info
  port: "COM_HEXBRIDGE:COM35:CH1"
```

**结果**: 返回字段与 discover 一致，字段完整无缺失。

---

### 4.3 MCP-03: 分屏初始化

| 实例 | 端口 | 状态 |
|:---|:---|:---|
| instanceId=1 | COM_HEXBRIDGE:COM35:CH1 | connected |
| instanceId=2 | COM24 | connected |

---

### 4.4 MCP-04: string 发送 ("Hello")

| 方向 | 端口 | 数据 | 时间戳 |
|:---|:---|:---|:---|
| TX | COM_HEXBRIDGE:COM35:CH1 | "Hello" | 1783843618375 |
| RX | COM24 | "Hello" | 1783843618474 |

**延迟**: ~99ms (发送 → 接收)。

---

### 4.5 MCP-05: hex 发送 (含边界值 0x00, 0xFF)

| 方向 | 端口 | 数据 |
|:---|:---|:---|
| TX | COM_HEXBRIDGE:COM35:CH1 | `01 02 03 FF 00` |
| RX | COM24 | `01 02 03 FF 00` |

**验证**: 首尾字节 0x00、0xFF 均无损传递。

---

### 4.6 MCP-06: COM24 注入 → 桥接接收 ❌ FAIL

| 阶段 | 操作 | 结果 |
|:---|:---|:---|
| 注入 "World" (1st) | COM24 → UART2 | `hex_bridge_uart_status.rxTotal` 0→5 |
| 注入 "World" (2nd) | COM24 → UART2 | `hex_bridge_uart_status.rxTotal` 5→10 |
| 读取 COM_HEXBRIDGE:COM35:CH1 RX | `read_serial_buffer` dir=rx | **空数组 `[]`** |

**根因分析**: `hex_bridge_uart_status` 查询的是 ESP32 UART 硬件层环形缓冲区计数器，硬件确实收到了数据。但 `read_serial_buffer` 显示的是 UBCP `UART_RECV (0xAE)` 事件解封后的数据。

固件代码 `mod_uart.c` 中，`rx_count` 递增加 `send_recv_event()` 调用仅在 RX 任务内部执行。RX 任务由 `start_rx_task()` 创建，`start_rx_task()` 仅在 `handle_uart_open()` 中被调用——即**必须显式发送 `UART_OPEN (0xA0)` 命令**才会启动 RX 任务。

Serial Monitor 插件打开 hex-bridge 虚拟端口时，发送了 `UART_OPEN` 命令（因为 `hex_bridge_send_break` 和 `hex_bridge_flush` 的 `statusCode=0` 表明固件侧 `is_open=true`），但 **RX 任务可能未启动、或已崩溃、或 `UART_RECV` 事件未被插件转发到 `read_serial_buffer`**。

**判定**: **FAIL** — `read_serial_buffer` RX 方向无法获取接收数据，用户端不可见。

---

### 4.7 MCP-07: 双向回环 ❌ FAIL

| 阶段 | 方向 | 操作 | 结果 |
|:---|:---|:---|:---|
| 正向 | COM35 → COM24 | hex-bridge 发送 "PING" | ✅ COM24 收到 "PING" (txTotal 15→19) |
| 反向 | COM24 → COM35 | COM24 注入 "PONG" | ❌ `read_serial_buffer` 无 RX 数据 |

**判定**: **FAIL** — 正向通路正常，反向通路不可用（同 MCP-06 根因）。

---

### 4.8 MCP-08: 256 字节大数据块

COM24 分 8 个 32 字节数据包接收:

| 块 | 范围 | 字节数 | 顺序 |
|:---|:---|:---|:---|
| 1 | 0x00–0x1F | 32 | ✅ |
| 2 | 0x20–0x3F | 32 | ✅ |
| 3 | 0x40–0x5F | 32 | ✅ |
| 4 | 0x60–0x7F | 32 | ✅ |
| 5 | 0x80–0x9F | 32 | ✅ |
| 6 | 0xA0–0xBF | 32 | ✅ |
| 7 | 0xC0–0xDF | 32 | ✅ |
| 8 | 0xE0–0xFF | 32 | ✅ |

**总计**: 256 字节完整无丢，顺序无错乱。

---

### 4.9 MCP-09: 实例独立性

| 操作 | 结果 |
|:---|:---|
| 关闭 COM24 (instanceId=2) | COM35 仍 connected |
| hex-bridge 发送 "test-after-close"(16B) | 发送成功, tx 增加 |
| 重新打开 COM24 | connected |
| hex_bridge_uart_status | 正常, txTotal=291, rxTotal=14, 无错误 |

---

### 4.10 MCP-10: 状态统计

| 端口 | isOpen | rx | tx |
|:---|:---|:---|:---|
| COM_HEXBRIDGE:COM35:CH1 | true | 0 | 286 |
| COM24 | true | 272 | 24 |

| UART2 指标 | 值 |
|:---|:---|
| baudRate | 115200 |
| txTotal | 291 |
| rxTotal | 24 |
| errorCount | 0 |
| txBufUsed | 28 (未排空) |

---

### 4.11 MCP-11: Break 信号

```
serial-monitor-mcp_hex_bridge_send_break
  port: "COM_HEXBRIDGE:COM35:CH1"
  durationMs: 50
```

**结果**: statusCode=0, 设备正常恢复, 无错误计数增加。

---

### 4.12 MCP-12: Flush 缓冲区

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "rx"
```

**结果**: statusCode=0, 执行成功。

---

## 5. 已知行为与限制

| 项目 | 说明 |
|:---|:---|
| COM35 为虚拟端口 | 物理串口列表中不出现 COM35，需通过 `hex_bridge_discover` 获取虚拟路径 `COM_HEXBRIDGE:COM35:CH1` 进行操作 |
| **RX 通路不可用** | `read_serial_buffer` 在 hex-bridge 虚拟端口仅返回 TX 方向数据。RX 方向数据虽被硬件接收（`rxTotal` 递增），但不产生 `UART_RECV` 事件或事件未被插件转发显示 |
| txBufUsed 残留 | 测试结束后 txBufUsed=28，UART2 发送缓冲区有未排空数据，可能是 115200→CH340 回环造成的拥塞积累 |
| flush 前端口验证 | `hex_bridge_flush` 需要端口以 hex-bridge 模式打开才可调用，直接打开物理 COM35 无效 |

---

## 6. FAIL 用例根因分析

### MCP-06 / MCP-07: 扩展口→桥接 RX 通路失效

**固件侧分析** (`main/modules/mod_uart.c`):

```
uart_module_init()          → 仅打印日志，不做硬件初始化
handle_uart_open()          → uart_driver_install() + uart_param_config() +
                               uart_set_pin() + start_rx_task()
send_recv_event()           → 仅在 RX 任务 (rx_task_passive/line/fixed/timeout) 内调用
```

RX 任务 (`rx_task_passive` 等) 是产生 `UART_RECV (0xAE)` 事件的唯一入口。RX 任务的 `rx_count` 递增和 `send_recv_event()` 调用均在任务循环内，而任务仅在 `handle_uart_open()` → `start_rx_task()` 时创建。

Serial Monitor 插件打开 hex-bridge 虚拟端口时，`hex_bridge_send_break` 和 `hex_bridge_flush` 返回 `statusCode=0` 表明固件侧 `is_open=true`（这些命令内部有 `if (!s_channel.is_open) return ERR_NOT_OPEN` 检查），所以 `UART_OPEN` 命令确实已被发送。

**可能原因** (按可能性排序):

1. **RX 任务未启动**: 插件发送 UART_OPEN 后任务启动失败（栈溢出 / 优先级冲突），日志见于 UART0 (COM34) 调试输出
2. **RX 任务已崩溃**: 任务启动后被异常终止，`rx_running` 变为 false，不再产生事件
3. **插件未处理 UART_RECV 事件**: 固件正常产生 `UART_RECV` 事件帧，但 Serial Monitor 插件内部未将其解封到 `read_serial_buffer` 的 RX 缓冲区

**建议排查**: 检查 COM34 (UART0 调试串口) 输出，搜索 `rx_running` / `ESP_ERR_NO_MEM` / 栈溢出相关日志。

---

## 7. 文件清单

### 6.1 测试用例

| 文件 | 说明 |
|:---|:---|
| `files/design/test/04-UART-MCP-Tests.md` | 测试用例规范 (12 用例) |

### 6.2 测试报告

| 文件 | 说明 |
|:---|:---|
| `files/design/test-report/UART-MCP-Test-Report.md` | **本报告** |

---

## 8. 结论

HEX-Bridge 透明桥接的 **正向 (用户→外设) 数据通路**在 MCP Serial Monitor 分屏模式下运行正常：设备发现、分屏初始化、数据发送 (string/hex/256B)、实例独立性、Break 和 Flush 均通过。

**反向 (外设→用户) 数据通路不工作**：COM24 注入的数据在硬件层被 UART2 接收（`rxTotal` 递增确认），但 `read_serial_buffer` 的 RX 方向无数据显示。根因为固件 RX 任务未启动或 Serial Monitor 插件未转发 `UART_RECV` 事件。

**9 PASS / 3 FAIL / 0 SKIP** — 核心发送通路完整可用，接收通路需修复。

### 通过的用例 (9)

| 编号 | 功能 |
|:---|:---|
| MCP-01 | 设备发现 |
| MCP-02 | 设备信息 |
| MCP-03 | 分屏双串口打开 |
| MCP-04 | string 格式桥接发送 |
| MCP-05 | hex 格式桥接发送 (含 0x00/0xFF 边界) |
| MCP-08 | 256 字节大数据块完整传输 |
| MCP-09 | 实例独立性 |
| MCP-10 | 状态统计 |
| MCP-11 | Break 信号发送 |
| MCP-12 | Flush 缓冲区清空 |

### 失败的用例 (3)

| 编号 | 根因 |
|:---|:---|
| MCP-06 | COM24 注入 → `read_serial_buffer` RX 为空 |
| MCP-07 | 反向 PONG 通路不可用 (同 MCP-06 根因) |
| MCP-10 | 收到数据但用户不可见 (rxTotal=24, read_serial_buffer rx=0) |

### 下一步建议

1. **查看 COM34 调试日志** — 搜索 `start_rx_task` / `rx_running` / 栈溢出信息
2. **手动触发 UART_OPEN** — 通过 COM35 直接发送 UBCP `UART_OPEN (0xA0)` 帧验证 RX 任务能否正常启动
3. **确认插件行为** — 验证 Serial Monitor 插件在打开 hex-bridge 虚拟端口时是否自动发送 `UART_OPEN`，以及 `UART_RECV` 事件是否被正确转发
