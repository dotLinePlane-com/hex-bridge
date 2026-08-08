# 7. CAN 模块设计

## 7.1 概述

CAN 模块管理 MCP2518FD CAN FD 控制器，实现 UBCP 协议中的 CAN 命令组 (0x10-0x1F)。

### 硬件配置

| 参数 | 值 |
|:---|:---|
| 控制器 | MCP2518FD |
| 接口 | SPI（VSPI / SPI3） |
| SCK 引脚 | GPIO 14 |
| MOSI 引脚 | GPIO 13 |
| MISO 引脚 | GPIO 36 (GPI，外接 10kΩ 上拉) |
| CS 引脚 | GPIO 15 (Strapping，外接 10kΩ 上拉) |
| INT 引脚 | GPIO 39 (GPI，外接 10kΩ 上拉) |
| 时钟频率 | 20 MHz (外部晶振) |
| SPI 速率 | 10 MHz |
| 默认波特率 | 500 kbps |
| RX 缓冲区 | 32 帧（可配置） |
| TX 缓冲区 | 16 帧（硬件 FIFO） |

### 通道分配

| Channel ID | 设备 | 说明 |
|:---|:---|:---|
| `0x03` (UBCP_CH_CAN_EXT1) | MCP2518FD #1 | 板载 CAN FD 控制器 |

## 7.2 命令实现状态

| 命令码 | 名称 | 状态 |
|:---|:---|:---|
| `0x10` | CAN_OPEN | 待实现 |
| `0x11` | CAN_CLOSE | 待实现 |
| `0x12` | CAN_CONFIG | 待实现 |
| `0x13` | CAN_SEND | 待实现 |
| `0x14` | CAN_RECV | 待实现（中断驱动事件上报） |
| `0x15` | CAN_FILTER | 待实现 |
| `0x16` | CAN_STATUS | 待实现 |
| `0x17` | CAN_BUS_EVENT | 待实现（总线状态变化主动上报） |
| `0x18` | CAN_ERROR_EVENT | 待实现（错误帧详情上报） |
| `0x19` | CAN_SLEEP | 待实现（休眠模式） |
| `0x1A` | CAN_WAKEUP | 待实现（唤醒控制器） |
| `0x1B` | CAN_FILTER_BATCH | 待实现（批量过滤器） |

## 7.3 架构设计

### 7.3.1 任务分配

| 任务名称 | 栈大小 | 优先级 | 职责 |
|:---|:---|:---|:---|
| `can_int_task` | 4096 | 9 | GPIO39 中断 → 读取 MCP2518FD 事件 → FIFO 分发 |
| `can_rx_proc` | 4096 | 8 | 接收队列 → UBCP CAN_RECV 事件帧编码上报 |

使用 FreeRTOS 队列解耦中断服务例程（ISR）和协议处理任务：

```
MCP2518FD RXINT (GPIO39) ──ISR──→ xQueueSendFromISR(can_event_queue)
                                          │
                                    can_int_task
                                          │
                              ┌───────────┴───────────┐
                              │  MCAN_ReadEvent()      │
                              │  ─ if RX data ready:  │
                              │      → can_rx_queue    │
                              │  ─ if error detected: │
                              │      → send error evt  │
                              │  ─ if bus state change:│
                              │      → send bus event  │
                              └───────────┬───────────┘
                                          │
                                    can_rx_proc
                                          │
                              UBCP CAN_RECV 事件帧 → msg_bus
```

### 7.3.2 中断处理

MCP2518FD INT 引脚 (GPIO39) 为开漏输出，配置为下降沿触发中断。中断线可能由以下事件拉低：
- RX FIFO 非空（收到新帧）
- TX FIFO 可用（发送完成）
- 总线错误检测
- 唤醒事件

ISR 中仅发送队列通知，不执行 SPI 读写操作（SPI 不可在 ISR 中使用）。

### 7.3.3 SPI 驱动

使用 ESP-IDF 的 `driver/spi_master.h` API：

