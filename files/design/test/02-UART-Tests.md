# 02. UART 扩展模块测试用例

> 命令码范围：`0xA0-0xAF` | 模块：`mod_uart` | UART2 → 外部串口设备
>
> **测试脚本**: `script/test/test_uart.py` (57 用例, UART-01 ~ UART-57)

**测试拓朴**:
```
PC(COM35) ── MCP ──→ HEX-Bridge ── UART2 ──→ 外部设备 ←── COM24(PC 监控)
```

所有 MCP 命令通过 COM35 发送，UART2 数据流通可通过 COM24 监控/注入。

---

## UART-01: UART_OPEN — 正常打开（被动上报模式）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA0` |
| **PayloadLen** | `0x0001` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | RxMode | `0x00` (被动上报) |

**预期响应**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-2 | RxBufSize | `0x0800` (2048, 大端) |
| 3-4 | TxBufSize | `0x0400` (1024, 大端) |

**判定**: PASS — Status=0x00, RxBufSize=2048, TxBufSize=1024

---

## UART-02: UART_OPEN — 重复打开（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA0` |
| **PayloadLen** | `0x0001` |

**前置**: 先执行 UART-01 成功打开

**请求载荷**: 同 UART-01

**预期响应**: Status=`0x0B` (ERR_ALREADY_OPEN)

**判定**: PASS — 拒绝重复打开

---

## UART-03: UART_OPEN — 无效 RxMode（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA0` |
| **PayloadLen** | `0x0001` |

**前置**: 先执行 UART_CLOSE 确保关闭

**请求载荷**: RxMode = `0x04` (> TIMEOUT 最大值 0x03)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

## UART-04: UART_OPEN — 行模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA0` |
| **PayloadLen** | `0x0001` |

**前置**: 先执行 UART_CLOSE

**请求载荷**: RxMode = `0x01` (行模式)

**预期响应**: Status=`0x00`, BufSize 与 UART-01 一致

---

## UART-05: UART_CONFIG — 配置波特率 921600

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` (11 字节) |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-3 | BaudRate | `0x000E1000` (921600) |
| 4 | DataBits | `0x08` |
| 5 | StopBits | `0x01` |
| 6 | Parity | `0x00` |
| 7 | FlowControl | `0x00` |
| 8-9 | RxThreshold | `0x0040` (64) |
| 10 | RxTimeout | `0x14` (20ms) |

**预期响应**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-4 | ActualBaud | 接近 921600 (±3% 偏差) |

**判定**: PASS — 接近 921600 (±3% 偏差)

---

## UART-06: UART_CONFIG — 配置波特率 115200

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` (11 字节) |

**请求载荷**: BaudRate=`0x0001C200` (115200), DataBits=`0x08`, StopBits=`0x01`, Parity=`0x00`, FlowControl=`0x00`, RxThreshold=`0x0040`, RxTimeout=`0x14`

**预期响应**: Status=`0x00`, ActualBaud 接近 115200 (±1%)

**判定**: PASS — ActualBaud≈115201 (±0.001%)

---

## UART-07: UART_CONFIG — 配置 7E1 数据格式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**请求载荷**: BaudRate=115200, DataBits=`0x07`, StopBits=`0x01`, Parity=`0x02` (Even), FlowControl=`0x00`

**预期响应**: Status=`0x00`

**判定**: PASS — 7 位数据 + 偶校验配置成功

---

## UART-08: UART_CONFIG — 无效 DataBits（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**请求载荷**: BaudRate=115200, DataBits=`0x04`, StopBits=`0x01`, Parity=`0x00`, FlowControl=`0x00`

**预期响应**: Status=`0x02` (ERR_PARAM)

**判定**: PASS — DataBits=`0x04` 不在合法范围 {5,6,7,8}

---

## UART-09: UART_CONFIG — 无效 StopBits（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**请求载荷**: BaudRate=115200, DataBits=`0x08`, StopBits=`0x04`, Parity=`0x00`, FlowControl=`0x00`

**预期响应**: Status=`0x02` (ERR_PARAM)

**判定**: PASS — StopBits=`0x04` 不在合法范围 {1, 1.5, 2}

---

## UART-10: UART_CONFIG — Mark/Space 校验（不支持）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**请求载荷**: BaudRate=115200, DataBits=`0x08`, StopBits=`0x01`, Parity=`0x03` (Mark) 或 `0x04` (Space)

**预期响应**: Status=`0x06` (ERR_NOT_SUPPORT)

