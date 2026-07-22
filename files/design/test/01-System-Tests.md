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

**预期响应**: Status=`0x00` (SUCCESS)

---

## SYS-10: GET_CONFIG — 读取 UartChannelCount (只读)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x02` |
| **PayloadLen** | `0x0002` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` (系统全局) |
| 1 | ConfigKey | `0x10` (UartChannelCount) |

**预期响应**: Status=`0x00`, ValueLen=`0x0001`, Value[0]=`0x01` (1 个 UART 通道)

---

## SYS-11: GET_CONFIG — 读取 CanChannelCount (只读)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x02` |
| **PayloadLen** | `0x0002` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` (系统全局) |
| 1 | ConfigKey | `0x11` (CanChannelCount) |

**预期响应**: Status=`0x00`, ValueLen=`0x0001`, Value[0]=`0x02` (2 个 CAN 通道)

---

## SYS-12: GET_CONFIG — 读取 FlowControlEnable (默认值)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x02` |
| **PayloadLen** | `0x0002` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` (系统全局) |
| 1 | ConfigKey | `0x03` (FlowControlEnable) |

**预期响应**: Status=`0x00`, ValueLen=`0x0001`, Value[0]=`0x01` (默认启用)

---

## SYS-13: SET_CONFIG — 修改 DeviceName 并回读验证

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x03` → 写入, `0x02` → 回读 |
| **PayloadLen** | `0x000B` |

**请求载荷 (SET)**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` |
| 1 | ConfigKey | `0x01` (DeviceName) |
| 2-3 | ValueLen | `0x0007` |
| 4+ | Value | `"TestDev"` (ASCII) |

**预期响应**: Status=`0x00`

**回读验证**: 发送 GET_CONFIG(ConfigGroup=0x00, ConfigKey=0x01)，验证 Value=`"TestDev"`。

---

## SYS-14: SET_CONFIG — 修改 HeartbeatInterval 并回读验证

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x03` → 写入, `0x02` → 回读 |

**请求载荷 (SET)**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` |
| 1 | ConfigKey | `0x02` (HeartbeatInterval) |
| 2-3 | ValueLen | `0x0002` |
| 4-5 | Value | `0x03E8` (1000ms, 大端) |

**预期响应**: Status=`0x00`

**回读验证**: 发送 GET_CONFIG(ConfigGroup=0x00, ConfigKey=0x02)，验证 Value=`0x03E8` (1000)。

---

## SYS-15: SET_CONFIG — 拒绝写入只读 Key (UartChannelCount)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x03` |
| **PayloadLen** | `0x0005` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` |
| 1 | ConfigKey | `0x10` (UartChannelCount, 只读) |
| 2-3 | ValueLen | `0x0001` |
| 4 | Value | `0x02` |

**预期响应**: Status=`0x0C` (ERR_PERMISSION) — 设备应拒绝写入只读配置项

---

## SYS-06: RESET — 软复位 + SYS_BOOT_EVENT 验证

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x04` |
| **PayloadLen** | `0x0001` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ResetType | `0x00` (软复位) |

**测试步骤**:
1. 发送软复位命令，等待 Status=`0x00` 响应
2. 设备复位后重新初始化，在 `mcp_transport_init()` 完成后主动发送 `SYS_BOOT_EVENT (0x06)` 事件帧
3. 等待接收事件帧，超时 5 秒

**SYS_BOOT_EVENT 事件帧预期**:
| 字段 | 预期值 |
|:---|:---|
| Flags | `DIR=1, EVT=1, TS=1` |
| CmdCode | `0x06` |
| Payload[0] ResetReason | `0x03` (SW_RESET, 软件复位) |
| Payload[1] BootStatus | `0x00` (正常启动) |
| Timestamp | 近期的微秒时间戳, `> 0` |

> ⚠️ 警告：执行此用例会导致设备断开，排在测试末尾执行。复位后设备会在 500ms 内重新上线。

---

## SYS-07: GET_TOPOLOGY — 获取硬件拓扑（正常流程）

| 项目 | 值 |
|:---|:---|
| **Step** | 握手流程第 3 步 — 拓扑发现 |
| **CmdCode** | `0x07` |
| **PayloadLen** | `0x0000` |

**请求载荷**: 空

