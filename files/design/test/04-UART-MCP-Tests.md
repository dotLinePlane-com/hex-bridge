# 04. UART MCP 测试 (MCP Serial Monitor 分屏通信)

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
// instanceId=1: hex 显示 + 时间戳 + 行号
serial-monitor-mcp_set_display_flags
  instanceId: "1"
  flags: {
    isHexRx: true,
    isHexTx: true,
    isAddTimeHead: true,
    isShowLine: true,
    isShowRx: true,
    isShowTx: true
  }

// instanceId=2: 同上
serial-monitor-mcp_set_display_flags
  instanceId: "2"
  flags: {
    isHexRx: true,
    isHexTx: true,
    isAddTimeHead: true,
    isShowLine: true,
    isShowRx: true,
    isShowTx: true
  }
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

---

## MCP-04: 桥接发送 → 扩展口监控 (数据通路: 用户→外设)

| 项目 | 值 |
|:---|:---|
| **目的** | 从 COM35 发送数据，在 COM24 验证 HEX-Bridge 正确将数据输出到 UART2 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 清空 HEX-Bridge 缓冲区:

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "drain"
```

2. 从桥接端发送 "Hello" (string 格式):

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "Hello"
  format: "string"
```

3. 等待约 500ms，从 COM24 读取接收数据:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM24"
  instanceId: "2"
  display: "hex"
  direction: "rx"
  count: 10
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| COM24 Rx 内容 | 含 `48 65 6C 6C 6F` ("Hello") |
| 时间戳 | 在发送操作后合理时间内 |

**判定**: PASS — COM24 收到完整的 "Hello" 数据

> Serial Monitor 插件自动将桥接端的 "Hello" 封装为 UBCP UART_SEND 帧发送给 ESP32，ESP32 从 UART2 输出原始数据，COM24 直接监听到物理信号。用户全程不感知 UBCP。

---

## MCP-05: 桥接发送 (hex) → 扩展口监控

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 hex 格式发送的二进制数据同样正确传递到 UART2 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 清空缓冲区:

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "drain"
```

2. 从桥接端发送 hex 数据 `0x01 0x02 0x03 0xFF 0x00`:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "01 02 03 FF 00"
  format: "hex"
```

3. 等待约 500ms，从 COM24 读取:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM24"
  instanceId: "2"
  display: "hex"
  direction: "rx"
  count: 10
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| COM24 Rx 内容 | `01 02 03 FF 00` |

**判定**: PASS — 二进制数据无损传递 (含 0xFF、0x00 边界值)

---

## MCP-06: 扩展口注入 → 桥接接收 (数据通路: 外设→用户)

| 项目 | 值 |
|:---|:---|
| **目的** | 从 COM24 注入数据模拟外设，在 COM35 验证 HEX-Bridge 正确上报接收数据 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 从 COM24 注入 "World" (hex 格式):

```
serial-monitor-mcp_send_serial_data
  port: "COM24"
  data: "57 6F 72 6C 64"
  format: "hex"
```

2. 等待约 500ms，从桥接端读取:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
  display: "hex"
  direction: "rx"
  count: 10
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| 桥接端 Rx 内容 | 含 `57 6F 72 6C 64` ("World") |

**判定**: PASS — 桥接端收到完整的 "World" 数据

> COM24 向 UART2 注入 "World" → ESP32 UART2 接收 → 封装为 UBCP UART_RECV 事件 → COM35 解封显示 "World"。用户全程不感知 UBCP。

---

## MCP-07: 双向回环 (string 模式)

| 项目 | 值 |
|:---|:---|
| **目的** | 完整验证双通道: COM35→Bridge→UART2→COM24 和 COM24→UART2→Bridge→COM35 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 清空两侧缓冲区:

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "all"
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

**预期结果**:

| 阶段 | 窗口 | 预期内容 |
|:---|:---|:---|
| 发送 | 桥接端 Tx | "PING" |
| 接收 | COM24 Rx | "PING" |
| 注入 | COM24 Tx | "PONG" |
| 上报 | 桥接端 Rx | "PONG" |

**判定**: PASS — 双向数据完整: "PING" 出现在 COM24，"PONG" 出现在桥接端

---

## MCP-08: 大数据块发送 — 验证载荷完整性

