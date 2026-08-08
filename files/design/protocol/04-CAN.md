# 4. CAN 接口命令 (0x10-0x1F)

## 通道选择

所有 CAN 命令通过 **UBCP 帧头 Channel ID 字段** 指定目标 CAN 通道。固件在 OPEN 时校验通道合法性（参考 `topology_find()` 路由表）。

| Channel ID | 说明 |
|:---|:---|
| `0x03` (UBCP_CH_CAN_EXT1) | 物理 CAN FD 1 (MCP2518FD) |
| `0x04-0x0A` | 预留 |

## 命令码一览

| 命令码 | 名称 | 方向 | 说明 |
|:---|:---|:---|:---|
| `0x10` | CAN_OPEN | 请求-响应 | 打开 CAN 通道 |
| `0x11` | CAN_CLOSE | 请求-响应 | 关闭 CAN 通道 |
| `0x12` | CAN_CONFIG | 请求-响应 | 配置 CAN 参数 |
| `0x13` | CAN_SEND | 请求-响应 | 发送 CAN 帧 |
| `0x14` | CAN_RECV | 事件上报 | 接收 CAN 帧 |
| `0x15` | CAN_FILTER | 请求-响应 | 设置接收过滤器 |
| `0x16` | CAN_STATUS | 请求-响应 | 获取 CAN 总线状态 |
| `0x17` | CAN_BUS_EVENT | 事件上报 | 总线状态变化通知 |
| `0x18` | CAN_ERROR_EVENT | 事件上报 | 错误帧详情上报 |
| `0x19` | CAN_SLEEP | 请求-响应 | 进入休眠模式 |
| `0x1A` | CAN_WAKEUP | 请求-响应 | 唤醒 CAN 控制器 |
| `0x1B` | CAN_FILTER_BATCH | 请求-响应 | 批量设置接收过滤器 |
| `0x1C-0x1F` | — | — | 保留 |

---

## 4.1 CAN_OPEN (0x10) — 打开 CAN 通道

通过帧头 Channel ID 指定目标 CAN 通道。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Mode | u8 | 工作模式 (必填，PayloadLen=0 时返回 ERR_PARAM) |

### Mode 定义

| 值 | 模式 | 说明 |
|:---|:---|:---|
| 0x00 | 正常模式 | 可收可发 |
| 0x01 | 只听模式 (Listen-Only) | 仅接收，不发送 ACK |
| 0x02 | 环回模式 (Loopback) | 自发自收，用于自测 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | ActualMode | u8 | 实际工作模式 |
| 2-3 | RxFIFODepth | u16 | 接收 FIFO 深度（帧数） |
| 4-7 | Capabilities | u32 | 能力标志位 | 
| 8-9 | TxQueueSize | u16 | 发送队列深度 |

### Capabilities 位定义

| Bit | 名称 | 说明 |
|:---|:---|:---|
| 0 | CAN_FD | 1 = 支持 CAN FD |
| 1 | BRS | 1 = 支持波特率切换 |
| 2 | WUF | 1 = 支持唤醒过滤器 (Wake-Up Filter) |
| 3 | Timestamp | 1 = 支持硬件时间戳 |
| 4-31 | — | 保留 |

---

## 4.2 CAN_CLOSE (0x11) — 关闭 CAN 通道

通过帧头 Channel ID 指定目标 CAN 通道。关闭前会自动等待 TX 队列排空。

### 请求

载荷为空。

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 4.3 CAN_CONFIG (0x12) — 配置 CAN 参数

通过帧头 Channel ID 指定目标 CAN 通道。支持预定义波特率索引和自定义位时序两种模式。

### 请求

#### 模式 A：预定义波特率 (BaudRateIndex < 0x80)

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | BaudRateIndex | u8 | 波特率索引（< 0x80 为预定义模式） |
| 1 | ConfigFlags | u8 | 配置标志 |
| 2 | RxBufSize | u8 | 接收缓冲区大小（帧数，默认 32） |
| 3 | FdBaudRateIndex | u8 | CAN FD 数据段波特率索引（仅 FD 模式） |

#### 模式 B：自定义位时序 (BaudRateIndex >= 0x80)