**判定**: PASS — ESP32 UART 硬件不支持 Mark/Space 校验

---

## UART-11: UART_CONFIG — 硬件流控（不支持）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**请求载荷**: BaudRate=115200, DataBits=`0x08`, StopBits=`0x01`, Parity=`0x00`, FlowControl=`0x01` (RTS/CTS)

**预期响应**: Status=`0x06` (ERR_NOT_SUPPORT)

**判定**: PASS — UART2 无 RTS/CTS 硬件引脚

---

## UART-12: UART_CONFIG — 未打开时调用（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |

**前置**: 执行 UART_CLOSE，确保通道关闭

**预期响应**: Status=`0x05` (ERR_NOT_OPEN)

---

## UART-13: UART_SEND — 发送数据到外部设备

| 项目 | 值 |
|:---|:---|
| **CmdCode (SEND)** | `0xA3` |
| **事件 (RECV)** | `0xA4` |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1) — 匹配外部设备参数
2. 通过 MCP (COM35) 发送 SEND 命令:

**请求载荷** (UART_SEND):
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | DataLen | `0x000B` (11) |
| 2-12 | Data | `"Hello World"` (ASCII) |

**预期 SEND 响应** (COM35): Status=`0x00`, ActualLen=`0x000B`

**验证 (COM24)**: 在 COM24 上监听到 HEX-Bridge UART2 发出的 `"Hello World"`。

**验证 (外部设备)**: 如果外部设备会回复数据，预期收到 UART_RECV 事件 (CmdCode=`0xA4`)：
| 偏移 | 字段 | 说明 |
|:---|:---|:---|
| 0 | RxFlags | 错误标志，正常为 `0x00` |
| 1-2 | DataLen | 外部设备回复数据长度 |
| 3... | Data | 外部设备回复数据 |

**判决**: PASS — SEND 响应 Status=0x00 + COM24 可监听到发送数据

---

## UART-14: UART_SEND — 空载荷

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA3` |

**请求载荷**: DataLen=`0x0000`, 无 Data 字段

**预期响应**: Status=`0x00`, ActualLen=`0x0000`

**验证 (COM24)**: 无任何字节输出

---

## UART-15: UART_SEND — 载荷长度声明不匹配（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA3` |

**请求载荷**: DataLen=`0x000A` (声明 10 字节), Data 仅 `0x48 0x45` (2 字节)

**帧 PayloadLen**: `2 + 2 = 4` (PayloadLen=4, DataLen 字段声明=10)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

## UART-16: UART_CLOSE — 正常关闭

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA1` |
| **PayloadLen** | `0x0000` |

**前置**: UART 通道已打开

**请求载荷**: 空

**预期响应**: Status=`0x00`

**验证**: 关闭后可重新 UART_OPEN 成功

---

## UART-17: UART_CLOSE — 未打开时关闭（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA1` |

**前置**: 确保通道未打开

**预期响应**: Status=`0x05` (ERR_NOT_OPEN)

---

## UART-18: UART_STATUS — 查询运行状态

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA6` |
| **PayloadLen** | `0x0000` |

**前置**: UART 通道已打开

**预期响应** (Payload 共 19 字节):
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-4 | BaudRate | 当前波特率 |
| 5 | LineState | Bit0 (TxIdle) = 1 if TX buffer empty, else 0 |
| 6-7 | TxBufUsed | `0x0000` |
| 8-9 | RxBufUsed | `>= 0` |
| 10-13 | TxCount | `>= 0` |
| 14-17 | RxCount | `>= 0` |
| 18 | ErrorCount | `0x00` |

**判定**: PASS — Status=0x00, LineState 包含 TxIdle, 各计数器为非负值

---

## UART-19: UART_STATUS — 未打开时查询

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA6` |

**预期响应**: Status=`0x05` (ERR_NOT_OPEN)

---

## UART-20: UART_FLUSH — 清空接收缓冲区

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA7` |
| **PayloadLen** | `0x0001` |

**请求载荷**: FlushType=`0x00` (清空 RX)

**预期响应**: Status=`0x00`

---

## UART-21: UART_FLUSH — 无效 FlushType

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA7` |
| **PayloadLen** | `0x0001` |

**请求载荷**: FlushType=`0x04` (> DRAIN 最大值 0x03)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