```
SPI Bus:  VSPI_HOST (SPI3)
Mode:     0 (CPOL=0, CPHA=0)
Speed:    10 MHz
CS:       GPIO15 (手动控制，非 SPI 自动 CS)
```

MCP2518FD 的 SPI 指令格式：

| 指令 | 格式 | 说明 |
|:---|:---|:---|
| RESET | `0x00 0x00` | 复位控制器 |
| READ | `0x03 <addr_h> <addr_l>` + N byte | 读取寄存器 |
| WRITE | `0x02 <addr_h> <addr_l>` + N byte | 写入寄存器 |
| READ_CRC | `0x0B <addr_h> <addr_l>` + N byte + CRC2 | 读取带 CRC 校验 |
| WRITE_CRC | `0x0A <addr_h> <addr_l>` + N byte + CRC2 | 写入带 CRC 校验 |
| WRITE_SAFE | `0x0C <addr_h> <addr_l>` + N byte + CRC2 | 安全写入（写后回读校验） |

## 7.4 命令处理流程

### 7.4.1 CAN_OPEN (0x10) — 打开通道

```
CAN_OPEN(Mode) 到达:
  1. 校验 Channel ID 合法性 (topology_find)
  2. 校验 device_type == UBCP_DEV_TYPE_CAN
  3. 校验通道未打开 (ERR_ALREADY_OPEN)
  4. 初始化 SPI 总线 (spi_bus_initialize)
  5. 添加 MCP2518FD 设备 (spi_bus_add_device)
  6. 复位 MCP2518FD (发送 RESET 指令)
  7. 配置 GPIO39 中断 (gpio_isr_handler_add)
  8. 创建 can_int_task + can_rx_proc
  9. 创建 can_event_queue + can_rx_queue
  10. 设置 Mode (Normal/ListenOnly/Loopback)
  11. 返回 Status + ActualMode + RxFIFODepth + Capabilities + TxQueueSize
```

### 7.4.2 CAN_CLOSE (0x11) — 关闭通道

```
CAN_CLOSE() 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 等待 TX FIFO 排空（轮询 TXREQ 标志）
  3. 设置 MCP2518FD 为 Configuration Mode
  4. 删除 can_int_task + can_rx_proc
  5. 删除 can_event_queue + can_rx_queue
  6. 移除 GPIO39 中断
  7. 移除 SPI 设备
  8. 返回 Status
```

### 7.4.3 CAN_CONFIG (0x12) — 配置参数

```
CAN_CONFIG(参数) 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 解析 BaudRateIndex / ConfigFlags / RxBufSize / FdBaudRateIndex
  3. 若 BaudRateIndex >= 0x80: 解析自定义位时序（模式 B）
  4. 设置 MCP2518FD 为 Configuration Mode
  5. 写入位时序寄存器（CiNBTCFG / CiDBTCFG）
  6. 若 FdBaudRateIndex ≥ 0x02 (FD ≥ 2M): 查表写入 CiTDC（模式 A 自动）
     若模式 B 且 TdcEnable=1: 根据 TdcValue 选择自动/手动模式写入 CiTDC
  7. 配置 Tx/Rx FIFO 深度、自动重传等
  8. 恢复为 Normal Mode (或原 Mode)
  9. 返回 Status
```

### 7.4.4 CAN_SEND (0x13) — 发送帧

```
CAN_SEND(CanID, DLC, Data) 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 校验 DLC 范围
  3. 若 CanID.OneShot=1: 等待 TX FIFO 排空 (MCP2518FD 的 AutoRetransmit 为全局控制)
  4. 检查 TX FIFO (CiFIFOSTAx.TFNRFNIF) 是否满
     → 满则返回 ERR_CAN_TX_QUEUE_FULL
  5. 构建 TEF (Transmit Event FIFO) 时间戳捕获使能
  6. 若 OneShot=1: 临时禁用 AutoRetransmit → 写入帧 → 设置 TXREQ → 等待发送完成 → 恢复 AutoRetransmit
  7. 若 OneShot=0: 写入 CiFIFOCONx / CiTXD → 设置 TXREQ
  8. 读取发送时间戳（因 ERR-1，使用 esp_timer_get_time() 记录，而非 TEF 硬件时间戳）
  9. 返回 Status + TxTimestamp (μs, 与 RxTimestamp 同源可直接比较)
```

