# 05. CAN 模块测试用例

> 命令码范围：`0x10-0x1F` | 模块：`mod_can` | 硬件：MCP2518FD | 对端：PCAN-USB
>
> **测试脚本**: `script/test/test_can.py`
>
> **用例总数**: Phase 1: 12 | Phase 2: 82 | **总计: 94**
>
> **环境依赖**:
> - HEX-Bridge 已烧录固件（含 CAN 模块），CAN 总线已连接 PCAN-USB 设备
> - PCANBasic.dll 位于 `files/can-files/win64/PCANBasic.dll`
> - CAN 总线两端均已正确端接 120Ω 终端电阻

---

## 测试阶段说明

CAN 模块测试分为两个阶段：

| 阶段 | 名称 | 依赖 | 状态 |
|:---|:---|:---|:---|
| **Phase 1** | PCAN | CAN module + PCAN-USB | ✅ |
| **Phase 2** | MCP integration | CAN module + PCAN-USB + MCPTransport(COM4) | ✅ script ready |

> Phase 1: PCAN standalone verification of CAN bus physical link.
> Phase 2: Full UBCP CAN command testing via COM4 MCPTransport + PCAN verification.

---

# Phase 1: PCAN 独立验证 (CAN-P1-01 ~ CAN-P1-12)

> 前提：固件 CAN 模块已烧录运行。Phase 1 可配合固件自启动 CAN 或通过 MCP CAN_OPEN
> 初始化后验证。PCAN 端直接发送/接收 CAN 帧，验证硬件链路和控制器驱动正确性。

**测试拓扑**:
```
HEX-Bridge (MCP2518FD) ←── CAN 总线 ──→ PCAN-USB ←── PC (pcan_basic.py)
    (固件自动初始化)                           (test_can.py)
```

**前置条件**:
1. 固件已烧录，`hex_config.h` 中 CAN 引脚与原理图一致
2. 固件启动时自动调用 `mod_can_init()` 初始化 SPI + MCP2518FD，进入 Normal 模式
3. 若未实现自动初始化，需通过 MCP UART0 调试口发送指令使 CAN 进入工作状态

**运行方式**:
```bash
python script/test/test_can.py --phase 1 --baud 500k
python script/test/test_can.py --phase 1 --baud 250k
python script/test/test_can.py --phase 1 --fd --baud 500k
```

---

## CAN-P1-01: CAN 总线连通性 — PCAN Ping

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 HEX-Bridge MCP2518FD 已上电、CAN 总线连通 |

**步骤**:
1. PCAN 初始化 (500k)
2. PCAN 发送标准帧 (ID=0x7E0, DLC=1, Data=0x01) — "Ping"
3. 等待 HEX-Bridge 回复 ACK（正常模式下设备会对 CAN 帧回复 ACK 位）
4. 通过 PCAN 发送/读回确认无总线错误

**预期**: PCAN 无错误状态（TEC=0, 总线正常），CAN_Write 返回 OK

**判定**: PASS ↔ `pcan_ch.get_status()` 不包含 BUSOFF / BUSHEAVY / BUSLIGHT

---

## CAN-P1-02: PCAN 发送 → 固件回环验证

| 项目 | 值 |
|:---|:---|

**前置**: 固件实现 CAN 接收 → UART0 调试输出（echo 模式）

**步骤**:
1. PCAN 发送: ID=0x100, DLC=3, Data=0x01 0x02 0x03
2. 通过 MCP UART0 (COM5) 监控固件日志，确认收到帧
3. 若固件实现 echo: 等待 CAN_RECV 通过某种方式上报

**预期**: 
- 固件日志显示 "CAN RX: ID=0x100, L=3"
- 或 MCP CAN_RECV 事件（若已通过 UBCP 上报）

**判定**: PASS ↔ 固件正确解析了 PCAN 发来的帧

---

## CAN-P1-03: 多帧连续收发

| 项目 | 值 |
|:---|:---|

**步骤**:
1. PCAN 循环发送 50 帧 (ID=0x200~0x231, DLC=1, Data=i)
2. 观察 PCAN 状态，检查是否有错误帧或发送失败
3. 观察固件调试日志（若实现），确认全部帧被接收

**预期**: 50 帧全部发送成功，PCAN 状态正常

**判定**: PASS ↔ PCAN GetStatus 返回 OK，无错误帧

---

## CAN-P1-04: 标准帧 ID 边界测试

| 项目 | 值 |
|:---|:---|

**步骤**:
1. PCAN 发送:
   - ID=0x000 (最小标准帧 ID)
   - ID=0x7FF (最大标准帧 ID)
   - ID=0x555 (中间值)
2. 每帧 DLC=1, Data=0xAA

**预期**: 3 帧全部发送成功

---

## CAN-P1-05: 扩展帧 (29-bit ID)

| 项目 | 值 |
|:---|:---|

**步骤**:
1. PCAN 发送扩展帧:
   - ID=0x00000001 (最小扩展 ID)
   - ID=0x1FFFFFFF (最大扩展 ID)
   - ID=0x1ABCDEFF (随机值)