## UART-22: UART_SET_BREAK — 发送 Break 信号

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA5` |
| **PayloadLen** | `0x0002` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | DurationMs | `0x000A` (10ms) |

**预期响应**: Status=`0x00`

**验证 (COM24)**: 外部设备侧可观察到 RX 线被拉低约 10ms（Break 信号）。

---

## UART-23: UART_SET_BREAK — 默认持续时间

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA5` |
| **PayloadLen** | `0x0002` |

**请求载荷**: DurationMs=`0x0000` (0 → 应使用默认 10ms)

**预期响应**: Status=`0x00`

---

## UART-24: 外部数据接收 — RECV 事件上报

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. 通过 COM24 向外部设备侧发送数据 `0x41 0x42 0x43` (ASCII "ABC")，数据会到达 HEX-Bridge UART2 RX 引脚

**预期**: 通过 COM35 收到 UART_RECV 事件:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | RxFlags | `0x00` |
| 1-2 | DataLen | `0x0003` |
| 3-5 | Data | `0x41 0x42 0x43` |

**判定**: PASS — 收到 RECV 事件，数据与 COM24 发出的完全一致

---

## UART-25: 接收模式 — 行模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(行模式, RxMode=`0x01`) + UART_CONFIG(115200, 8N1)
2. 通过 COM24 发送 `"Hello\nWorld\n"`

**预期**: 收到 2 条 RECV 事件：
- 第 1 条: Data=`"Hello\n"`
- 第 2 条: Data=`"World\n"`

**判定**: PASS — 按行分割上报

---

## UART-26: 接收模式 — 定长模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(定长模式, RxMode=`0x02`) + UART_CONFIG(115200, 8N1, RxThreshold=`0x0004`)
2. 通过 COM24 发送 8 字节: `0x00 0x01 0x02 0x03 0x04 0x05 0x06 0x07`

**预期**: 收到 2 条 RECV 事件：
- 第 1 条: DataLen=4, Data=`0x00 0x01 0x02 0x03`
- 第 2 条: DataLen=4, Data=`0x04 0x05 0x06 0x07`

**判定**: PASS — 按 RxThreshold=4 分块上报

---

## UART-27: 接收模式 — 超时模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(超时模式, RxMode=`0x03`) + UART_CONFIG(115200, 8N1, RxTimeout=`0x14`=20ms)
2. 通过 COM24 发送 3 字节: `0xAA 0xBB 0xCC`
3. 等待超过 20ms，确保超时触发上报

**预期**: 收到 1 条 RECV 事件，DataLen=3, Data=`0xAA 0xBB 0xCC`

**判定**: PASS — 超时后一次性上报累积数据

---

## UART-28: FLOW_CONTROL — 查询流控状态

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x05` |
| **PayloadLen** | `0x0001` |

**前置**: UART 通道已打开，无大量数据注入

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ModuleID | `0xA0` (UART 模块) |

**预期响应**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | Count | `0x01` |
| 2 | ModuleID | `0xA0` |
| 3 | State | `0x00` (normal) |
| 4-5 | BufUsage | `< BufCapacity` |
| 6 | BufPercent | `0x00-0x50` (低水位) |

**判定**: PASS — State=0x00 (normal), 缓冲区使用率低

---

## UART-29: FLOW_CONTROL — 查询所有模块

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x05` |
| **PayloadLen** | `0x0001` |

**请求载荷**: ModuleID=`0xFF` (查询全部)

**预期响应**: Count>=1, 包含所有已注册的模块状态（至少 UART 0xA0）

**判定**: PASS — 返回全部模块流控状态

---

## UART-30: FLOW_CONTROL — XOFF/XON 序列

| 项目 | 值 |
|:---|:---|
| **事件 CmdCode** | `0x05` (FLOW_CONTROL, 设备→主机) |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. 查询流控 → State=normal
3. 通过 COM24 持续注入大量数据 (如 4000+ bytes at 115200 bps) 填满 UART2 RX 缓冲区
4. 监听 FLOW_CONTROL 事件 (CmdCode=`0xA4` for RECV + `0x05` for flow)

**预期**: 
- 数据注入期间可能收到 XOFF 事件 (Action=`0x00`, ModuleID=`0xA0`)
- 数据停止后缓冲区排空，收到 XON 事件 (Action=`0x01`, ModuleID=`0xA0`)
- 或：缓冲区未达到 80% 高水位，不触发 XOFF (正常)

**判定**: PASS — RX 缓冲区水位检测正常工作，或缓冲区未溢出

---

# 补充测试用例 (v0.2.0)