> **OneShot 限制**：MCP2518FD 的 AutoRetransmit 是全局位 (CiCON.RETRAN)，非逐帧控制。
> 因此 OneShot 帧必须先排空 TX FIFO 后单独发送，确保不会误影响队列中其他正常帧。

### 7.4.5 CAN_RECV (0x14) — 接收上报

由 `can_rx_proc` 任务从 `can_rx_queue` 取帧后自动上报：

```
can_rx_proc:
  loop:
    wait can_rx_queue (超时 100ms)
    if rx_msg:
      → 读取 MCP2518FD RX 数据 (CiRXD): CanID + DLC + Data + RX_FLAGS + Timestamp
      → 映射 MCP2518FD RX flags → UBCP RxFlags
      → 读取 MCP2518FD Time Base Counter (CiTBC, 0x034→高16位 + 0x038→低16位)
        → 组合为 32-bit μs 时间戳
      → 构建 UBCP CAN_RECV 事件帧 (含 RxTimestamp)
      → msg_bus_send_frame(&evt)
      更新 RxCount 计数
      if 丢帧检测 (FIFOOverflow):
        → 更新 LostCount
```

**RxTimestamp 来源**：固件统一使用 `esp_timer_get_time()` (μs) 作为时间戳时钟源，
确保 TxTimestamp 和 RxTimestamp 可直接比较时间差。
MCP2518FD 的 Time Base Counter (CiTBC) 可作为辅助参考，但不直接用于协议字段。
实现方式：`can_rx_proc` 从 `can_rx_queue` 取帧时立即调用 `esp_timer_get_time()` 记录接收时刻。

### 7.4.6 CAN_FILTER (0x15) — 过滤器

```
CAN_FILTER(FilterIndex, Mask, Code, Enable, FilterType, FIFONum) 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 校验 FilterIndex < 32
  3. 校验 FIFONum ∈ {0x01, 0x02}
  4. 设置 MCP2518FD CiFLTOBJ 寄存器 (Mask/Code/Enable)
  5. 配置滤波对象连接到的 FIFO (CiFIFOCONx.FSEL)
  6. 返回 Status
```

### 7.4.7 CAN_STATUS (0x16) — 查询状态

```
CAN_STATUS() 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 读取 CiTREC (TEC/REC)
  3. 读取 CiFIFOSTAx (TX/RX Queue Usage)
  4. 读取 CiBDIAG0 (错误类型计数)
  5. 汇总 TxCount/RxCount/LostCount
  6. 返回完整状态载荷 (28 字节)
```

## 7.5 MCP2518FD 寄存器速查

| 寄存器 | 地址 | 说明 |
|:---|:---|:---|
| CiCON | 0x000 | 主控制寄存器 |
| CiNBTCFG | 0x004 | 仲裁段位时序 |
| CiDBTCFG | 0x008 | 数据段位时序 (FD) |
| CiTDC | 0x00C | 发送延迟补偿 (FD) |
| CiTREC | 0x034 | TEC/REC 错误计数 |
| CiBDIAG0 | 0x038 | 总线诊断寄存器 0 |
| CiBDIAG1 | 0x03C | 总线诊断寄存器 1 |
| CiTEFCON | 0x040 | TEF 控制 |
| CiTEFSTA | 0x044 | TEF 状态 |
| CiFIFOCONx | 0x050/0x58 | FIFO 控制 (x=1,2) |
| CiFIFOSTAx | 0x054/0x5C | FIFO 状态 |
| CiFIFOUAx | 0x058+ | FIFO 用户地址 |
| CiFLTOBJ | 0x1F0+ | 滤波对象 (0-31) |
| CiMASK | 0x1F4+ | 掩码寄存器 |
| CiTXD | 0x400+ | TX 队列数据区 |
| CiRXD | 0x600+ | RX FIFO 数据区 |

