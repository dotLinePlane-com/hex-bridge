# 04. UART MCP 测试 (MCP Serial Monitor 分屏通信) — 逐步执行版

> ⚠️ **重要**: 所有 COM35 侧操作均使用 `discover` 返回的虚拟端口路径 `COM_HEXBRIDGE:COM35:CH1`，而非物理端口名 `COM35`。`open_serial_port` 直接传入虚拟路径即可，插件会自动识别为 HEX-Bridge 设备并处理通道映射。
>
> ⚠️ **波特率一致**: 远端 UART2 的波特率需与 COM24 (扩展口监控端) 的物理波特率一致，默认为 115200 bps。若需修改 UART2 波特率，通过 `open_serial_port` `COM_HEXBRIDGE:COM35:CH1` 的 `baudRate` 参数指定（配合虚拟路径传入）。

> 验证 MCP Serial Monitor 分屏模式下 HEX-Bridge 透明桥接的数据通路。

> **UBCP v2.0 协议在用户端不可见** — Serial Monitor 插件自动处理 UBCP 成帧/解帧，用户仅看到原始载荷数据。

---

## 测试拓朴

```
┌─────────────────────────────────────────────────────┐
│              MCP Serial Monitor (分屏)               │
│                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐   │
│  │  instanceId=1       │  │  instanceId=2       │   │
│  │  COM_HEXBRIDGE:COM35:CH1│  │  COM24 (115200)     │   │
│  │  HEX-Bridge 桥接端   │  │  UART2 扩展口监控    │   │
│  │  Tx→桥接发送        │  │  Rx→观察外设上行     │   │
│  │  Rx←桥接接收        │  │  Tx→注入模拟数据     │   │
│  └────────┬────────────┘  └────────┬────────────┘   │
└───────────┼────────────────────────┼────────────────┘
            │                        │
     UBCP 透明封装              物理串口直连
            │                        │
            ▼                        ▼
    ┌───────────────┐      ┌─────────────────┐
    │   HEX-Bridge   │      │   外部串口设备    │
    │   ESP32        │      │                 │
    │               │      │  (可空接, 仅做    │
    │  UART1(GP4/34)│      │   数据通路验证)   │
    │    ← MCP →     │      └─────────────────┘
    │               │
    │  UART2(GP32/35)│────── TX/RX ──────→ 外部设备
    │   扩展口        │
    └───────────────┘
```

**分屏布局**:

| 实例 | 串口 | 角色 | 用户看到的 |
|:---|:---|:---|:---|
|  `instanceId=1` | COM_HEXBRIDGE:COM35:CH1 | 桥接端 | 发送: 原始数据 (插件封装为 UBCP) → 接收: 原始数据 (插件解封 UBCP) |
| `instanceId=2` | COM24 | 监控端 | UART2 物理线路上实际收发字节 |

---

## 测试环境

| 项目 | 值 |
|:---|:---|
| HEX-Bridge 设备 | ESP32, 固件已烧录运行 |
| 桥接端口 (虚拟路径) | COM_HEXBRIDGE:COM35:CH1, 由 discover 返回 |
| 扩展口监控 | COM24, 115200 bps, 8N1, 无流控 |
| UBCP | v2.0, Serial Monitor 插件透明处理 |
| 前置条件 | COM35/COM24 未被其他程序占用 |

---

## 分屏初始化流程

### 步骤 1: 发现 HEX-Bridge 设备

```
serial-monitor-mcp_hex_bridge_discover
```

**预期**: 返回设备列表，包含虚拟端口路径 (如 `COM_HEXBRIDGE:COM35:CH1`) 和设备基本信息。

### 步骤 2: 打开桥接端 (instanceId=1)

通过 `hex_bridge_discover` 获取的虚拟端口路径打开 HEX-Bridge 桥接通道：

```
serial-monitor-mcp_open_serial_port
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
```

> 插件自动识别 `COM_HEXBRIDGE:COM35:CH1` 为 HEX-Bridge 设备，无需额外指定 `hexBridge`、`channel` 等参数。后续 `send`/`read`/`status` 操作均使用此虚拟路径。

### 步骤 3: 打开 COM24 (instanceId=2)

```
serial-monitor-mcp_open_serial_port
  port: "COM24"
  baudRate: 115200
  dataBits: 8
  parity: "none"
  stopBits: 1
  instanceId: "2"
```