当 BaudRateIndex >= 0x80 时，请求载荷扩展为 17 字节：

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | BaudRateIndex | u8 | 0x80-0xFF，自定义模式标志 |
| 1 | ConfigFlags | u8 | 配置标志 |
| 2 | RxBufSize | u8 | 接收缓冲区大小（帧数，默认 32） |
| 3 | FdBaudRateIndex | u8 | 置 0x00 (自定义模式下 FD 段也通过以下字段配置) |
| 4 | NomSyncSeg | u8 | 仲裁段同步段 (TQ) |
| 5 | NomPropSeg | u8 | 仲裁段传播段 (TQ) |
| 6 | NomPhaseSeg1 | u8 | 仲裁段相位段1 (TQ) |
| 7 | NomPhaseSeg2 | u8 | 仲裁段相位段2 (TQ) |
| 8 | NomSJW | u8 | 仲裁段同步跳转宽度 (TQ) |
| 9 | FdSyncSeg | u8 | FD 数据段同步段 (TQ)，0x00=不使用 FD |
| 10 | FdPropSeg | u8 | FD 数据段传播段 (TQ) |
| 11 | FdPhaseSeg1 | u8 | FD 数据段相位段1 (TQ) |
| 12 | FdPhaseSeg2 | u8 | FD 数据段相位段2 (TQ) |
| 13 | FdSJW | u8 | FD 数据段同步跳转宽度 (TQ) |
| 14 | TdcEnable | u8 | 0x00=禁用发送延迟补偿, 0x01=启用 (TDC) |
| 15 | TdcValue | u8 | TDC 补偿值 (TQ, 范围 0-63) |
| 16 | TdcOffset | u8 | TDC 二次采样点偏移 (TQ, 范围 0-63) |

TDC 仅在 CAN FD 数据段波特率 ≥ 2 Mbps 时建议启用。MCP2518FD 通过 CiTDC 寄存器配置。
当 FdSyncSeg=0x00 时（不使用 FD），TDC 字段被忽略。

**TDC 字段到 MCP2518FD TDCMOD 的映射**：

| TdcEnable | TdcValue | 含义 | 对应 TDCMOD | 说明 |
|:---|:---|:---|:---|:---|
| 0x00 | 忽略 | 禁用 TDC | 0 | 经典 CAN 或低速 FD |
| 0x01 | 0x00 | 自动模式 | 1 | MCP2518FD 硬件自动测量 Secondary Sample Point |
| 0x01 | 1-63 | 手动模式 | 2 | 使用 TdcValue 作为 TDCV，TdcOffset 作为 TDCO |

TQ (Time Quanta) 基于 MCP2518FD 时钟（通常 20 MHz 或 40 MHz），用户需根据硬件时钟频率计算采样点位置：
```
采样点(%) = (SyncSeg + PropSeg + PhaseSeg1) / (SyncSeg + PropSeg + PhaseSeg1 + PhaseSeg2) × 100
```

### BaudRateIndex（仲裁段 / 经典 CAN 波特率）

| 值 | 波特率 |
|:---|:---|
| 0x00 | 10 kbps |
| 0x01 | 20 kbps |
| 0x02 | 50 kbps |
| 0x03 | 100 kbps |
| 0x04 | 125 kbps |
| 0x05 | 250 kbps |
| 0x06 | 500 kbps (默认) |
| 0x07 | 800 kbps |
| 0x08 | 1000 kbps |
| 0x80-0xFF | 自定义位时序模式（见模式 B） |

### FdBaudRateIndex（CAN FD 数据段波特率）

| 值 | 波特率 |
|:---|:---|
| 0x00 | 不使用 FD (经典 CAN) |
| 0x01 | 1 Mbps |
| 0x02 | 2 Mbps |
| 0x03 | 4 Mbps |
| 0x04 | 5 Mbps |
| 0x05 | 8 Mbps |

### ConfigFlags

| Bit | 名称 | 说明 |
|:---|:---|:---|
| 0 | AutoRetransmit | 1 = 启用自动重传 |
| 1 | AutoBusOff | 1 = 启用自动离线恢复 |
| 2 | FdMode | 1 = 启用 CAN FD 模式 |
| 3 | FdBRS_Default | 1 = 全局默认启用 FD 波特率切换 (可被 CAN_SEND.CanID.bit28 逐帧覆盖) |
| 4-7 | — | 保留 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 4.4 CAN_SEND (0x13) — 发送 CAN 帧

通过帧头 Channel ID 指定目标 CAN 通道。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-3 | CanID | u32 | CAN ID (含标志位) |
| 4 | DLC | u8 | 数据长度 (经典: 0-8, FD: 0-64) |
| 5... | Data | u8[DLC] | 数据 |