## 7.6 位时序计算

MCP2518FD 使用 20 MHz 外部晶振，系统时钟通过 PLL 倍频至 **40 MHz** (CAN FD 需要)。以下所有计算基于 `Fosc = 40 MHz`。

### 公式

```
TQ = (BRP + 1) / Fosc = (BRP + 1) / 40,000,000
波特率 = Fosc / ((BRP + 1) × TotalTQ)
TotalTQ = SYNC(1) + PropSeg + PhaseSeg1 + PhaseSeg2
采样点% = (SYNC + PropSeg + PhaseSeg1) / TotalTQ × 100
```

### MCP2518FD NBTCFG / DBTCFG 寄存器格式 (32-bit)

```
Bit:  31    24 | 23 22    16 | 15 14      8 | 7         0
    +----------+-------------+-------------+------------+
    |  BRP     |      SJW    |    TSEG2    |   TSEG1    |
    +----------+-------------+-------------+------------+

TSEG1 (寄存器值) = PropSeg + PhaseSeg1 - 1
TSEG2 (寄存器值) = PhaseSeg2 - 1
SJW  (寄存器值) = SJW - 1
```

### 仲裁段 (Nominal) 波特率查找表 — CiNBTCFG

所有速率统一 75% 采样点，TQ 总数 20（800k 除外为 25 TQ，72% 采样点）：

| 索引 | 波特率 | BRP | TQ (ns) | PropSeg | PhaseSeg1 | PhaseSeg2 | SJW | TotalTQ | SP% | NBTCFG 值 |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0x00 | 10 kbps | 199 | 5000 | 7 | 7 | 5 | 4 | 20 | 75% | `0xC703040D` |
| 0x01 | 20 kbps | 99 | 2500 | 7 | 7 | 5 | 4 | 20 | 75% | `0x6303040D` |
| 0x02 | 50 kbps | 39 | 1000 | 7 | 7 | 5 | 4 | 20 | 75% | `0x2703040D` |
| 0x03 | 100 kbps | 19 | 500 | 7 | 7 | 5 | 4 | 20 | 75% | `0x1303040D` |
| 0x04 | 125 kbps | 15 | 400 | 7 | 7 | 5 | 4 | 20 | 75% | `0x0F03040D` |
| 0x05 | 250 kbps | 7 | 200 | 7 | 7 | 5 | 4 | 20 | 75% | `0x0703040D` |
| 0x06 | 500 kbps | 3 | 100 | 7 | 7 | 5 | 4 | 20 | 75% | `0x0303040D` |
| 0x07 | 800 kbps | 1 | 50 | 8 | 9 | 7 | 4 | 25 | 72% | `0x01030610` |
| 0x08 | 1000 kbps | 1 | 50 | 7 | 7 | 5 | 4 | 20 | 75% | `0x0103040D` |

### CAN FD 数据段波特率查找表 — CiDBTCFG

FD 数据段使用 BRP=0 (TQ=25 ns)，无需重新计算 BRP：

| 索引 | 波特率 | BRP | PropSeg | PhaseSeg1 | PhaseSeg2 | SJW | TotalTQ | SP% | DBTCFG 值 | 建议 TDC |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0x01 | 1 Mbps | 0 | 15 | 16 | 8 | 4 | 40 | 80% | `0x0003071E` | 选配 |
| 0x02 | 2 Mbps | 0 | 7 | 8 | 4 | 4 | 20 | 80% | `0x0003030E` | 建议 |
| 0x03 | 4 Mbps | 0 | 3 | 4 | 2 | 2 | 10 | 80% | `0x00010106` | 必须 |
| 0x04 | 5 Mbps | 0 | 2 | 3 | 2 | 2 | 8 | 75% | `0x00010104` | 必须 |
| 0x05 | 8 Mbps | 0 | 1 | 2 | 1 | 1 | 5 | 80% | `0x00000002` | 必须 |

### 7.6.1 TDC (Transmitter Delay Compensation) 配置

