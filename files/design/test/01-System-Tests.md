# 01. 系统管理测试用例

> 命令码范围：`0x00-0x0F` | 模块：`mod_system`

---

## SYS-01: PING — 心跳检测（正常流程）

| 项目 | 值 |
|:---|:---|
| **Step** | 握手流程第 1 步 — 连接确认 |
| **CmdCode** | `0x00` |
| **PayloadLen** | `0x0000` |

**请求载荷**: 空

**预期响应**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` (SUCCESS) |
| 1-4 | Uptime | `> 0` |
| 5 | Load | `0x00-0x64` (0-100) |
| 6 | FreeHeap | `0x01-0x64` (> 0) |

**判定**: PASS — Status=0x00, Uptime>0, Load 在合理范围内（ESP32 空闲时 0-10%）

---

## SYS-02: PING — 连续心跳（连接维持）

| 项目 | 值 |
|:---|:---|
| **Step** | 验证心跳间隔内的连续响应 |
| **CmdCode** | `0x00` |
| **PayloadLen** | `0x0000` |

**测试步骤**:
1. 发送第 1 次 PING，记录 `Uptime1`
2. 等待 200ms
3. 发送第 2 次 PING，记录 `Uptime2`

**预期**: `Uptime2 > Uptime1`, Status 均为 `0x00`

---

## SYS-03: GET_INFO — 设备识别（正常流程）

| 项目 | 值 |
|:---|:---|
| **Step** | 握手流程第 2 步 — 身份识别 |
| **CmdCode** | `0x01` |
| **PayloadLen** | `0x0000` |

**请求载荷**: 空

**预期响应**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-3 | FwVersion | `0x00, 0x01, 0x00` (v0.1.0) |
| 4-7 | SerialNum | 非零 32 位值 |
| 8-11 | ModelID | `"HXB1"` (ASCII: `0x48 0x58 0x42 0x31`) |
| 12-13 | Capabilities | Bit4 (UART)=1, 其余按实际实现 |
| 14-15 | MaxPayload | `0x0800` (2048) |
| 16 | ProtoVersion | `0x02` |

**判定**: PASS — ModelID="HXB1", ProtoVersion=0x02

---

## SYS-04: GET_CONFIG — 读取设备名称

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x02` |
| **PayloadLen** | `0x0002` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` (系统全局) |
| 1 | ConfigKey | `0x01` (DeviceName) |

**预期响应**: Status=`0x00`, ValueLen>0, Value 为 ASCII 字符串

> 注：当前固件 GET_CONFIG 未实现，预期返回 Status=`0x06` (ERR_NOT_SUPPORT)

---

## SYS-05: SET_CONFIG — 设置心跳间隔

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x03` |
| **PayloadLen** | `0x0006` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` (系统全局) |
| 1 | ConfigKey | `0x02` (HeartbeatInterval) |
| 2-3 | ValueLen | `0x0002` |
| 4-5 | Value | `0x03E8` (1000ms, 大端) |

**预期响应**: Status=`0x00` (SUCCESS) 或 `0x06` (ERR_NOT_SUPPORT, 若未实现)

---

## SYS-06: RESET — 软复位

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x04` |
| **PayloadLen** | `0x0001` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ResetType | `0x00` (软复位) |

**预期**: 响应 Status=`0x00`，之后设备重新初始化。复位后 500ms 内可重新 PING 通。

> ⚠️ 警告：执行此用例会导致设备断开，排在测试末尾执行。

---

## SYS-07: 无效命令码测试

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x06` (保留命令码) |
| **PayloadLen** | `0x0000` |

**预期响应**: Status=`0x06` (ERR_NOT_SUPPORT)

**判定**: PASS — 设备拒绝未注册的命令码（通过 msg_bus 路由验证）

---

## SYS-08: 协议版本不兼容测试

| 项目 | 值 |
|:---|:---|
| **Header.Version** | `0x01` (v1.0, 已废弃) |
| **CmdCode** | `0x00` (PING) |

**预期**: 设备丢弃帧并发送 FLOW_CONTROL 或 ERR_VERSION 响应，或直接丢弃帧不响应。

**判定**: PASS — 收到 ERR_VERSION 或帧被忽略（不导致崩溃）