### CanID 位定义

```
EXT=0 (标准帧):
Bit:  31     30     29     28    27    26        11   10              0
    +------+------+------+------+------+---...---+----+----------------+
    | EXT  | RTR  |  FD  | BRS  |OneSht|  保留   |  11-bit CAN ID     |
    +------+------+------+------+------+---...---+----+----------------+

EXT=1 (扩展帧):
Bit:  31     30     29     28                                      0
    +------+------+------+------+------------------------------------+
    | EXT  | RTR  |  FD  |           29-bit CAN ID                  |
    +------+------+------+------+------------------------------------+
          (BRS 和 OneShot 由 ConfigFlags 全局控制)
```

| Bit | 名称 | 适用帧类型 | 说明 |
|:---|:---|:---|:---|
| 31 | EXT | 全部 | 1 = 29 位扩展帧, 0 = 11 位标准帧 |
| 30 | RTR | 全部 | 1 = 远程帧 (RTR), 0 = 数据帧 |
| 29 | FD | 全部 | 1 = CAN FD 帧, 0 = 经典 CAN 帧 |
| 28 | BRS | 仅标准帧 (EXT=0) | 1 = 启用波特率切换 (覆盖 ConfigFlags.FdBRS_Default) |
| 27 | OneShot | 仅标准帧 (EXT=0) | 1 = 单次发送 (禁止自动重传，覆盖 ConfigFlags.AutoRetransmit) |
| 26-11 | — | 仅标准帧 (EXT=0) | 保留，写入 0 |
| 10-0 | ID(STD) | 仅标准帧 (EXT=0) | 11 位 CAN ID |
| 28-0 | ID(EXT) | 仅扩展帧 (EXT=1) | 29 位 CAN ID |

> **注意**：
> - BRS 仅在 FD=1 时有效。经典 CAN 帧忽略此位。
> - 扩展帧 (EXT=1) 无法逐帧控制 BRS 和 OneShot，需通过 ConfigFlags 全局配置。
> - OneShot 模式下，若总线拥塞导致仲裁失败，帧立即丢弃不重试。适用于诊断/错误注入场景。
> - **实现约束**：MCP2518FD 的 AutoRetransmit 是全局设置而非逐帧控制。固件实现 OneShot 时需先排空 TX FIFO，
>   临时禁用全局 AutoRetransmit，发送完成后恢复。若 TX FIFO 非空，快速连续发送 OneShot 帧之间需等待前一帧完成。

### CAN FD DLC 映射

CAN FD 模式下，DLC 值 > 8 时的实际数据长度：

| DLC 值 | 实际字节数 |
|:---|:---|
| 0-8 | 0-8 |
| 9 | 12 |
| 10 | 16 |
| 11 | 20 |
| 12 | 24 |
| 13 | 32 |
| 14 | 48 |
| 15 | 64 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-4 | TxTimestamp | u32 | 固件微秒时间戳（大端序）。与 RxTimestamp 同源可直接比较 |

---

## 4.5 CAN_RECV (0x14) — 接收 CAN 帧 (事件上报)

### 设备 → 主机主动上报

通过帧头 Channel ID 标识来源 CAN 通道。

Flags: DIR=1, EVT=1, TS=1（启用时间戳）

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-3 | CanID | u32 | CAN ID (格式同发送) |
| 4 | DLC | u8 | 数据长度 |
| 5... | Data | u8[DLC] | 接收数据 |
| 5+DLC | RxFlags | u8 | 接收状态标志 |
| 6+DLC | RxTimestamp | u32 | 固件微秒时间戳（大端序）。与 TxTimestamp 同源可直接比较时间差 |

### RxFlags

| Bit | 名称 | 说明 |
|:---|:---|:---|
| 0 | FrameLost | 1 = 检测到丢帧 |
| 1 | FIFOOverflow | 1 = FIFO 溢出 |
| 2 | ErrorFrame | 1 = 错误帧 |
| 3 | FdBRS | 1 = FD 帧使用了波特率切换 |
| 4 | FdESI | 1 = FD 帧的错误状态指示 |
| 5-7 | — | 保留 |

---

## 4.6 CAN_FILTER (0x15) — 设置接收过滤器