CAN FD 在数据段波特率 ≥ 2 Mbps 时需要启用 TDC 补偿发送延迟。
MCP2518FD 通过 **CiTDC** 寄存器配置，建议使用自动模式 (TDCMOD=1)。

**CiTDC 寄存器格式 (32-bit)**:

```
Bit:  31  22 | 21   16 | 15 14  8 | 7  2 | 1    0
    +--------+---------+----------+------+--------+
    | 保留   |  TDCV   |    TDCO  | 保留 | TDCMOD |
    +--------+---------+----------+------+--------+
```

- **TDCMOD[1:0]** = 0: 禁用, 1: 自动模式 (MCP2518FD 自动测量 SSP), 2: 手动模式
- **TDCV[5:0]** = 手动模式下 TDC 补偿值 (TQ), 自动模式下忽略
- **TDCO[5:0]** = 二次采样点偏移 (TQ)

**推荐 CiTDC 值 (自动模式)**:

| FD 数据波特率 | TDCMOD | TDCO | CiTDC 值 | 说明 |
|:---|:---|:---|:---|:---|
| ≤ 1 Mbps | 1 | 0 | `0x00000001` | 低频下 TDC 选配 |
| 2 Mbps | 1 | 4 | `0x00000401` | 推荐启用 |
| 4 Mbps | 1 | 5 | `0x00000501` | 必须启用 |
| 5 Mbps | 1 | 6 | `0x00000601` | 必须启用 |
| 8 Mbps | 1 | 7 | `0x00000701` | 必须启用 |

> **实现注意**：CAN_CONFIG 命令在模式 A（预定义）下，固件根据 FdBaudRateIndex 自动查表配置
> CiTDC。模式 B（自定义位时序）下，由协议载荷中的 TdcEnable/TdcValue/TdcOffset 字段控制。
> 若 FdBaudRateIndex=0x00（经典 CAN），跳过 TDC 配置。

### 7.4.8 CAN_SLEEP (0x19) — 进入休眠

```
CAN_SLEEP() 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 校验未处于休眠 (ERR_BUSY)
  3. 等待 TX FIFO 排空
  4. 设置 MCP2518FD 为 Sleep 模式 (CiCON.REQOP=001)
  5. 禁用 GPIO39 中断 (避免误唤醒)
  6. 记录休眠前的工作模式 (ModeSnapshot)
  7. 返回 Status
```

### 7.4.9 CAN_WAKEUP (0x1A) — 唤醒

```
CAN_WAKEUP() 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 发送 SPI 指令唤醒 MCP2518FD (拉低 CS 产生边沿，或写 CiCON.REQOP)
  3. 等待振荡器起振 (OSC 稳定，轮询 CiCON.OPMOD)
  4. 恢复至 ModeSnapshot 工作模式
  5. 重新启用 GPIO39 中断
  6. 读取 WakeupReason (检查 CiCON.WAKIF + SPI 指令来源)
  7. 返回 Status + ActualMode + WakeupReason
```

> 注意：MCP2518FD 也可被 CAN 总线 WUF (Wake-Up Filter) 唤醒。此时由 GPIO39 中断触发
> can_int_task，固件自动执行恢复流程并上报 CAN_WAKEUP 事件（作为主动事件）。

### 7.4.10 CAN_FILTER_BATCH (0x1B) — 批量过滤器

```
CAN_FILTER_BATCH(StartIndex, Count, Filters[]) 到达:
  1. 校验通道已打开 (ERR_NOT_OPEN)
  2. 校验 StartIndex + Count ≤ 32 (ERR_PARAM)
  3. 设置 MCP2518FD 为 Configuration Mode
  4. for i = 0 to Count-1:
     a. 写入 CiFLTOBJ[StartIndex+i] (Mask/Code)
     b. 配置 CiMASK[StartIndex+i] (Enable/FilterType)
     c. 验证写入值 (回读比对)
     任一失败 → 中断循环, 返回 ERR_HAL_FAIL + WrittenCount=i
  5. 恢复原工作模式
  6. 返回 Status + WrittenCount
```

## 7.7 错误处理