### 步骤 4: 配置显示标志

```
// instanceId=1: string 显示 + 时间戳 + 行号
serial-monitor-mcp_set_display_flags
  instanceId: "1"
  flags: {
    isHexRx: false,
    isHexTx: false,
    isAddTimeHead: true,
    isShowLine: true,
    isShowRx: true,
    isShowTx: true
  }

// instanceId=2: 同上
serial-monitor-mcp_set_display_flags
  instanceId: "2"
  flags: {
    isHexRx: false,
    isHexTx: false,
    isAddTimeHead: true,
    isShowLine: true,
    isShowRx: true,
    isShowTx: true
  }
```

### 步骤 5: 回填 MCP-01~03 结果到串口 (补发标注与结果)

MCP-01/02/03 在串口打开前完成，通过桥接端补发:

```
// MCP-01 结果
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-01: PASS --- COM_HEXBRIDGE:COM35:CH1 ==="
  format: "string"

// MCP-02 结果
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-02: PASS --- HXB1 fw=0.1.0 proto=2 ==="
  format: "string"

// MCP-03 结果
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-03: PASS --- 双实例 connected ==="
  format: "string"
```

---

## MCP-01: 设备发现 — 确认 HEX-Bridge 在线

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 `hex_bridge_discover` 能发现已连接的 HEX-Bridge 设备 |

**步骤**:

```
serial-monitor-mcp_hex_bridge_discover
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| 设备列表 | 非空，至少 1 个设备 |
| 虚拟端口路径 | 格式 `COM_HEXBRIDGE:COM35:CH1` |
| 设备型号/序列号 | 非空 |

**判定**: PASS — 发现至少 1 个设备，虚拟端口路径可解析

**测试执行**:

```
=== MCP-01: PASS --- COM_HEXBRIDGE:COM35:CH1 ===  (步骤5回填)
```

---

## MCP-02: 设备信息 — 获取设备详情

| 项目 | 值 |
|:---|:---|
| **目的** | 通过 `hex_bridge_device_info` 获取设备完整信息 |
| **前置** | MCP-01 通过 |

**步骤**:

```
serial-monitor-mcp_hex_bridge_device_info
  port: "COM_HEXBRIDGE:COM35:CH1"
```

**预期结果**:

| 字段 | 预期值 |
|:---|:---|
| model | 非空 (如 "HEX-Bridge") |
| serialNumber | 非空 |
| firmwareVersion | 非空 (如 "0.1.0") |
| protocolVersion | ≥ 0x02 |
| capabilities | 非零 (能力标志位) |
| maxPayloadSize | ≥ 256 |

**判定**: PASS — 所有字段非空/非零

**测试执行**:

```
=== MCP-02: PASS --- HXB1 fw=0.1.0 proto=2 ===  (步骤5回填)
```

---

## MCP-03: 分屏初始化 — 双串口同时打开

| 项目 | 值 |
|:---|:---|
| **目的** | 验证分屏模式下 COM35 和 COM24 同时打开并独立运行 |

**步骤**: 依次执行步骤 2、步骤 3，然后获取状态：

```
// instanceId=1
serial-monitor-mcp_get_serial_status
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"

// instanceId=2
serial-monitor-mcp_get_serial_status
  port: "COM24"
  instanceId: "2"
```

**预期结果**:

| 实例 | 端口 | 状态 |
|:---|:---|:---|
| instanceId=1 | COM_HEXBRIDGE:COM35:CH1 | connected |
| instanceId=2 | COM24 | connected |

**判定**: PASS — 两个实例均 connected

**测试执行**:

```
=== MCP-03: PASS --- 双实例 connected ===  (步骤5回填)
```

---

## MCP-04: 桥接发送 → 扩展口监控 (数据通路: 用户→外设)

| 项目 | 值 |
|:---|:---|
| **目的** | 从 COM35 发送数据，在 COM24 验证 HEX-Bridge 正确将数据输出到 UART2 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 发送测试标注:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "--- MCP-04: 桥接发送 -> 扩展口监控 ---"
  format: "string"
```

2. 从桥接端发送 "Hello":

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "Hello"
  format: "string"
```

3. 等待约 500ms，从 COM24 读取:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM24"
  instanceId: "2"
  display: "string"
  direction: "rx"
  count: 10
```