> 以下用例覆盖评估报告识别的缺口：请求层错误路径、RxFlags 错误标志、FLUSH 子类型、STATUS 深度查询、边界/压力、整合场景。

---

## 请求层错误路径

### UART-31: UART_SEND — 未打开时调用（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA3` |

**前置**: 执行 UART_CLOSE，确保通道关闭

**请求载荷**: DataLen=`0x0005`, Data=`0x41 0x42 0x43 0x44 0x45`

**预期响应**: Status=`0x05` (ERR_NOT_OPEN)

---

### UART-32: UART_SET_BREAK — 未打开时调用（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA5` |

**前置**: 执行 UART_CLOSE，确保通道关闭

**请求载荷**: DurationMs=`0x000A` (10ms)

**预期响应**: Status=`0x05` (ERR_NOT_OPEN)

---

### UART-33: UART_FLUSH — 未打开时调用（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA7` |

**前置**: 执行 UART_CLOSE，确保通道关闭

**请求载荷**: FlushType=`0x02` (清空 ALL)

**预期响应**: Status=`0x05` (ERR_NOT_OPEN)

---

### UART-34: UART_CONFIG — 载荷不足（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x0005` (仅 5 字节, 需要 11) |

**前置**: UART 通道已打开

**请求载荷**: 仅 `0x00 0x01 0x02 0x03 0x08` (截断)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

### UART-35: UART_SEND — 载荷不足（错误用例）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA3` |
| **PayloadLen** | `0x0001` (仅 1 字节, 至少需要 2 字节的 DataLen 字段) |

**前置**: UART 通道已打开

**请求载荷**: 仅 `0x00` (缺少 DataLen 高字节)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

### UART-36: UART_SET_BREAK — 空载荷（使用默认值）

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA5` |
| **PayloadLen** | `0x0000` |

**前置**: UART 通道已打开

**请求载荷**: 空（应使用默认 10ms）

**预期响应**: Status=`0x00`

**验证**: 行为与 UART-23（DurationMs=0）相同

---

## FLUSH 子类型

### UART-37: UART_FLUSH — 清空发送缓冲区 (TX)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA7` |
| **PayloadLen** | `0x0001` |

**前置**: UART 通道已打开，先 SEND 大数据（如 512 字节），等待写入缓冲区

**请求载荷**: FlushType=`0x01` (清空 TX)

**预期响应**: Status=`0x00`

**验证**: `uart_wait_tx_done` 被调用，等待发送完成后返回

---

### UART-38: UART_FLUSH — 清空所有缓冲区 (ALL)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA7` |
| **PayloadLen** | `0x0001` |

**前置**: UART 通道已打开

**请求载荷**: FlushType=`0x02` (清空 ALL)

**预期响应**: Status=`0x00`

**验证**: RX 和 TX 缓冲区均被清空

---

### UART-39: UART_FLUSH — 等待发送完成后清空 (DRAIN)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA7` |
| **PayloadLen** | `0x0001` |

**前置**: UART 通道已打开，先 SEND 小量数据

**请求载荷**: FlushType=`0x03` (DRAIN)

**预期响应**: Status=`0x00`

**验证**: 命令返回前数据已从 TX 缓冲区发出，然后 RX 缓冲区也被清空

---

## RxFlags 错误标志

### UART-40: RECV 事件 — BreakDetect (RxFlags Bit3)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. 执行 UART_SET_BREAK (10ms)
3. 等待 COM24 回环到达 UART2 RX 引脚

**预期**: 通过 COM35 收到 UART_RECV 事件，RxFlags Bit3 (BreakDetect) = 1

**注意**: 需 UART2 TX/RX 回环连接（短接 GPIO32 与 GPIO35），使 Break 信号反馈到接收端

---

### UART-41: RECV 事件 — ParityError (RxFlags Bit1)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 7E1)
2. 通过 COM24 以 115200/8N1 参数发送数据 `0x41 0x42`（对方无校验 → 接收端检测到校验不匹配）

**预期**: 通过 COM35 收到 UART_RECV 事件，RxFlags Bit1 (ParityError) = 1

---

### UART-42: RECV 事件 — FrameError (RxFlags Bit2)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. 通过 COM24 以 115200/8N2 参数发送数据 `0x41`（对方 2 停止位 → 接收端期望 1 停止位，检测到帧错误）

**预期**: 通过 COM35 收到 UART_RECV 事件，RxFlags Bit2 (FrameError) = 1

---