### 总线状态监控

`can_int_task` 在每次中断处理时读取 CiTREC：

| TEC / REC | 状态 | 动作 |
|:---|:---|:---|
| < 128 | Error Active | — |
| ≥ 128 | Error Passive | 上报 CAN_BUS_EVENT(Error Passive) |
| ≥ 256 | Bus Off | 上报 CAN_BUS_EVENT(Bus Off)；若 AutoBusOff=1 则自动恢复 |

### 错误帧诊断

当检测到错误时，`can_int_task` 读取 CiBDIAG0 寄存器并上报 CAN_ERROR_EVENT：

| CiBDIAG0 Bit | 错误类型 | UBCP ErrorType Bit |
|:---|:---|:---|
| NCRCERR | CRC 错误 | Bit 0 |
| NFRMERR | 格式错误 | Bit 1 |
| NACKERR | ACK 错误 | Bit 2 |
| NSTUFERR | 填充错误 | Bit 5 |
| NBIT0ERR | 显性位错误 | Bit 4 |
| NBIT1ERR | 隐性位错误 | Bit 3 |

### 错误事件限速

CAN_ERROR_EVENT 上报频率受固件端限速器控制：
- 默认最小上报间隔：**500 ms**（可通过 CONFIG_KEY `CAN_ERROR_THROTTLE_MS` 调整）
- 同一 `ErrorType` 组合在限速窗口内不重复上报
- 若总线噪声导致错误风暴，事件在达到限速上限后被丢弃，优先保证 UBCP 链路正常

## 7.8 SPI 事务并发保护

MCP2518FD 的 CS 引脚 (GPIO15) 为手动控制。以下场景需访问 SPI 总线：

| 场景 | 发起者 | 上下文 |
|:---|:---|:---|
| RX 中断响应读取 CAN 帧 | `can_int_task` | FreeRTOS Task (prio 9) |
| 命令处理：CONFIG/SEND/FILTER/STATUS | `handle_cmd` (msg_bus 回调) | FreeRTOS Task (prio 5, MCP transport) |
| 周期性错误/状态巡检 | `can_int_task` | FreeRTOS Task (prio 9) |

### 互斥方案

使用 FreeRTOS 互斥锁 (`SemaphoreHandle_t can_spi_mutex`) 保护所有 SPI 事务：

```
所有 SPI 操作必须走 mcp2518fd_spi_lock() / mcp2518fd_spi_unlock() 包装：
  - mcp2518fd_spi_lock():   xSemaphoreTake(can_spi_mutex, pdMS_TO_TICKS(100))
  - mcp2518fd_spi_unlock(): xSemaphoreGive(can_spi_mutex)
```

**优先级反转风险**：MCP transport 任务 (prio 5) 在持有 SPI 锁期间可能被 `can_int_task` (prio 9)
抢占。由于 FreeRTOS 互斥锁自带优先级继承，此风险可控。
SPI 单次事务耗时约 10-50 μs（10 MHz, ≤64 字节），不会长时间阻塞。

## 7.9 内存分配策略

### 缓冲区容量

| 缓冲区 | 容量 | 帧大小 (worst) | 总内存 | 位置 |
|:---|:---|:---|:---|:---|
| `can_rx_queue` (FreeRTOS) | 32 句柄 | 4 字节/句柄 | 128 B | DRAM |
| `can_event_queue` (FreeRTOS) | 16 句柄 | 4 字节/句柄 | 64 B | DRAM |
| RX 帧池 (mempool) | 32 帧 | 80 字节/帧 | 2560 B | **PSRAM** |
| TX 帧缓冲 (栈上) | 1 次 1 帧 | 80 字节/帧 | 80 B | 栈 |

**总计**：~192 B DRAM + ~2560 B PSRAM

### 分配策略

- **RX 帧池**：使用静态 `uint8_t[N][80]` 数组，放置于 `.ext_ram_bss` 段（PSRAM）。
  每帧 80 字节 = 4B CanID + 1B DLC + 64B Data + 1B RxFlags + 4B RxTimestamp + 6B 预留对齐。
  通过 FreeRTOS 消息队列传递帧指针（零拷贝），避免 memcpy。