2. `is_extended=True`, DLC=2, Data=0x55 0xAA

**预期**: 3 帧全部发送成功

---

## CAN-P1-06: 数据长度边界 — 0~8 字节

| 项目 | 值 |
|:---|:---|

**步骤**:
1. PCAN 发送 DLC=0 (空数据帧), ID=0x300
2. PCAN 发送 DLC=8 (满数据帧), ID=0x301, Data=0x00..0x07
3. 固件日志应显示正确的 DLC

**预期**: 两帧均可发送，DLC 正确

---

## CAN-P1-07: 波特率切换 — 500k→250k→500k

| 项目 | 值 |
|:---|:---|

**步骤**:
1. PCAN 初始化 500k，发送 Ping 帧成功
2. PCAN 切换为 250k（uninit + reinit），固件也需切换波特率
3. 250k 下发送 Ping 帧成功
4. PCAN 切换回 500k，发送 Ping 帧成功

**预期**: 两种波特率下均可正常通信

**自动化策略**: 
- Phase 1 脚本通过 `--baud 250k` 单独启动，验证该速率下链路正常
- 脚本自动记录每种波特率的 Ping 结果

> 注：需确保固件支持动态波特率切换（或需重新上电切换）。如仅支持固定波特率，此用例改为多轮独立运行验证：`--baud 500k` → `--baud 250k` → `--baud 500k` 各跑一次。

---

## CAN-P1-08: 远程帧 (RTR)

| 项目 | 值 |
|:---|:---|

**步骤**:
1. PCAN 发送 RTR 帧: ID=0x400, DLC=4, is_rtr=True
2. 观察固件日志确认收到 RTR 帧
3. 若固件支持自动回复，等待回复数据帧

**预期**: RTR 帧发送成功

---

## CAN-P1-09: CAN FD 帧 (64 字节)

| 项目 | 值 |
|:---|:---|

**前置**: 固件已启用 CAN FD 模式 (CiCON.FDEN=1)

**步骤**:
1. PCAN 初始化 FD 模式 (500k nominal + 2M data)
2. PCAN 发送 FD 帧: ID=0x100, DLC=15 (64 字节), data=0..63
3. 验证 PCAN 状态正常

**预期**: FD 帧发送成功，64 字节数据完整

---

## CAN-P1-10: CAN FD + BRS (波特率切换)

| 项目 | 值 |
|:---|:---|

**前置**: 固件已启用 CAN FD + BRS

**步骤**:
1. PCAN 发送 FD+BRS 帧: ID=0x101, DLC=15, data=64 字节, is_brs=True
2. 验证发送成功

**预期**: FD+BRS 帧发送成功

---

## CAN-P1-11: 总线错误检测 — ACK Error

| 项目 | 值 |
|:---|:---|

**前置**: 仅 HEX-Bridge 连接在总线上（拔掉 PCAN-USB）

**步骤**:
1. PCAN-USB 断开 → 只有 HEX-Bridge 一个节点在总线
2. 脚本调用 `pcan_ch.uninitialize()` 释放 PCAN 收发器
3. 固件端发送 CAN 帧，应检测到 ACK Error
4. 通过 UART0 调试日志观察 TEC 递增

**预期**: 固件日志报告 ACK Error / TEC > 0

**半自动实现**: 脚本控制 PCAN disconnect (`pcan_ch.uninitialize()`)，等待 2 秒后 reinitialize 恢复，期间通过 MCP CAN_STATUS 查询 TEC 变化。

---

## CAN-P1-12: 总线错误恢复

| 项目 | 值 |
|:---|:---|

**前置**: 执行 CAN-P1-11 后 TEC > 0

**步骤**:
1. 重新 reinitialize PCAN-USB（恢复总线 2 节点）
2. PCAN 持续发送 200 帧 (ID=0x700, DLC=1)，帮助固件 TEC 递减
3. 通过 CAN_STATUS 查询 TEC 归零
4. 发送 Ping 帧验证总线恢复正常

**预期**: TEC 恢复到 0，总线状态恢复正常，Ping 成功

---

## Phase 1 用例索引

| 用例 | 名称 | 前置 |
|:---|:---|:---|
| CAN-P1-01 | 总线连通性 Ping | 固件 CAN 已初始化 |
| CAN-P1-02 | PCAN→固件帧收发 | 固件 CAN echo |
| CAN-P1-03 | 多帧连续收发 (50帧) | — |
| CAN-P1-04 | 标准帧 ID 边界 (0x000/0x7FF) | — |
| CAN-P1-05 | 扩展帧 29-bit ID | — |
| CAN-P1-06 | 数据长度 0~8 字节 | — |
| CAN-P1-07 | 波特率切换 500k↔250k | 固件支持动态切换 |
| CAN-P1-08 | 远程帧 RTR | — |
| CAN-P1-09 | CAN FD 帧 64 字节 | 固件 FD 已启用 |
| CAN-P1-10 | CAN FD + BRS | 固件 FD+BRS 已启用 |
| CAN-P1-11 | ACK Error 检测 | 仅单节点 |
| CAN-P1-12 | 总线错误恢复 | TEC ≥ 128 |