### UART-43: RECV 事件 — BufferOverflow (RxFlags Bit0)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA4` (事件) |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(128000, 8N1)（使用非标准高速率）
2. 通过 COM24 以 ≥ 921600 bps 持续高速注入 4000+ 字节，超过 RX 缓冲区
3. 观察是否有 RECV 事件携带 BufferOverflow 标志

**预期**: 注入速率超过 RX 任务排水速率时，通过 COM35 收到 RECV 事件，RxFlags Bit0 (BufferOverflow) = 1

**注意**: 此用例依赖硬件注入速率 > 固件排水速率，可能无法在低速 PC 串口上触发

---

## STATUS 深度查询

### UART-44: UART_STATUS — 发送数据后查询

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA6` |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. 先查询 STATUS (基线: TxCount=0)
3. UART_SEND 100 字节数据
4. 再查询 STATUS

**预期** (第 2 次 STATUS):
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 10-13 | TxCount | `>= 100` (与 SEND 的 ActualLen 一致) |

---

### UART-45: UART_STATUS — 接收数据后查询

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA6` |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. 先查询 STATUS (基线: RxCount=0)
3. 通过 COM24 注入 50 字节数据
4. 等待收到 RECV 事件后查询 STATUS

**预期** (第 2 次 STATUS):
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 14-17 | RxCount | `>= 50` (与注入字节数一致) |

---

### UART-46: UART_STATUS — 错误累积计数

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA6` |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 7E1)
2. 通过 COM24 以 115200/8N1 注入多组数据（每组 4 字节），触发 ParityError
3. 查询 STATUS

**预期**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 18 | ErrorCount | `> 0` (累积校验错误 + 帧错误) |

---

## 边界与参数覆盖

### UART-47: UART_SEND — 大数据量

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA3` |

**前置**: UART 通道已打开，UART_CONFIG(115200, 8N1)

**请求载荷**: DataLen=`0x0200` (512), Data = 512 字节随机数据

**预期响应**: Status=`0x00`, ActualLen=`0x0200`

**验证 (COM24)**: 监听到 512 字节完整数据输出

---

### UART-48: UART_CONFIG — 极限波特率 1200

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**前置**: UART 通道已打开

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-3 | BaudRate | `0x000004B0` (1200) |
| 4 | DataBits | `0x08` |
| 5 | StopBits | `0x01` |
| 6 | Parity | `0x00` |
| 7 | FlowControl | `0x00` |
| 8-9 | RxThreshold | `0x0001` |
| 10 | RxTimeout | `0x14` |

**预期响应**: Status=`0x00`, ActualBaud 接近 1200

---

### UART-49: UART_CONFIG — 定长模式修改阈值触发任务重启

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |

**测试步骤**:
1. UART_OPEN(定长模式, RxMode=`0x02`) + UART_CONFIG(115200, 8N1, RxThreshold=`0x0004`)
2. 通过 COM24 发送 3 字节（未达到阈值 4，数据暂存不报）
3. SEND_CONFIG(RxThreshold=`0x0008`) 增大阈值
4. 再通过 COM24 发送 5 字节（累积 3+5=8，达到新阈值）
5. 验证收到 8 字节定长块

**预期**: 阈值修改后 RX 任务重启，新阈值生效，收到完整 8 字节数据块

---

### UART-50: UART_CONFIG — 超时模式修改超时触发任务重启

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |

**测试步骤**:
1. UART_OPEN(超时模式, RxMode=`0x03`) + UART_CONFIG(115200, 8N1, RxTimeout=`0x32`=50ms)
2. 通过 COM24 发送 2 字节，等待 30ms（短于 50ms 超时，未触发上报）
3. SEND_CONFIG(RxTimeout=`0x0A`=10ms) 缩短超时
4. 等待 > 10ms

**预期**: 超时修改后 RX 任务重启，新超时生效，10ms 后收到之前累积的 2 字节上报

---

### UART-51: UART_CONFIG — 5 位数据位

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**前置**: UART 通道已打开

**请求载荷**: BaudRate=115200, **DataBits=`0x05`**, StopBits=`0x01`, Parity=`0x00`, FlowControl=`0x00`

**预期响应**: Status=`0x00`

---

### UART-52: UART_CONFIG — 2 位停止位

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA2` |
| **PayloadLen** | `0x000B` |

**前置**: UART 通道已打开

**请求载荷**: BaudRate=115200, DataBits=`0x08`, **StopBits=`0x03`**, Parity=`0x00`, FlowControl=`0x00`

**预期响应**: Status=`0x00`

---

### UART-53: UART_SET_BREAK — 长时间 Break

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0xA5` |
| **PayloadLen** | `0x0002` |