**预期响应**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` (SUCCESS) |
| 1 | ChannelCount | `>= 1` |
| 2 | ChannelID[0] | `0x01` (UBCP_CH_UART_EXT1) |
| 3 | DeviceType[0] | `0x01` (UBCP_DEV_TYPE_UART) |

**判定**: PASS — Status=0x00, ChannelCount>0, 首个通道为 UART 扩展口 (ID=1, Type=1)

---

## SYS-08: 协议版本不兼容测试

| 项目 | 值 |
|:---|:---|
| **Header.Version** | `0x01` (v1.0, 已废弃) |
| **CmdCode** | `0x00` (PING) |

**预期**: 设备丢弃帧并发送 FLOW_CONTROL 或 ERR_VERSION 响应，或直接丢弃帧不响应。

**判定**: PASS — 收到 ERR_VERSION 或帧被忽略（不导致崩溃）

---

## SYS-09: SYS_BOOT_EVENT — 启动事件结构验证

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x06` |
| **方向** | 设备 → 主机（主动上报） |
| **Flags** | `DIR=1, EVT=1, TS=1` |

**测试方法**: 连接后立即检查串口缓冲区中是否已有待接收的启动事件帧（设备上电/复位后发出的第一帧），或通过 SYS-06 软复位触发。

**预期事件帧载荷**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | ResetReason | 合法的 ResetReason 值 (0x01/0x03/0x05/0x07/0x08/0x09/0x0D/0xFF) |
| 1 | BootStatus | `0x00` (正常启动) |

**判定**: PASS — PayloadLen=2, ResetReason 在合法范围内, BootStatus=0x00, 时间戳有效

---

## SYS-16: GET_CONFIG — 读取 McpBaudRate (默认值)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x02` |
| **PayloadLen** | `0x0002` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` (系统全局) |
| 1 | ConfigKey | `0x12` (McpBaudRate) |

**预期响应**: Status=`0x00`, ValueLen=`0x0004`, Value 为 u32 大端序波特率（默认 `0x000E1000` = 921600 或编译期 `HEX_MCP_UART_BAUD` 值）

**判定**: PASS — Status=0x00, Value 为非零 u32 值

---

## SYS-17: SET_CONFIG — 修改 McpBaudRate 并回读验证

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x03` → 写入, `0x02` → 回读 |
| **PayloadLen** | `0x0008` |

**请求载荷 (SET)**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` |
| 1 | ConfigKey | `0x12` (McpBaudRate) |
| 2-3 | ValueLen | `0x0004` |
| 4-7 | Value | `0x0001C200` (115200, 大端) |

**预期响应**: Status=`0x00`

**回读验证**: 发送 GET_CONFIG(ConfigGroup=0x00, ConfigKey=0x12)，验证 Value=`0x0001C200` (115200)。

> ⚠️ 注意：波特率写入 NVS 后需通过 RESET(0x00) 软复位才能使新波特率在当前 MCP 链路上生效。写入后设备立即返回 SUCCESS，但当前链路波特率不变。

**判定**: PASS — Status=0x00, 回读 Value 与写入一致

---

## SYS-18: SET_CONFIG — 拒绝无效 McpBaudRate

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x03` |
| **PayloadLen** | `0x0008` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` |
| 1 | ConfigKey | `0x12` (McpBaudRate) |
| 2-3 | ValueLen | `0x0004` |
| 4-7 | Value | `0x000000C8` (200, 远低于 9600 下限) |

**预期响应**: Status=`0x02` (ERR_PARAM) — 设备应拒绝无效波特率

---

## SYS-19: SET_CONFIG — 拒绝过高的 McpBaudRate

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x03` |
| **PayloadLen** | `0x0008` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | ConfigGroup | `0x00` |
| 1 | ConfigKey | `0x12` (McpBaudRate) |
| 2-3 | ValueLen | `0x0004` |
| 4-7 | Value | `0x05F5E100` (100000000, 远高于 5000000 上限) |

**预期响应**: Status=`0x02` (ERR_PARAM) — 设备应拒绝无效波特率

---

## SYS-20: SET_CONFIG → 软复位 → 新波特率验证 (端到端)

| 项目 | 值 |
|:---|:---|
| **测试类型** | 端到端集成测试 |
| **依赖** | 需主机能在复位后以新波特率重新连接 |

**测试步骤**:
1. 发送 SET_CONFIG(ConfigKey=0x12, Value=115200)，记录原始波特率
2. 收到 SUCCESS 后，发送 RESET(0x00) 软复位
3. 主机以新波特率 115200 重新打开串口
4. 等待 SYS_BOOT_EVENT 事件帧
5. 发送 PING + GET_INFO 验证链路正常
6. 发送 GET_CONFIG(ConfigKey=0x12) 验证波特率为 115200
7. 恢复默认波特率（SET_CONFIG 回原始值 + RESET）

**预期**: 复位后设备以 115200 bps 通信，所有命令正常响应。

> ⚠️ 警告：此用例会断开并重新连接 MCP 链路，排在测试末尾执行。