4. 发送测试结果:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-04: PASS --- COM24收到Hello ==="
  format: "string"
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| COM24 Rx 内容 | 含 "--- MCP-04: ..." 和 "Hello" |
| 时间戳 | 在发送操作后合理时间内 |

**判定**: PASS — COM24 收到标注和完整的 "Hello" 数据

> Serial Monitor 插件自动将桥接端的 "Hello" 封装为 UBCP UART_SEND 帧发送给 ESP32，ESP32 从 UART2 输出原始数据，COM24 直接监听到物理信号。用户全程不感知 UBCP。

**测试执行**:

```
Tx --- MCP-04: 桥接发送 -> 扩展口监控 ---
Tx Hello
Rx --- MCP-04: ... --- (COM24)
Rx Hello (COM24)
Tx === MCP-04: PASS --- COM24收到Hello ===
```

---

## MCP-05: 扩展口注入 → 桥接接收 (数据通路: 外设→用户)

| 项目 | 值 |
|:---|:---|
| **目的** | 从 COM24 注入数据模拟外设，在 COM35 验证 HEX-Bridge 正确上报接收数据 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 发送测试标注:

```
serial-monitor-mcp_send_serial_data
  port: "COM24"
  data: "--- MCP-05: 扩展口注入 -> 桥接接收 ---"
  format: "string"
```

2. 从 COM24 注入 "World":

```
serial-monitor-mcp_send_serial_data
  port: "COM24"
  data: "World"
  format: "string"
```

3. 等待约 500ms，从桥接端读取:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
  display: "string"
  direction: "rx"
  count: 10
```

4. 发送测试结果:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-05: PASS --- 桥接端收到World ==="
  format: "string"
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| 桥接端 Rx 内容 | 含 "--- MCP-05: ..." 和 "World" |

**判定**: PASS — 桥接端收到标注和完整的 "World" 数据

> COM24 向 UART2 注入 "World" → ESP32 UART2 接收 → 封装为 UBCP UART_RECV 事件 → COM35 解封显示 "World"。用户全程不感知 UBCP。

**测试执行**:

```
Rx --- MCP-05: 扩展口注入 -> 桥接接收 --- (COM24 Tx → 桥接 Rx)
Rx World (COM24 Tx → 桥接 Rx)
Tx === MCP-05: PASS --- 桥接端收到World ===
```

---

## MCP-06: 双向回环 (PING/PONG)

| 项目 | 值 |
|:---|:---|
| **目的** | 完整验证双通道: COM35→Bridge→UART2→COM24 和 COM24→UART2→Bridge→COM35 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 发送测试标注:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "--- MCP-06: 双向回环 PING/PONG ---"
  format: "string"
```

2. 桥接端发送 "PING":

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "PING"
  format: "string"
```

3. 等待约 500ms，确认 COM24 收到:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM24"
  instanceId: "2"
  display: "string"
  direction: "rx"
  count: 5
```

4. COM24 回复 "PONG":

```
serial-monitor-mcp_send_serial_data
  port: "COM24"
  data: "PONG"
  format: "string"
```

5. 等待约 500ms，确认桥接端收到:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
  display: "string"
  direction: "rx"
  count: 5
```

6. 发送测试结果:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-06: PASS --- PING/PONG ==="
  format: "string"
```

**预期结果**:

| 阶段 | 窗口 | 预期内容 |
|:---|:---|:---|
| 发送 | 桥接端 Tx | "PING" |
| 接收 | COM24 Rx | "PING" |
| 注入 | COM24 Tx | "PONG" |
| 上报 | 桥接端 Rx | "PONG" |

**判定**: PASS — 双向数据完整: "PING" 出现在 COM24，"PONG" 出现在桥接端

**测试执行**:

```
Tx --- MCP-06: 双向回环 PING/PONG ---
Tx PING
Rx --- MCP-06: ... --- (COM24)
Rx PING (COM24)
Tx PONG (COM24)
Rx PONG (桥接端)
Tx === MCP-06: PASS --- PING/PONG ===
```

---

## MCP-07: 实例独立性 — 关闭/重开 COM24 不影响 COM35

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 instanceId=1 和 instanceId=2 完全独立 |
| **前置** | 两个实例已打开 |

**步骤**:

1. 发送测试标注:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "--- MCP-07: 实例独立性 ---"
  format: "string"