| 项目 | 值 |
|:---|:---|
| **目的** | 发送 256 字节数据，验证大数据块通过桥接后完整性 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 清空缓冲区:

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "drain"
```

2. 从桥接端发送 256 字节递增数据 (hex 格式):

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F 10 11 12 13 14 15 16 17 18 19 1A 1B 1C 1D 1E 1F 20 21 22 23 24 25 26 27 28 29 2A 2B 2C 2D 2E 2F 30 31 32 33 34 35 36 37 38 39 3A 3B 3C 3D 3E 3F 40 41 42 43 44 45 46 47 48 49 4A 4B 4C 4D 4E 4F 50 51 52 53 54 55 56 57 58 59 5A 5B 5C 5D 5E 5F 60 61 62 63 64 65 66 67 68 69 6A 6B 6C 6D 6E 6F 70 71 72 73 74 75 76 77 78 79 7A 7B 7C 7D 7E 7F 80 81 82 83 84 85 86 87 88 89 8A 8B 8C 8D 8E 8F 90 91 92 93 94 95 96 97 98 99 9A 9B 9C 9D 9E 9F A0 A1 A2 A3 A4 A5 A6 A7 A8 A9 AA AB AC AD AE AF B0 B1 B2 B3 B4 B5 B6 B7 B8 B9 BA BB BC BD BE BF C0 C1 C2 C3 C4 C5 C6 C7 C8 C9 CA CB CC CD CE CF D0 D1 D2 D3 D4 D5 D6 D7 D8 D9 DA DB DC DD DE DF E0 E1 E2 E3 E4 E5 E6 E7 E8 E9 EA EB EC ED EE EF F0 F1 F2 F3 F4 F5 F6 F7 F8 F9 FA FB FC FD FE FF"
  format: "hex"
```

3. 等待约 1s，从 COM24 读取:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM24"
  instanceId: "2"
  display: "hex"
  direction: "rx"
  count: 20
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| COM24 收到数据总长度 | 256 字节 |
| 首字节 | 0x00 |
| 尾字节 | 0xFF |
| 连续性 | 相邻字节差 1 (0x00, 0x01, 0x02, ..., 0xFF) |

**判定**: PASS — 256 字节完整无缺，顺序无错乱

---

## MCP-09: 实例独立性 — 关闭/重开 COM24 不影响 COM35

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 instanceId=1 和 instanceId=2 完全独立 |
| **前置** | 两个实例已打开 |

**步骤**:

1. 关闭 instanceId=2:

```
serial-monitor-mcp_close_serial_port
  port: "COM24"
  instanceId: "2"
```

2. 桥接端仍正常工作 — 发送 "test":

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "test-after-close"
  format: "string"
```

3. 读取桥接端状态确认:

```
serial-monitor-mcp_get_serial_status
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
```

4. 重新打开 COM24:

```
serial-monitor-mcp_open_serial_port
  port: "COM24"
  baudRate: 115200
  instanceId: "2"
```

5. 验证 COM35 仍然正常:

```
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

**预期结果**:

| 操作 | 预期 |
|:---|:---|
| 关闭 COM24 后 | 桥接端仍 connected |
| 发送 "test-after-close" | 桥接端正常发送，Tx 计数增加 |
| 重开 COM24 | connected |
| UART2 状态 | 正常，无溢出 |

**判定**: PASS — COM24 关闭/重开不影响 COM35

---

## MCP-10: 串口状态统计 — Tx/Rx 计数器验证

| 项目 | 值 |
|:---|:---|
| **目的** | 验证各实例的 Tx/Rx 字节计数正确累加 |
| **前置** | 至少执行过 MCP-04 ~ MCP-07 中的几个 |

**步骤**:

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

---

## MCP-11: Break 信号发送

| 项目 | 值 |
|:---|:---|
| **目的** | 通过 hex_bridge_send_break 发送 Break 信号，在 COM24 验证效果 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 对 HEX-Bridge UART2 发送 Break (持续 50ms):

```
serial-monitor-mcp_hex_bridge_send_break
  port: "COM_HEXBRIDGE:COM35:CH1"
  durationMs: 50
```

2. 获取 UART2 状态:

```
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| 命令执行 | 无错误返回 |
| UART2 状态 | 正常 (Break 后恢复) |

**判定**: PASS — Break 信号发送成功

> 如 COM24 端设备支持 Break 检测，可观察到 RX 线短暂的逻辑 0 电平。

---

## MCP-12: Flush 缓冲区清空

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 flush 操作能正确清空 HEX-Bridge 缓冲区 |
| **前置** | MCP-03 通过 |

**步骤**:

1. 从 COM24 注入填充数据:

```
serial-monitor-mcp_send_serial_data
  port: "COM24"
  data: "FF FE FD FC FB FA F9 F8 F7 F6"
  format: "hex"
```

2. 获取 UART2 状态查看 RX 缓冲:

```
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

3. 清空 RX 缓冲:

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "rx"
```

4. 再次获取状态:

```
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| flush 前 RX 计数 | > 0 |
| flush 后 RX 计数 | 较之前减少 (缓冲区已清空) |

**判定**: PASS — flush 后缓冲区清除

---

## MCP-13: FLUSH ALL 不再超时 — 验证修复

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 `type: "all"` 在 TX 缓冲区有残余数据时不再超时 |
| **前置** | MCP-03 通过 |
| **背景** | 修复前固件 `uart_wait_tx_done(1000ms)` 阻塞导致 MCP 插件 UBCP 响应超时。修复后改为轮询+Yield（200ms max），响应时间大幅缩短。 |