通过帧头 Channel ID 指定目标 CAN 通道。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | FilterIndex | u8 | 过滤器索引 (0-31，对应 MCP2518FD 32 个 Filter Object) |
| 1-4 | Mask | u32 | 掩码 (1 = 比较该位) |
| 5-8 | Code | u32 | 匹配值 |
| 9 | Enable | u8 | 0x00 = 禁用, 0x01 = 启用 |
| 10 | FilterType | u8 | 0x00 = 标准帧, 0x01 = 扩展帧, 0x02 = 两者 |
| 11 | FIFONum | u8 | 0x01 = 路由到 FIFO1, 0x02 = 路由到 FIFO2 (默认 0x01) |

> **注意**：FilterType 为 0x02 (两者) 时，MCP2518FD 利用 EXIDE 位区分标准帧和扩展帧，两种帧都会被匹配。Mask/Code 的位布局因帧类型而异：标准帧使用 bit[10:0]，扩展帧使用 bit[28:0]。

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 4.7 CAN_STATUS (0x16) — 获取 CAN 总线状态

通过帧头 Channel ID 指定目标 CAN 通道。

### 请求

载荷为空。

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | BusState | u8 | 总线状态 |
| 2 | TxErrCount | u8 | 发送错误计数 |
| 3 | RxErrCount | u8 | 接收错误计数 |
| 4-5 | TxQueueUsage | u16 | 发送队列已用帧数 |
| 6-7 | RxQueueUsage | u16 | 接收队列已用帧数 |
| 8-9 | TxCount | u16 | 总发送帧数 |
| 10-11 | RxCount | u16 | 总接收帧数 |
| 12-13 | LostCount | u16 | 丢帧计数 |
| 14-15 | TxQueueSize | u16 | 发送队列总容量（帧数） |
| 16-17 | RxQueueSize | u16 | 接收队列总容量（帧数） |
| 18-19 | CrcErrCount | u16 | CRC 错误累计次数 |
| 20-21 | FormErrCount | u16 | 格式错误累计次数 |
| 22-23 | AckErrCount | u16 | ACK 错误累计次数 |
| 24-25 | BitErrCount | u16 | 位错误累计次数 |
| 26-27 | StuffErrCount | u16 | 填充错误累计次数 |

### BusState 定义

| 值 | 状态 | 说明 |
|:---|:---|:---|
| 0x00 | 正常 (Error Active) | 错误计数 < 128 |
| 0x01 | 被动错误 (Error Passive) | 错误计数 ≥ 128 |
| 0x02 | 总线关闭 (Bus Off) | 错误计数 ≥ 256 |
| 0x03 | 恢复中 (Recovering) | 正在从 Bus Off 恢复 |

---

## 4.8 CAN_BUS_EVENT (0x17) — 总线状态变化通知 (事件上报)

当 CAN 总线状态发生变化（进入 Error Passive、Bus Off 或恢复正常）时，设备主动上报此事件。
通过帧头 Channel ID 标识来源 CAN 通道。

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1, TS=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | BusState | u8 | 当前总线状态（同 CAN_STATUS.BusState） |
| 1 | PrevState | u8 | 变化前的总线状态 |
| 2 | TxErrCount | u8 | 变化时的发送错误计数 |
| 3 | RxErrCount | u8 | 变化时的接收错误计数 |

> **触发条件**：BusState 在 0x00↔0x01↔0x02 之间变化时上报，主机无需轮询即可感知总线异常。

---

## 4.9 CAN_ERROR_EVENT (0x18) — 错误帧详情上报 (事件上报)

当 CAN 控制器检测到总线错误帧时，设备主动上报错误详情。通过帧头 Channel ID 标识来源 CAN 通道。

> **速率限制**：固件端对 CAN_ERROR_EVENT 实施最小上报间隔控制，默认 500 ms 内同一 ErrorType 组合不重复上报。
> 该间隔可通过 SET_CONFIG (ConfigGroup=0x00, ConfigKey=0x04 CAN_ErrorThrottleMs) 调整。
> 若总线噪声导致错误风暴，固件优先保证 UBCP 链路正常，错误事件可能被丢弃。

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1, TS=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | ErrorType | u8 | 错误类型位图 |
| 1 | TxErrCount | u8 | 发生错误时的发送错误计数 |
| 2 | RxErrCount | u8 | 发生错误时的接收错误计数 |
| 3 | ErrorLocation | u8 | 错误发生时所在位置 |