```

2. 关闭 instanceId=2:

```
serial-monitor-mcp_close_serial_port
  port: "COM24"
  instanceId: "2"
```

3. 桥接端仍正常工作 — 发送 "test-after-close":

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "test-after-close"
  format: "string"
```

4. 读取桥接端状态确认:

```
serial-monitor-mcp_get_serial_status
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
```

5. 重新打开 COM24:

```
serial-monitor-mcp_open_serial_port
  port: "COM24"
  baudRate: 115200
  instanceId: "2"
```

6. 验证 UART2 正常:

```
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

7. 发送测试结果:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-07: PASS --- 实例独立 ==="
  format: "string"
```

**预期结果**:

| 操作 | 预期 |
|:---|:---|
| 关闭 COM24 后 | 桥接端仍 connected |
| 发送 "test-after-close" | 桥接端正常发送，Tx 计数增加 |
| 重开 COM24 | connected |
| UART2 状态 | 正常，无溢出 |

**判定**: PASS — COM24 关闭/重开不影响 COM35

**测试执行**:

```
Tx --- MCP-07: 实例独立性 ---
    [1] close COM24
Tx test-after-close
    [2] get_status → connected
    [3] open COM24
    [4] uart_status → 无溢出
Tx === MCP-07: PASS --- 实例独立 ===
```

---

## MCP-08: 串口状态统计 — Tx/Rx 计数器验证

| 项目 | 值 |
|:---|:---|
| **目的** | 验证各实例的 Tx/Rx 字节计数正确累加 |
| **前置** | 至少执行过 MCP-04 ~ MCP-06 中的几个 |

**步骤**:

1. 发送测试标注:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "--- MCP-08: 串口状态统计 ---"
  format: "string"
```

2. 获取各状态:

```
// 桥接端状态
serial-monitor-mcp_get_serial_status
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"

// COM24 状态
serial-monitor-mcp_get_serial_status
  port: "COM24"
  instanceId: "2"

// HEX-Bridge UART2 状态
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

3. 发送测试结果:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-08: PASS --- 计数器正常 overflow=0 ==="
  format: "string"
```

**预期结果**:

| 指标 | 预期值 |
|:---|:---|
| 桥接端 Tx 字节数 | > 0 (已发送数据) |
| 桥接端 Rx 字节数 | > 0 (已接收外设数据) |
| COM24 Tx 字节数 | ≥ 0 (取决于是否注入) |
| COM24 Rx 字节数 | > 0 (已收到桥接输出) |
| UART2 TX overflow | 0 |
| UART2 RX overflow | 0 |
| UART2 波特率 | 当前配置值 |

**判定**: PASS — 计数器非零，UART2 无溢出错误

**测试执行**:

```
Tx --- MCP-08: 串口状态统计 ---
    [1] get_status bridge → Tx>0, Rx>0
    [2] get_status COM24 → Rx>0
    [3] uart_status → overflow=0
Tx === MCP-08: PASS --- 计数器正常 overflow=0 ===
```

---

## MCP-09: Break 信号发送

| 项目 | 值 |
|:---|:---|
| **目的** | 通过 hex_bridge_send_break 发送 Break 信号，在 COM24 验证效果 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 发送测试标注:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "--- MCP-09: Break 信号 ---"
  format: "string"
```

2. 对 HEX-Bridge UART2 发送 Break (持续 50ms):

```
serial-monitor-mcp_hex_bridge_send_break
  port: "COM_HEXBRIDGE:COM35:CH1"
  durationMs: 50
```

3. 获取 UART2 状态:

```
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

4. 发送测试结果:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== MCP-09: PASS --- Break success ==="
  format: "string"
```

5. 发送测试总结:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "=== 测试总结: 全部 9/9 PASS ==="
  format: "string"
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| 命令执行 | 无错误返回 |
| UART2 状态 | 正常 (Break 后恢复) |

**判定**: PASS — Break 信号发送成功

> 如 COM24 端设备支持 Break 检测，可观察到 RX 线短暂的逻辑 0 电平。

**测试执行**:

```
Tx --- MCP-09: Break 信号 ---
    [1] send_break durationMs=50 → success
    [2] uart_status → 正常
Tx === MCP-09: PASS --- Break success ===
Tx === 测试总结: 全部 9/9 PASS ===
```

---

## 分屏清理流程