- **TX 帧**：在 `handle_cmd` 上下文中栈上构造 SPI 发送缓冲区，不占用持久内存。
- **状态变量** (TxCount/RxCount/LostCount/TEC/REC 等)：全局 `static` 变量，DRAM (.bss)。
- 若 PSRAM 不可用（`ESP_SPIRAM_SIZE == 0`），降级使用 DRAM。

## 7.10 Bus Off 恢复状态机

MCP2518FD 在 TEC ≥ 256 时自动进入 Bus Off 状态。恢复流程如下：

```
Bus Off 触发:
  1. 上报 CAN_BUS_EVENT(BusState=0x02, PrevState=当前状态, TEC, REC)
  2. 若 ConfigFlags.AutoBusOff=1:
     a. MCP2518FD 自动启动恢复序列（CiCON.ABAT=1）
     b. 固件轮询 CiTREC，检测 TEC 降至 127 以下 (每 50ms 检查一次)
     c. 上报 CAN_BUS_EVENT(BusState=0x03 "恢复中")
     d. TEC 归零后，MCP2518FD 自动切回 Normal 模式
     e. 上报 CAN_BUS_EVENT(BusState=0x00, PrevState=0x03)
  3. 若 ConfigFlags.AutoBusOff=0:
     a. 保持 Bus Off 状态，等待主机通过 CAN_CONFIG 重新配置
     b. 或主机主动 CLOSE → OPEN 重置控制器
  4. Bus Off 期间：
     - CAN_SEND 返回 ERR_CAN_BUS_OFF (0x10)
     - CAN_RECV 继续尝试上报（实际上不会收到帧）
     - 主机可通过 CAN_STATUS 查询恢复进度
```

**MCP2518FD 恢复机制**：CAN 规范要求检测到 128 次 11 位隐性位 (Bus Idle) 后恢复。
MCP2518FD 在 ABAT=1 时自动执行此序列。典型恢复时间：128 × 11 × 2μs ≈ 2.8 ms @ 500k。

## 7.11 MCP2518FD 硬件勘误注意事项

MCP2518FD 已知硅片问题 (Rev A/B)，固件需规避：

| 编号 | 问题描述 | 规避措施 |
|:---|:---|:---|
| ERR-1 | TEF (Transmit Event FIFO) 在特定条件下可能丢失尾部条目 | 固件不依赖 TEF 获取 TX 时间戳；改用软件记录的 `esp_timer_get_time()` |
| ERR-2 | CiBDIAG0 错误计数器在读后不清零（与文档描述不符） | 固件维护软件累加计数器；CiBDIAG0 值仅用于事件触发判断，不依赖硬件清零 |
| ERR-3 | 写 CiNBTCFG / CiDBTCFG 后需额外延迟才能生效 | `mcp2518fd_write_reg()` 后增加 100 μs 延时，再读取验证写入值 |
| ERR-4 | SPI CRC (READ_CRC/WRITE_CRC) 在高速模式 (≥8 MHz) 下偶发校验失败 | 默认使用普通 READ/WRITE 指令；CRC 指令仅用于关键配置写入后验证 |
| ERR-5 | FD 模式下连续高速接收 (>85% 总线负载) 可能导致 CiFIFOSTA 溢出标志滞后 | 在 can_rx_proc 中增加软件溢出判断：若 RX 帧池空闲数 < 4 → 主动丢弃旧帧并设置 RxFlags.FIFOOverflow |

> 勘误规避代码集中在 `mcp2518fd.c` 中实现，标注 `/* Errata ERR-N */` 注释。

## 7.12 源文件

| 文件 | 说明 |
|:---|:---|
| `modules/mod_can.h` | 接口声明 |
| `modules/mod_can.c` | 完整实现 |
| `modules/mcp2518fd.h` | MCP2518FD 寄存器定义与驱动 |
| `modules/mcp2518fd.c` | MCP2518FD SPI 操作封装 |