---

# Phase 2: MCP 集成测试 (CAN-01 ~ CAN-82)

> ✅ **已实现**：所有用例通过 `test_can.py` 脚本自动化，直接使用 `MCPTransport(COM4)` + `UBCPBuilder` 发送 UBCP CAN 帧，无需 MCP Serial Monitor GUI 面板。
>
> **运行方式**: `python script/test/test_can.py --phase 2`
>
> MCP 命令通过 COM4 串口直接发送 UBCP CAN 帧，PCAN-USB 对端验证 CAN 总线流量。

**测试拓扑**:
```
PC(COM4) ── MCP/UBCP ──→ HEX-Bridge ←── CAN 总线 ──→ PCAN-USB ←── PC
         ←── MCP/UBCP ──     (MCP2518FD)                 (pcan_basic.py)
```

所有 MCP 命令通过 UBCP 帧头 Channel ID = `0x03` (UBCP_CH_CAN_EXT1) 指定目标通道。

---

## 通道选择

所有 CAN 命令通过帧头 Channel ID = `0x03` (UBCP_CH_CAN_EXT1) 指定目标通道。

---

## CAN-01: CAN_OPEN — 正常模式打开

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x10` |
| **Channel ID** | `0x03` |
| **PayloadLen** | `0x0001` |

**请求载荷**:
| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | Mode | `0x00` (正常模式) |

**预期响应**:
| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | ActualMode | `0x00` |
| 2-3 | RxFIFODepth | `>= 1` (如 32) |
| 4-7 | Capabilities | Bit0(CAN_FD)=1, Bit1(BRS)=1 |
| 8-9 | TxQueueSize | 16 (MCP2518FD TX FIFO 深度) |

**判定**: PASS ↔ Status=0x00, Capabilities Bit0=1

---

## CAN-02: CAN_OPEN — 重复打开（错误用例）

| 项目 | 值 |
|:---|:---|
| **前置** | 已执行 CAN-01 成功打开 |

**请求载荷**: 同 CAN-01

**预期响应**: Status=`0x0B` (ERR_ALREADY_OPEN)

---

## CAN-03: CAN_OPEN — 无效 Mode（错误用例）

**请求载荷**: Mode = `0x03` (> Loopback 最大值 0x02)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

## CAN-04: CAN_OPEN — 只听模式

**请求载荷**: Mode = `0x01` (Listen-Only)

**预期响应**: Status=`0x00`, ActualMode=`0x01`

---

## CAN-05: CAN_OPEN — 环回模式

**请求载荷**: Mode = `0x02` (Loopback)

**预期响应**: Status=`0x00`, ActualMode=`0x02`

**验证**: 发送一帧，可收到 RECV 事件回环

---

## CAN-06: CAN_OPEN — 无效 Channel（错误用例）

**Channel ID**: `0xFF`

**预期响应**: Status=`0x0A` (ERR_CHANNEL_INVALID)

---

## CAN-07: CAN_OPEN — Channel 类型不匹配（错误用例）

**Channel ID**: `0x01` (UART channel)

**预期响应**: Status=`0x16` (ERR_TYPE_MISMATCH)

---

## CAN-08 ~ CAN-11: CAN_CONFIG 波特率配置

| 用例 | 波特率索引 | 预期 |
|:---|:---|:---|
| CAN-08 | `0x06` (500k) | Status=0x00 |
| CAN-09 | `0x05` (250k) | Status=0x00 |
| CAN-10 | `0x08` (1000k) | Status=0x00 |
| CAN-11 | `0x09` (无效) | Status=0x02 或 0x16 |

---

## CAN-12: CAN_CONFIG — 启用 CAN FD 模式

**请求载荷**: BaudRateIndex=`0x06`, ConfigFlags=`0x07` (FdMode+AutoRetransmit+AutoBusOff), FdBaudRateIndex=`0x02` (2M)

**预期响应**: Status=`0x00`

**验证 (PCAN)**: FD 模式下可收发 FD 帧

---

## CAN-13: CAN_CONFIG — 自定义位时序 (Mode B)

**请求载荷**: BaudRateIndex=`0x80`, 后跟 10 字节自定义 TQ 参数

**预期响应**: Status=`0x00`

---

## CAN-14: CAN_CONFIG — 未打开时调用（错误用例）

**前置**: 执行 CAN_CLOSE

**预期响应**: Status=`0x05` (ERR_NOT_OPEN)

---

## CAN-15 ~ CAN-22: CAN_SEND 发送帧

| 用例 | 帧类型 | 关键参数 |
|:---|:---|:---|
| CAN-15 | 标准帧 | ID=0x123, DLC=3, Data=01 02 03, PCAN 验证收到 |
| CAN-16 | 扩展帧 | EXT=1, ID=0x567, DLC=8 |
| CAN-17 | RTR 帧 | RTR=1, ID=0x100, DLC=4 |
| CAN-18 | FD 帧 | FD=1, DLC=15 (64字节), PCAN 验证 |
| CAN-19 | FD + BRS | FD=1, BRS=1, DLC=10 (16字节) |
| CAN-20 | TX 满 | 连发 >16 帧 → Status=0x12 (ERR_CAN_TX_QUEUE_FULL) |
| CAN-21 | 未打开 | Status=0x05 (ERR_NOT_OPEN) |
| CAN-22 | 无效 DLC | DLC=0x10 → Status=0x02 (ERR_PARAM) |

---

## CAN-23 ~ CAN-27: CAN_RECV 接收事件上报

| 用例 | 场景 | PCAN 发送 | 验证点 |
|:---|:---|:---|:---|
| CAN-23 | 标准帧 | ID=0x456, 3 字节 | RECV 事件 CanID/Data 匹配 |
| CAN-24 | 扩展帧 | 29-bit ID=0x1ABCDEF | RECV CanID Bit31=1 |
| CAN-25 | FD 帧 | FD=1, 64 字节 | RECV CanID Bit29=1 |
| CAN-26 | FIFO 溢出 | 高速发送 >32 帧 | RxFlags Bit1(FIFOOverflow)=1 |
| CAN-27 | 帧丢失 | 持续高速发送 | RxFlags Bit0(FrameLost)=1 |

---

## CAN-28 ~ CAN-32: CAN_FILTER 过滤器

| 用例 | 过滤类型 | 配置 | 验证 |
|:---|:---|:---|:---|
| CAN-28 | 标准帧 | Mask=0x7F0, Code=0x120 | ID 0x120~0x12F 通过，0x200 被过滤 |
| CAN-29 | 扩展帧 | Mask=0x1FFFFFF0, Code=0x10000010 | 扩展 ID 通过/过滤 |
| CAN-30 | 禁用 | Enable=0 | 之前被过滤的帧恢复接收 |
| CAN-31 | FIFO2 | FIFONum=0x02 | 过滤器路由到 FIFO2 |
| CAN-32 | 无效 FIFO | FIFONum=0x03 | Status=0x02 (ERR_PARAM) |

---

## CAN-33 ~ CAN-34: CAN_STATUS 查询

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| CAN-33 | 正常状态 | Status=0x00, BusState=0x00, TEC=0, REC=0, 各计数器≥0 |
| CAN-34 | 未打开 | Status=0x05 (ERR_NOT_OPEN) |

CAN_STATUS 响应 28 字节，含 BusState / TEC / REC / TxQueueUsage / RxQueueUsage / TxCount / RxCount / LostCount / 5 类错误计数。

---

## CAN-35 ~ 36: CAN_BUS_EVENT 总线事件

| 用例 | 事件 | 触发方式 |
|:---|:---|:---|
| CAN-35 | Bus Off | 拔掉 PCAN → 固件持续发送 → TEC≥256 → BUS_EVENT 上报 + SEND 返回 ERR_CAN_BUS_OFF (0x10) |
| CAN-36 | 恢复 | 重连 PCAN → TEC 递减 → BUS_EVENT 上报 BusState=0x00, SEND 恢复正常 |

**验证点**:
- 事件帧 CmdCode=`0x17`, DIR=1, EVT=1
- BusState/PrevState 字段正确反映状态迁移
- TxErrCount/RxErrCount 反映变化时刻的计数值
- **CAN-35 追加**: Bus Off 状态下发送 SEND → Status=`0x10` (ERR_CAN_BUS_OFF)
- **CAN-36 追加**: 恢复后发送 SEND → Status=`0x00` (正常)

> 自动化：通过 USB 可控的 CAN 开关或继电器实现 PCAN 断连；或手工拔插与脚本等待配合。

**运行方式**:
```bash
# 半自动模式：脚本提示拔插时机，等待事件
python script/test/test_can.py --phase 2 --baud 500k --test bus-event
```

---

## CAN-37 ~ CAN-38: CAN_ERROR_EVENT 错误详情

| 用例 | ErrorType Bit | 错误类型 | 触发方式 | 验证字段 |
|:---|:---|:---|:---|:---|
| CAN-37 | Bit2 | ACK Error | 拔掉 PCAN，固件发送一帧 | ErrorType=0x04, TEC/REC 非零 |
| CAN-38 | Bit5 | Stuff Error | PCAN 以错误波特率发送帧 | ErrorType=0x20, ErrorLocation≠0xFF |

> 半自动：脚本控制 PCAN uninit/reinit 模拟断连；错误波特率可通过脚本切换 PCAN baud。
> 注意：CAN_ERROR_EVENT 上报频率建议固件端做限速，避免事件风暴。

**运行方式**:
```bash
python script/test/test_can.py --phase 2 --baud 500k --test error-event
```

---

## CAN-39 ~ CAN-40: CAN_CLOSE 关闭

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| CAN-39 | 正常关闭 | Status=0x00 |
| CAN-40 | 重复关闭 | Status=0x05 (ERR_NOT_OPEN) |

---

## CAN-41 ~ CAN-45: 集成场景

| 用例 | 名称 | 步骤 |
|:---|:---|:---|
| CAN-41 | 完整生命周期 | OPEN→CONFIG→STATUS→SEND→PCAN回环→RECV→STATUS→CLOSE |
| CAN-42 | CONFIG 后立即 SEND | 500k SEND→CONFIG 250k→SEND (PCAN 验证) |
| CAN-43 | 多帧连续收发 | 20 帧 SEND + 20 帧 PCAN 注入 → 40 RECV |
| CAN-44 | 关闭重开 (不同模式) | Normal→CLOSE→ListenOnly OPEN→SEND 不发送 |
| CAN-45 | FD 完整流程 | OPEN→CONFIG FD→SEND FD+BRS 64 字节→PCAN 验证 |

---

## CAN-46 ~ CAN-50: CAN FD DLC 全映射

> FD 模式下 DLC 码值 9~15 分别对应 12/16/20/24/32/48/64 字节数据。
> 补齐 DLC=9/11/12/13/14 的测试（DLC=10 见 CAN-19，DLC=15 见 CAN-18/45）。

| 用例 | DLC 值 | 实际字节数 | 验证点 |
|:---|:---|:---|:---|
| CAN-46 | 9 | 12 | PCAN 收到帧 len=12, FD flag 置位 |
| CAN-47 | 11 | 20 | PCAN 收到帧 len=20 |
| CAN-48 | 12 | 24 | PCAN 收到帧 len=24 |
| CAN-49 | 13 | 32 | PCAN 收到帧 len=32 |
| CAN-50 | 14 | 48 | PCAN 收到帧 len=48 |

**步骤** (以 CAN-46 为例):
1. OPEN + CONFIG FD 模式
2. SEND FD 帧 (ID=0x200, DLC=9, Data=12 字节)
3. PCAN 端验证: `rx.is_fd == True` 且 `len(rx.data) == 12`

**运行方式**:
```bash
python script/test/test_can.py --phase 2 --fd --baud 500k --test fd-dlc
```

---

## CAN-51 ~ CAN-52: RECV RxFlags 补充验证

> 补齐 RxFlags Bit3(FdBRS) 和 Bit4(FdESI) 的验证。

| 用例 | RxFlags 位 | Bit | 触发方式 | 预期 |
|:---|:---|:---|:---|:---|
| CAN-51 | FdBRS | Bit3 | PCAN 发送 FD+BRS 帧 | RxFlags Bit3=1 |
| CAN-52 | FdESI | Bit4 | PCAN 发送 FD 帧 (ESI) | RxFlags Bit4=1 (需 PCAN 驱动支持 ESI 发送) |

**步骤** (CAN-51):
1. OPEN + CONFIG FD 模式
2. PCAN 发送 FD+BRS 帧 (ID=0x300, 16 字节)
3. 等待 CAN_RECV 事件
4. 解析 RxFlags 字段，验证 Bit3=1

---

## CAN-53 ~ CAN-54: CAN_FILTER 补充

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| CAN-53 | FilterType=Both (0x02) | 标准帧和扩展帧 ID 范围均通过过滤 |
| CAN-54 | 未打开时设 FILTER | Status=0x05 (ERR_NOT_OPEN) |

**CAN-53 步骤**:
1. OPEN + CONFIG 500k
2. 设置 Filter: Mask=0x1FF, Code=0x100, FilterType=Both(0x02)
3. PCAN 发送标准帧 ID=0x100 → MCP 收到 RECV 事件
4. PCAN 发送扩展帧 ID=0x100 → MCP 收到 RECV 事件
5. PCAN 发送标准帧 ID=0x200 → MCP 无 RECV 事件（被过滤）

---

## CAN-55 ~ CAN-56: CAN_CONFIG 波特率全覆盖

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| CAN-55 | 仲裁段全部预设波特率 (0x00~0x08) | 全部返回 Status=0x00，PCAN 对应速率可通信 |
| CAN-56 | FD 数据段全部预设波特率 (0x01~0x05) | 全部返回 Status=0x00 |

**CAN-55 波特率枚举表**:

| 索引 | 波特率 | 索引 | 波特率 | 索引 | 波特率 |
|:---|:---|:---|:---|:---|:---|
| 0x00 | 10 kbps | 0x03 | 100 kbps | 0x06 | 500 kbps |
| 0x01 | 20 kbps | 0x04 | 125 kbps | 0x07 | 800 kbps |
| 0x02 | 50 kbps | 0x05 | 250 kbps | 0x08 | 1000 kbps |

**CAN-56 FD 波特率枚举表**:

| 索引 | 波特率 | 索引 | 波特率 |
|:---|:---|:---|:---|
| 0x01 | 1 Mbps | 0x03 | 4 Mbps |
| 0x02 | 2 Mbps | 0x04 | 5 Mbps |
| — | — | 0x05 | 8 Mbps |

> 注：对于固件不支持的波特率索引（如 800k），验证返回错误码而非异常。

---

## CAN-57: CAN_CONFIG ConfigFlags 独立位测试

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 ConfigFlags 各 bit 独立可配且互不干扰 |

**步骤**:
1. OPEN Normal
2. 分别测试以下 ConfigFlags 组合:

| 子用例 | ConfigFlags | 说明 |
|:---|:---|:---|
| 57a | `0x00` | 全部关闭（无自动重传、无自动离线恢复、无 FD） |
| 57b | `0x01` | 仅 AutoRetransmit |
| 57c | `0x02` | 仅 AutoBusOff |
| 57d | `0x04` | 仅 FdMode |
| 57e | `0x08` | 仅 FdBRS_Default |
| 57f | `0x0F` | 全部开启 |

**预期**: 所有组合返回 Status=0x00（或 ERR_NOT_SUPPORT 对于硬件不支持的能力位）

---

## CAN-58 ~ CAN-59: CAN_STATUS 补充

| 用例 | 场景 | 验证点 |
|:---|:---|:---|
| CAN-58 | Error Passive (BusState=0x01) | TEC≥128 时 BusState=0x01 |
| CAN-59 | 错误计数递增验证 | 注入错误帧后 CrcErrCount/FormErrCount/AckErrCount 增加 |

**CAN-58 步骤**:
1. 拔掉 PCAN-USB（仅 HEX-Bridge 在总线）
2. 固件持续发送帧 → TEC 递增
3. 调用 CAN_STATUS 查询，验证 TEC≥128 时 BusState 为 0x01

**CAN-59 步骤**:
1. 记录初始 STATUS 各错误计数
2. PCAN 以错误波特率发送 10 帧（触发 CRC/Form 错误）
3. 再次 STATUS 查询，验证 CrcErrCount + FormErrCount > 初始值

---

## CAN-60 ~ CAN-61: CAN_CLOSE 补充

| 用例 | 场景 | 验证点 |
|:---|:---|:---|
| CAN-60 | CLOSE 排空 TX 队列 | 发送多帧后立即 CLOSE → Status=0x00，无需等待超时 |
| CAN-61 | 快速 OPEN→CLOSE 循环 | 连续 5 次 OPEN→STATUS→CLOSE，全部成功 |

**CAN-60 步骤**:
1. OPEN Normal + CONFIG 500k
2. 连续 SEND 10 帧（ID=0x301~0x30A）
3. 立即执行 CLOSE
4. 验证 CLOSE 响应 Status=0x00（等待 TX 队列排空后才关闭）

---

## CAN-62: 全双工 SEND+RECV 并发

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 CAN 模块可同时收发，无丢帧或死锁 |

**步骤**:
1. OPEN Normal + CONFIG 500k
2. MCP 端连续 SEND 10 帧 (ID=0x400~0x409)
3. 同时 PCAN 端连续发送 10 帧 (ID=0x500~0x509)
4. MCP 端等待并统计 CAN_RECV 事件数
5. PCAN 端确认收到 10 帧

**预期**: 
- MCP 收到 ≥10 个 RECV 事件
- PCAN 收到 ≥10 帧
- 无丢帧或超时

---

## CAN-63 ~ CAN-65: 事件命令作为主机请求（错误路径）

> 参照 UART 模块模式：RECV/BUS_EVENT/ERROR_EVENT 是设备→主机事件，
> 主机不应发送这些命令码。若收到应返回 ERR_NOT_SUPPORT。

| 用例 | CmdCode | 说明 |
|:---|:---|:---|
| CAN-63 | `0x14` (CAN_RECV) | 主机尝试发送 RECV 命令 |
| CAN-64 | `0x17` (CAN_BUS_EVENT) | 主机尝试发送 BUS_EVENT 命令 |
| CAN-65 | `0x18` (CAN_ERROR_EVENT) | 主机尝试发送 ERROR_EVENT 命令 |

**步骤** (以 CAN-63 为例):
1. OPEN Normal + CONFIG 500k
2. 通过 MCP 发送 CmdCode=`0x14`, Channel=`0x03`, PayloadLen=0

**预期**: Status=`0x06` (ERR_NOT_SUPPORT)

---

## CAN-66: CAN_OPEN 空载荷

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 OPEN 命令未提供 Mode 字节时的行为 |

**步骤**:
1. 确保 CAN 通道关闭
2. 发送 CAN_OPEN (PayloadLen=0)

**预期**: Status=`0x02` (ERR_PARAM)

---

## CAN-67: CAN_CONFIG 载荷不足

| 项目 | 值 |
|:---|:---|

**步骤**:
1. OPEN Normal
2. CAN_CONFIG 仅 2 字节载荷 (需 ≥4)

**预期**: Status=`0x02` (ERR_PARAM)

---

## CAN-68: CAN_SEND 仅 CanID 无 DLC

| 项目 | 值 |
|:---|:---|

**步骤**:
1. OPEN Normal + CONFIG 500k
2. 发送 CAN_SEND 载荷仅 4 字节 (CanID 占 4B, 缺少 DLC 字节)

**预期**: Status=`0x02` (ERR_PARAM)

---

## CAN-69: CAN_FILTER FilterIndex 超范围

| 项目 | 值 |
|:---|:---|

**步骤**:
1. OPEN Normal
2. CAN_FILTER FilterIndex=`0x20` (32, MCP2518FD 最大为 31)

**预期**: Status=`0x02` (ERR_PARAM)

---

## CAN-70: CAN_STATUS 带载荷

| 项目 | 值 |
|:---|:---|

**步骤**:
1. OPEN Normal
2. 发送 CAN_STATUS 附带 1 字节随机载荷

**预期**: Status=`0x00` (忽略额外载荷, 正常返回) 或 `0x02` (ERR_PARAM, 严格模式)

---

## CAN-71: Loopback 模式自收验证

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 Loopback 模式下发送的帧可通过 RECV 事件自收 |

**步骤**:
1. CLOSE → OPEN Loopback (Mode=0x02)
2. SEND 帧: ID=0x100, Data=0x01 0x02 0x03
3. 等待 CAN_RECV 事件

**预期**: 收到 RECV 事件，CanID=0x100, Data=0x01 0x02 0x03

---

## CAN-72: ListenOnly 模式禁止发送

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 ListenOnly 模式下 SEND 被正确拒绝 |

**步骤**:
1. CLOSE → OPEN ListenOnly (Mode=0x01) + CONFIG 500k
2. SEND 帧: ID=0x100, Data=0xAA
3. PCAN 端验证未收到该帧

**预期**: SEND 返回 Status=`0x05` (ERR_NOT_OPEN, 仅 ListenOnly 不可发送) 或 Status=`0x00` 但 PCAN 端未收到

---

## CAN-73: CAN_RECV RxTimestamp 校验

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 RECV 事件中包含硬件 RxTimestamp (μs) |

**步骤**:
1. OPEN + CONFIG 500k
2. PCAN 以 10ms 间隔发送 3 帧 (ID=0x100, 0x101, 0x102, DLC=1)
3. 等待 3 个 CAN_RECV 事件
4. 解析每个事件的 RxTimestamp 字段

**预期**: 
- 每个 RECV 事件含 4 字节 RxTimestamp
- RxTimestamp[2] - RxTimestamp[1] ≈ 10ms (10000 μs ± 10%)
- RxTimestamp 值单调递增

---

## CAN-74 ~ CAN-75: CAN_SLEEP / CAN_WAKEUP

| 用例 | 命令 | 场景 | 预期 |
|:---|:---|:---|:---|
| CAN-74 | SLEEP (0x19) | 正常进入休眠 | Status=0x00, PCAN 端发现总线无应答 |
| CAN-75 | SLEEP 重复 | 休眠状态下再次 SLEEP | Status=0x04 (ERR_BUSY) |

**CAN-74 步骤**:
1. OPEN Normal + CONFIG 500k
2. SLEEP 请求
3. PCAN 发送 Ping 帧 (ID=0x7E0) → 无 ACK 应答
4. WAKEUP 请求
5. PCAN 再次 Ping → 收到 ACK
6. 验证 WAKEUP 响应: Status=0x00, ActualMode=Normal, WakeupReason Bit0(CMD_WAKEUP)=1

---

## CAN-76 ~ CAN-77: CAN_WAKEUP 唤醒

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| CAN-76 | 命令唤醒 | Status=0x00, 恢复至之前的工作模式, WakeupReason Bit0=1 |
| CAN-77 | 未休眠时唤醒 | Status=0x04 (ERR_BUSY) 或 Status=0x00 幂等 |

**CAN-76 步骤**:
1. OPEN Normal + CONFIG 500k
2. SLEEP → Status=0x00
3. WAKEUP → Status=0x00, ActualMode=0x00 (Normal), WakeupReason=0x0001
4. SEND 验证恢复正常收发: PCAN 收到帧

---

## CAN-78 ~ CAN-79: CAN_FILTER_BATCH 批量过滤器

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| CAN-78 | 批量配置 4 个过滤器 | Status=0x00, WrittenCount=4 |
| CAN-79 | 超范围 StartIndex+Count | Status=0x02 (ERR_PARAM) |

**CAN-78 步骤**:
1. OPEN Normal + CONFIG 500k
2. FILTER_BATCH: StartIndex=0, Count=4, 配置 4 个标准帧过滤器:
   - Filter 0: Code=0x100, Mask=0x7F0 → 通过 ID 0x100-0x10F
   - Filter 1: Code=0x200, Mask=0x7F0 → 通过 ID 0x200-0x20F
   - Filter 2: Code=0x300, Mask=0x7F0 → 通过 ID 0x300-0x30F
   - Filter 3: Code=0x400, Mask=0x7F0 → 通过 ID 0x400-0x40F
3. PCAN 发送 ID=0x105 (应通过) → MCP 收到 RECV 事件
4. PCAN 发送 ID=0x505 (应过滤) → MCP 无 RECV 事件

---

## CAN-80: CAN_SEND One-Shot 标志

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 CanID.Bit27 (OneShot) 禁止自动重传 |

**前置**: 仅 HEX-Bridge 在总线（拔掉 PCAN-USB，无应答节点）

**步骤**:
1. OPEN Normal + CONFIG 500k (AutoRetransmit=1, 全局启用)
2. SEND OneShot 帧: CanID=0x08000100 (Bit27=1), DLC=1, Data=0xAA
3. PCAN 拔线后: SEND 返回 Status=0x00 (提交到 TX FIFO)
4. 等待 100ms (正常重传窗口), 再次 SEND Normal 帧: CanID=0x00000100 (Bit27=0)
5. 验证 OneShot 帧不会阻塞 TX 队列 (相比于 AutoRetransmit 会持续重试)

**预期**: OneShot 帧在仲裁失败/ACK 错误后立即丢弃，不阻塞后续正常帧发送

---

## CAN-81: CAN_CONFIG Mode B 自定义 TDC

| 项目 | 值 |
|:---|:---|
| **目的** | 验证 Mode B 自定义位时序含 TDC 参数 |

**步骤**:
1. OPEN Normal
2. CONFIG Mode B: BaudRateIndex=0x80, Nominal 500k 参数, FD 2M 参数, TdcEnable=1, TdcValue=5, TdcOffset=4
3. SEND FD+BRS 帧 (ID=0x100, DLC=15, 64 字节)
4. PCAN 端验证收到完整 64 字节 FD+BRS 帧

**预期**: Status=0x00, FD+BRS 帧正常收发, 无 CRC 或格式错误

---

## CAN-82: CAN_ERROR_EVENT 限速验证

| 项目 | 值 |
|:---|:---|
| **目的** | 验证错误事件在 500ms 限速窗口内不重复上报 |

**步骤**:
1. OPEN Normal + CONFIG 500k
2. PCAN 以错误波特率 (250k) 快速发送 20 帧，触发 CRC/Form 错误
3. 统计接收到的 CAN_ERROR_EVENT 事件数量
4. 验证在 1 秒内同类型错误事件 ≤ 2 次 (500ms 限速)

**预期**: 错误事件总数远小于 20 次 (实际错误帧数)，同 ErrorType 事件被限速

---

## Phase 2 用例索引

| 分组 | 用例编号 | 数量 | 说明 |
|:---|:---|:---|:---|
| OPEN | CAN-01 ~ CAN-07 | 7 | 正常/重复/无效Mode/ListenOnly/Loopback/无效Channel/类型不匹配 |
| CONFIG | CAN-08 ~ CAN-14 | 7 | 四种波特率+/无效/FD模式/自定义时序/未打开 |
| SEND | CAN-15 ~ CAN-22 | 8 | 标准帧/扩展帧/RTR/FD帧/BRS逐帧/TX满/未打开/无效DLC |
| RECV | CAN-23 ~ CAN-27 | 5 | 标准帧/扩展帧/FD帧/FIFOOverflow/FrameLost |
| FILTER | CAN-28 ~ CAN-32 | 5 | 标准过滤/扩展过滤/禁用/FIFO2/无效FIFONum |
| STATUS | CAN-33 ~ CAN-34 | 2 | 查询正常/未打开 |
| BUS_EVENT | CAN-35 ~ CAN-36 | 2 | BusOff上报/恢复正常 |
| ERROR_EVENT | CAN-37 ~ CAN-38 | 2 | ACK错误/Stuff错误 |
| CLOSE | CAN-39 ~ CAN-40 | 2 | 正常关闭/重复关闭 |
| 集成 | CAN-41 ~ CAN-45 | 5 | 完整生命周期/mangle/多帧/重开/FD完整流程 |
| FD DLC | CAN-46 ~ CAN-50 | 5 | DLC=9(12B)/11(20B)/12(24B)/13(32B)/14(48B) |
| RECV RxFlags | CAN-51 ~ CAN-52 | 2 | FdBRS(Bit3)/FdESI(Bit4) |
| FILTER | CAN-53 ~ CAN-54 | 2 | FilterType=Both/未打开错误 |
| CONFIG | CAN-55 ~ CAN-57 | 3 | 仲裁段枚举/FD段枚举/ConfigFlags独立位 |
| STATUS | CAN-58 ~ CAN-59 | 2 | ErrorPassive/错误计数递增 |
| CLOSE | CAN-60 ~ CAN-61 | 2 | TX队列排空/快速循环 |
| 并发 | CAN-62 | 1 | 全双工SEND+RECV |
| 错误路径 | CAN-63 ~ CAN-72 | 10 | 事件命令拒收/空载荷/短载荷/DLC缺失/FilterIndex超限/STATUS带载荷/Loopback自收/ListenOnly禁发 |
| RxTimestamp | CAN-73 | 1 | RECV 事件含 RxTimestamp + 间隔校验 |
| SLEEP | CAN-74 ~ CAN-75 | 2 | 正常休眠/重复休眠 |
| WAKEUP | CAN-76 ~ CAN-77 | 2 | 命令唤醒/未休眠幂等 |
| FILTER_BATCH | CAN-78 ~ CAN-79 | 2 | 批量配置4个/超范围 |
| SEND OneShot | CAN-80 | 1 | OneShot 标志禁止自动重传 |
| CONFIG TDC | CAN-81 | 1 | Mode B 自定义位时序含 TDC |
| ERROR throttling | CAN-82 | 1 | 错误事件 500ms 限速 |
| **Phase 2 合计** | | **82** | |
| **Phase 1 合计** | CAN-P1-01 ~ CAN-P1-12 | **12** | |
| **总计** | | **94** | |