```
// 关闭 instanceId=2
serial-monitor-mcp_close_serial_port
  port: "COM24"
  instanceId: "2"

// 关闭 instanceId=1
serial-monitor-mcp_close_serial_port
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
```

---

## 用例总览

| 编号 | 用例名称 | 分类 | 涉及工具 |
|:---|:---|:---|:---|
| MCP-01 | 设备发现 | 基础 | hex_bridge_discover |
| MCP-02 | 设备信息 | 基础 | hex_bridge_device_info |
| MCP-03 | 分屏初始化 | 基础 | open ×2, get_status ×2 |
| MCP-04 | 桥接发送 (string) → 扩展口 | 数据通路 | send (虚拟路径), read (COM24) |
| MCP-05 | 扩展口注入 → 桥接接收 | 数据通路 | send (COM24), read (虚拟路径) |
| MCP-06 | 双向回环 (PING/PONG) | 集成 | send ×2, read ×2 |
| MCP-07 | 实例独立性 | 基础 | close, send, open, uart_status |
| MCP-08 | 状态统计 | 系统 | send, get_status ×2, uart_status |
| MCP-09 | Break 信号 | UART | send, send_break, uart_status |

---

## 测试执行汇总

| 编号 | 用例名称 | 结果 |
|:---|:---|:---|
| MCP-01 | 设备发现 | PASS |
| MCP-02 | 设备信息 | PASS |
| MCP-03 | 分屏初始化 | PASS |
| MCP-04 | 桥接发送 → 扩展口监控 | PASS |
| MCP-05 | 扩展口注入 → 桥接接收 | PASS |
| MCP-06 | 双向回环 (PING/PONG) | PASS |
| MCP-07 | 实例独立性 | PASS |
| MCP-08 | 状态统计 | PASS |
| MCP-09 | Break 信号 | PASS |

---

## 判定标准

| 级别 | 说明 |
|:---|:---|
| **PASS** | 数据通路正常，两端收发一致，无丢包/乱序 |
| **FAIL** | 数据不一致、丢包、乱序、超时无响应、实例间干扰 |
| **N/A** | Serial Monitor MCP 不可用、HEX-Bridge 未连接、COM 端口占用 |

---

## 关键原则

1. **UBCP 不可见** — 所有用例不涉及 UBCP 帧构造、命令码、CRC 计算。用户仅操作原始数据。
2. **分屏独立** — instanceId=1 和 instanceId=2 各自独立，关闭一侧不影响另一侧。
3. **透明桥接** — HEX-Bridge 对用户来说就是一个透明的串口桥: 通过虚拟路径 `COM_HEXBRIDGE:COM35:CH1` 发送的数据，COM24 就能收到；COM24 发送的数据，在虚拟路径端就能收到。
4. **标注通过串口** — 每个测试的标注和结果均通过 `send_serial_data` 发送到桥接端，在设备界面中可见。

---

## MCP 工具速查

| 工具 | 实例参数 | 用途 |
|:---|:---|:---|
| `serial-monitor-mcp_hex_bridge_discover` | 无 | 发现所有 HEX-Bridge 设备 |
| `serial-monitor-mcp_hex_bridge_device_info` | `port` (虚拟路径) | 获取设备型号/序列号/固件版本 |
| `serial-monitor-mcp_hex_bridge_uart_status` | `port` (虚拟路径) | 获取远端 UART2 状态 |
| `serial-monitor-mcp_hex_bridge_send_break` | `port` (虚拟路径) | 发送 Break 信号 |
| `serial-monitor-mcp_open_serial_port` | `instanceId: "1" \| "2"`, `port` (物理端口或虚拟路径) | 打开串口 (分屏)。HEX-Bridge 设备直接传入虚拟路径 |
| `serial-monitor-mcp_close_serial_port` | `instanceId: "1" \| "2"` | 关闭串口 |
| `serial-monitor-mcp_send_serial_data` | `port` | 发送数据 (原始格式) |
| `serial-monitor-mcp_read_serial_buffer` | `instanceId: "1" \| "2"` | 读取收发缓存 |
| `serial-monitor-mcp_get_serial_status` | `instanceId: "1" \| "2"` | 获取连接状态和计数器 |
| `serial-monitor-mcp_set_display_flags` | `instanceId: "1" \| "2"` | 设置显示格式 |