**前置**: UART 通道已打开

**请求载荷**: DurationMs=`0x03E8` (1000ms)

**预期响应**: Status=`0x00`

**验证 (COM24)**: TXD 线被拉低约 1000ms

---

## 整合场景

### UART-54: CLOSE → 重新 OPEN (不同 RxMode)

| 项目 | 值 |
|:---|:---|
| **涉及的 CmdCode** | `0xA0`, `0xA1` |

**测试步骤**:
1. UART_OPEN(行模式, RxMode=`0x01`) + UART_CONFIG(115200, 8N1)
2. UART_CLOSE
3. UART_OPEN(定长模式, RxMode=`0x02`) + UART_CONFIG(115200, 8N1, RxThreshold=`0x0004`)
4. 通过 COM24 发送 8 字节
5. 验证按定长模式分块上报（收到 2 条 4 字节事件）

**预期**: 关闭后通道状态完全重置，新打开的通道按新 RxMode 工作

---

### UART-55: CONFIG 后立即 SEND (参数 mangle)

| 项目 | 值 |
|:---|:---|
| **涉及的 CmdCode** | `0xA2`, `0xA3` |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. UART_SEND("Hello")
3. UART_CONFIG(921600, 8N1)
4. UART_SEND("World")

**预期**: 两次 SEND 均返回 Status=`0x00`，配置变更即时生效

**验证 (COM24)**: 第一次在 115200 bps 收到 "Hello"，第二次在 921600 bps 收到 "World"

---

### UART-56: 并发 SEND + RECV (全双工)

| 项目 | 值 |
|:---|:---|
| **涉及的 CmdCode** | `0xA3`, `0xA4` |

**测试步骤**:
1. UART_OPEN(被动上报) + UART_CONFIG(115200, 8N1)
2. 同时执行两个操作（在测试脚本中 close-interleave）:
   - UART_SEND 100 字节数据
   - 通过 COM24 注入 50 字节数据
3. 等待所有响应和事件

**预期**:
- SEND 返回 Status=`0x00`, ActualLen=100
- 收到 RECV 事件包含 50 字节 COM24 注入数据
- 两个方向数据独立、无串扰

---

### UART-57: 完整生命周期 (集成)

| 项目 | 值 |
|:---|:---|
| **涉及的 CmdCode** | `0xA0` → `0xA2` → `0xA3` → `0xA6` → `0xA7` → `0xA1` |

**测试步骤**:
1. **OPEN**: UART_OPEN(行模式, RxMode=`0x01`) → Status=`0x00`
2. **CONFIG**: UART_CONFIG(115200, 8N1, RxThreshold=0, RxTimeout=20ms) → Status=`0x00`
3. **STATUS**: UART_STATUS → Status=`0x00`, BaudRate=115200, TxIdle=1
4. **SEND**: UART_SEND("PING\r\n") → Status=`0x00`, ActualLen=6
5. **STATUS**: UART_STATUS → Status=`0x00`, TxCount >= 6
6. **FLUSH**: UART_FLUSH(ALL) → Status=`0x00`
7. **CLOSE**: UART_CLOSE → Status=`0x00`
8. **STATUS**: UART_STATUS → Status=`0x05` (ERR_NOT_OPEN)

**预期**: 全部 8 步依次成功，无异常

---

## 补充用例索引

| 分组 | 用例编号 | 数量 | 说明 |
|:---|:---|:---|:---|
| 请求层错误路径 | UART-31 ~ UART-36 | 6 | 未打开时的 SEND/BREAK/FLUSH, 载荷过短 |
| FLUSH 子类型 | UART-37 ~ UART-39 | 3 | TX, ALL, DRAIN |
| RxFlags 错误标志 | UART-40 ~ UART-43 | 4 | BreakDetect, ParityError, FrameError, BufferOverflow |
| STATUS 深度查询 | UART-44 ~ UART-46 | 3 | TxCount, RxCount, ErrorCount |
| 边界与参数 | UART-47 ~ UART-53 | 7 | 大数据, 1200bps, 任务重启, 5N1, 2-stop, 长时间Break |
| 整合场景 | UART-54 ~ UART-57 | 4 | 重开, mangle, 全双工, 完整生命周期 |
| **合计** | | **27** | |

> 补充用例总数: **27**。加上现有 30 个用例，UART 模块测试用例总数: **57**。