**步骤**:

1. 从 COM35 发送数据填充 TX 缓冲区后立即执行 FLUSH ALL:

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "all"
```

2. 从 COM35 发送验证数据确认通道正常:

```
serial-monitor-mcp_send_serial_data
  port: "COM_HEXBRIDGE:COM35:CH1"
  data: "post-flush"
  format: "string"
```

3. 从 COM24 读取确认:

```
serial-monitor-mcp_read_serial_buffer
  port: "COM24"
  instanceId: "2"
  display: "string"
  direction: "rx"
  count: 5
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| flush all 返回 | success, 无 UBCP command timed out |
| COM24 收到 | "post-flush" |

**判定**: PASS — FLUSH ALL 无超时，数据通路正常

---

## MCP-14: STATUS 紧接 FLUSH ALL — 验证不阻塞

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 FLUSH ALL 后立即调用 STATUS 不会因前序阻塞而超时 |
| **前置** | MCP-13 通过 |

**步骤**:

1. 从 COM24 注入填充数据（使 RX 有活跃数据）:

```
serial-monitor-mcp_send_serial_data
  port: "COM24"
  data: "AA BB CC DD EE FF 00 11 22 33"
  format: "hex"
```

2. 立即执行 FLUSH ALL:

```
serial-monitor-mcp_hex_bridge_flush
  port: "COM_HEXBRIDGE:COM35:CH1"
  type: "all"
```

3. 紧接着获取 UART2 状态:

```
serial-monitor-mcp_hex_bridge_uart_status
  port: "COM_HEXBRIDGE:COM35:CH1"
```

4. 再获取 COM35 实例状态:

```
serial-monitor-mcp_get_serial_status
  port: "COM_HEXBRIDGE:COM35:CH1"
  instanceId: "1"
```

**预期结果**:

| 检查项 | 预期值 |
|:---|:---|
| flush all | success, 无超时 |
| uart_status | 正常返回，无超时 |
| get_serial_status | connected |

**判定**: PASS — FLUSH ALL 与 STATUS 均无超时，通道正常

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
| MCP-05 | 桥接发送 (hex) → 扩展口 | 数据通路 | send (虚拟路径), read (COM24) |
| MCP-06 | 扩展口注入 → 桥接接收 | 数据通路 | send (COM24), read (虚拟路径) |
| MCP-07 | 双向回环 (PING/PONG) | 集成 | send ×2, read ×2 |
| MCP-08 | 大数据块 (256 字节) | 数据通路 | send (虚拟路径), read (COM24) |
| MCP-09 | 实例独立性 | 基础 | close, send, open, uart_status |
| MCP-10 | 状态统计 | 系统 | get_status ×2, uart_status |
| MCP-11 | Break 信号 | UART | send_break, uart_status |
| MCP-12 | Flush 缓冲区 | UART | send (COM24), flush, uart_status |
| MCP-13 | FLUSH ALL 不再超时 | UART | flush all, send, read |
| MCP-14 | STATUS 紧接 FLUSH ALL | UART | send (COM24), flush all, uart_status, get_status |

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

---

## MCP 工具速查

| 工具 | 实例参数 | 用途 |
|:---|:---|:---|
| `serial-monitor-mcp_hex_bridge_discover` | 无 | 发现所有 HEX-Bridge 设备 |
| `serial-monitor-mcp_hex_bridge_device_info` | `port` (虚拟路径) | 获取设备型号/序列号/固件版本 |
| `serial-monitor-mcp_hex_bridge_uart_status` | `port` (虚拟路径) | 获取远端 UART2 状态 |
| `serial-monitor-mcp_hex_bridge_flush` | `port` (虚拟路径) | 清空 HEX-Bridge 收发缓冲区 |
| `serial-monitor-mcp_hex_bridge_send_break` | `port` (虚拟路径) | 发送 Break 信号 |
| `serial-monitor-mcp_open_serial_port` | `instanceId: "1" \| "2"`, `port` (物理端口或虚拟路径) | 打开串口 (分屏)。HEX-Bridge 设备直接传入虚拟路径 |
| `serial-monitor-mcp_close_serial_port` | `instanceId: "1" \| "2"` | 关闭串口 |
| `serial-monitor-mcp_send_serial_data` | `port` | 发送数据 (原始格式) |
| `serial-monitor-mcp_read_serial_buffer` | `instanceId: "1" \| "2"` | 读取收发缓存 |
| `serial-monitor-mcp_get_serial_status` | `instanceId: "1" \| "2"` | 获取连接状态和计数器 |
| `serial-monitor-mcp_set_display_flags` | `instanceId: "1" \| "2"` | 设置显示格式 |