### ErrorType 位图

| Bit | 名称 | 说明 |
|:---|:---|:---|
| 0 | CRC | CRC 定界符错误 |
| 1 | Form | 格式错误 |
| 2 | ACK | ACK 错误（无节点应答） |
| 3 | BitRecessive | 隐性位错误（发送隐性但检测到显性） |
| 4 | BitDominant | 显性位错误（发送显性但检测到隐性） |
| 5 | Stuff | 位填充错误 |
| 6 | RxWarning | TEC/REC ≥ 96 (警告阈值) |
| 7 | BusOffRecovery | Bus Off 恢复计数完成一次 |

### ErrorLocation 定义

| 值 | 位置 | 说明 |
|:---|:---|:---|
| 0x00 | IDLE | 空闲期间 |
| 0x01 | SOF | 帧起始 |
| 0x02 | ID段 | 标识符段 |
| 0x03 | 控制段 | IDE/r0/FDF/BRS/ESI/DLC |
| 0x04 | 数据段 | 数据字段 |
| 0x05 | CRC段 | CRC 序列 + 定界符 |
| 0x06 | ACK段 | ACK Slot + 定界符 |
| 0x07 | EOF | 帧结束 (7 个隐性位) |
| 0x08 | IFS | 帧间间隔 |
| 0xFF | 未知 | 无法确定位置 |

---

## 4.10 CAN_SLEEP (0x19) — 进入休眠模式

通过帧头 Channel ID 指定目标 CAN 通道。使 CAN 控制器进入低功耗休眠状态，收发器关闭。
休眠期间 MCP2518FD 停止总线活动，可通过 CAN_WAKEUP 命令或总线唤醒事件 (WUF) 唤醒。

### 请求

载荷为空。

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

> **注意**：睡眠模式下 CAN 收发器关闭，接收功能完全停止。唤醒后 CAN_RECV 事件自动恢复上报。
> 若控制器已在休眠状态，再次发送 SLEEP 命令返回 ERR_BUSY (0x04)。

---

## 4.11 CAN_WAKEUP (0x1A) — 唤醒 CAN 控制器

通过帧头 Channel ID 指定目标 CAN 通道。使 CAN 控制器从休眠状态恢复至休眠前的工作模式。
唤醒后保留之前的 CONFIG 配置和 FILTER 设置。

### 请求

载荷为空。

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | ActualMode | u8 | 唤醒后的实际工作模式 |
| 2-3 | WakeupReason | u16 | 唤醒原因位图 |

### WakeupReason 位图

| Bit | 名称 | 说明 |
|:---|:---|:---|
| 0 | CMD_WAKEUP | 由 UBCP CAN_WAKEUP 命令唤醒 |
| 1 | CAN_BUS | 由 CAN 总线活动唤醒 (WUF) |
| 2 | SPI_CMD | 由 SPI 指令唤醒 |
| 3-15 | — | 保留 |

---

## 4.12 CAN_FILTER_BATCH (0x1B) — 批量设置接收过滤器

通过帧头 Channel ID 指定目标 CAN 通道。一次性配置多个过滤器对象，减少 UBCP 往返次数。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | StartIndex | u8 | 起始 Filter Index (0-31) |
| 1 | Count | u8 | 配置数量 (1-32, StartIndex+Count ≤ 32) |
| 2... | Filters[] | 可变 | Count × 12 字节的 Filter 条目数组 |

### Filter 条目结构 (每个 12 字节)

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-3 | Mask | u32 | 掩码 (1 = 比较该位) |
| 4-7 | Code | u32 | 匹配值 |
| 8 | Enable | u8 | 0x00 = 禁用, 0x01 = 启用 |
| 9 | FilterType | u8 | 0x00 = 标准帧, 0x01 = 扩展帧, 0x02 = 两者 |
| 10 | FIFONum | u8 | 0x01 = FIFO1, 0x02 = FIFO2 |
| 11 | Pad | u8 | 对齐填充 (写入 0x00) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | WrittenCount | u8 | 成功写入的过滤器数量 |

> **注意**：
> - 若 StartIndex + Count > 32，返回 ERR_PARAM (0x02)。
> - 若部分写入失败（例如硬件故障），WrittenCount 报告实际成功数量，Status 返回 ERR_HAL_FAIL (0x17)。
> - 写入成功后过滤器立即生效，无需额外指令。
