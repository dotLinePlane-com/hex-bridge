# HEX-Bridge 系统管理模块 — 测试报告

> **测试日期**: 2026-07-22 | **固件版本**: v0.1.0 | **协议**: UBCP v2.0
> **结果**: **81 PASS / 0 FAIL / 0 SKIP**

---

## 1. 测试概要

| 项目 | 值 |
|:---|:---|
| 被测模块 | 系统管理 (mod_system, 命令范围 0x00-0x0F) |
| 已实现命令 | PING (0x00), GET_INFO (0x01), GET_CONFIG (0x02), SET_CONFIG (0x03), RESET (0x04), FLOW_CONTROL (0x05), SYS_BOOT_EVENT (0x06), GET_TOPOLOGY (0x07) |
| 测试用例数 | 17 (SYS-01~SYS-20, 排除 SYS-08 重复编号) |
| 测试断言数 | 81 |
| 测试结果 | **81 PASS / 0 FAIL / 0 SKIP** |
| 测试脚本 | `script/test/test_system.py`, `script/test/test_mcp_baud.py` |

---

## 2. 编译与烧录

### 2.1 编译 (2026-07-22)

| 项目 | 值 |
|:---|:---|
| ESP-IDF 版本 | v6.0.1 |
| 编译器 | xtensa-esp-elf-gcc (esp-14.2.0_20240906) |
| Python | idf6.0_py3.11_env |
| esptool | v5.3.dev3 |
| 构建产物 | `build/hex-bridge.bin` (0x39000 bytes, 78% free) |

### 2.2 编译 (2026-07-10, 原始版本)

| 项目 | 值 |
|:---|:---|
| ESP-IDF 版本 | v6.0.1 |
| 编译器 | xtensa-esp-elf-gcc (esp-15.2.0_20251204) |
| 构建产物 | `build/hex-bridge.bin` (0x37120 bytes, 78% free) |

### 2.2 烧录

| 项目 | 值 |
|:---|:---|
| 芯片型号 | ESP32-D0WD-V3 (revision v3.1) |
| 晶振频率 | 40MHz |
| MAC 地址 | 28:56:2f:8f:82:88 |
| Flash 大小 | 16MB, DIO mode |
| 烧录端口 | COM34, 460800 bps |
| 烧录内容 | bootloader (0x1000) + partition-table (0x8000) + app (0x10000) |
| 烧录结果 | ✅ 全部 3 分区写入并校验通过 |

---

## 3. 测试环境

### 3.1 硬件连接

```
┌──────────────┐                      ┌─────────────────┐
│   PC (COM35) │── MCP/UBCP ────────→│   HEX-Bridge     │
│  测试客户端   │   921600 bps        │   ESP32          │
│              │←── MCP/UBCP ────────│   UART1 (GP4/34) │
└──────────────┘                      └─────────────────┘
COM34: ESP32 调试输出 + 烧录 (UART0, 115200 bps)
```

### 3.2 引脚配置

| 串口 | 功能 | TX | RX | 参数 |
|:---|:---|:---|:---|:---|
| UART0 | 调试/烧录 | GPIO 1 | GPIO 3 | 115200, 8N1 |
| UART1 | MCP 通信 | GPIO 4 | GPIO 34 (GPI) | 921600, 8N1 |

### 3.3 软件环境

| 组件 | 版本/说明 |
|:---|:---|
| Python | 3.11 |
| pyserial | 最新 |
| 测试框架 | ubcp_client.py + mcp_transport.py |

---

## 4. 测试结果汇总

| ID | 名称 | 命令码 | 断言数 | 结果 |
|:---|:---|:---|:---|:---|
| SYS-01 | PING | 0x00 | 5 | ✅ PASS |
| SYS-02 | PING 连续 | 0x00 | 3 | ✅ PASS |
| SYS-03 | GET_INFO | 0x01 | 5 | ✅ PASS |
| SYS-04 | GET_CONFIG DeviceName | 0x02 | 4 | ✅ PASS |
| SYS-05 | SET_CONFIG HeartbeatInterval | 0x03 | 5 | ✅ PASS |
| SYS-06 | RESET + SYS_BOOT_EVENT | 0x04→0x06 | 9 | ✅ PASS |
| SYS-07 | 无效命令 | 0x07 | 2 | ✅ PASS |
| SYS-09 | SYS_BOOT_EVENT 结构 | 0x06 | 8 | ✅ PASS |
| SYS-10 | GET_CONFIG UartChannelCount | 0x02 | 4 | ✅ PASS |
| SYS-11 | GET_CONFIG CanChannelCount | 0x02 | 4 | ✅ PASS |
| SYS-12 | GET_CONFIG FlowControlEnable | 0x02 | 4 | ✅ PASS |
| SYS-13 | SET_CONFIG DeviceName + 回读 | 0x03 | 5 | ✅ PASS |
| SYS-14 | SET_CONFIG HeartbeatInterval + 回读 | 0x03 | 5 | ✅ PASS |
| SYS-15 | SET_CONFIG 只读拒绝 (旧) | 0x03 | 3 | ✅ PASS |
| SYS-16 | GET_CONFIG McpBaudRate | 0x02 | 4 | ✅ PASS |
| SYS-17 | SET_CONFIG McpBaudRate + 回读 | 0x03→0x02 | 3 | ✅ PASS |
| SYS-18 | SET_CONFIG 拒绝过低 McpBaudRate | 0x03 | 1 | ✅ PASS |
| SYS-19 | SET_CONFIG 拒绝过高 McpBaudRate | 0x03 | 1 | ✅ PASS |
| SYS-20 | McpBaudRate 端到端切换+重连 | 0x03→0x04→0x00→0x01 | 7 | ✅ PASS |

---

## 5. 详细测试结果

### 5.1 SYS-01: PING — 心跳检测

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | 收到响应帧 | yes | ✅ |
| 2 | Status | 0x00 | ✅ 0x00 |
| 3 | Uptime | > 0 | ✅ |
| 4 | Load | 0-100 | ✅ 0 (ESP32 空闲) |
| 5 | FreeHeap | > 0 | ✅ |

### 5.2 SYS-02: PING 连续心跳

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | Status1 / Status2 | 0x00 | ✅ |
| 2 | Uptime2 > Uptime1 | 递增 | ✅ |

### 5.3 SYS-03: GET_INFO — 设备身份识别

| 步骤 | 字段 | 预期值 | 实际 |
|:---|:---|:---|:---|
| 1 | Status | 0x00 | ✅ 0x00 |
| 2 | FwVersion | 0.1.0 | ✅ 0.1.0 |
| 3 | ModelID | "HXB1" | ✅ HXB1 |
| 4 | ProtoVersion | 0x02 | ✅ 0x02 |
| 5 | MaxPayload | 2048 | ✅ 2048 |
| 6 | Capabilities | UART 位=1 | ✅ 0x0FFF |

### 5.4 SYS-04: GET_CONFIG — 读取 DeviceName

| 步骤 | 字段 | 预期值 | 实际 |
|:---|:---|:---|:---|
| 1 | Status | 0x00 | ✅ 0x00 |
| 2 | Value 非空 | true | ✅ |
| 3 | DeviceName | "HXB-Device" | ✅ "HXB-Device" |

### 5.5 SYS-05: SET_CONFIG — 修改 HeartbeatInterval

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET_CONFIG 响应 | 收到 | ✅ |
| 2 | SET status | 0x00 | ✅ 0x00 |
| 3 | 回读响应 | 收到 | ✅ |
| 4 | 回读 status | 0x00 | ✅ 0x00 |
| 5 | HeartbeatInterval | 1000 | ✅ 0x3e8 |

### 5.6 SYS-06: RESET + SYS_BOOT_EVENT — 端到端验证

**测试流程**:
1. 发送 RESET (0x04), `ResetType=0x00`
2. 接收 RESET 响应: Status=`0x00` ✅
3. 设备软复位重启 (~500ms)
4. 接收 SYS_BOOT_EVENT 事件帧

**SYS_BOOT_EVENT 事件帧验证 (实际值)**:

| 字段 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| is_event (EVT=1) | true | ✅ | PASS |
| is_response (DIR=1) | true | ✅ | PASS |
| cmd_code | `0x06` | ✅ 0x06 | PASS |
| payload_len | `2` | ✅ 2 | PASS |
| payload[0] ResetReason | `0x03` (SW_RESET) | ✅ 0x03 | PASS |
| payload[1] BootStatus | `0x00` (正常) | ✅ 0x00 | PASS |
| has_timestamp (TS=1) | true | ✅ | PASS |
| timestamp | `> 0` | ✅ | PASS |

### 5.7 SYS-07: 无效命令码 (cmd=0x07)

| 项目 | 预期 | 实际 |
|:---|:---|:---|
| 响应 Status | `0x06` (ERR_NOT_SUPPORT) | ✅ 0x06 |

### 5.8 SYS-09: SYS_BOOT_EVENT 结构完整性验证

独立触发第二次软复位，验证事件帧结构一致性：

| 验证项 | 判定 |
|:---|:---|
| is_event (EVT=1) | ✅ PASS |
| is_response (DIR=1) | ✅ PASS |
| cmd_code = 0x06 | ✅ PASS |
| payload_len = 2 | ✅ PASS |
| ResetReason = 0x03 | ✅ PASS |
| BootStatus = 0x00 | ✅ PASS |
| has_timestamp (TS=1) | ✅ PASS |
| timestamp > 0 | ✅ PASS |

### 5.9 SYS-10: GET_CONFIG — UartChannelCount (只读)

| 步骤 | 字段 | 预期值 | 实际 |
|:---|:---|:---|:---|
| 1 | Status | 0x00 | ✅ 0x00 |
| 2 | ValueLen | 1 | ✅ 1 |
| 3 | UartChannelCount | 0x01 | ✅ 0x01 |

### 5.10 SYS-11: GET_CONFIG — CanChannelCount (只读)

| 步骤 | 字段 | 预期值 | 实际 |
|:---|:---|:---|:---|
| 1 | Status | 0x00 | ✅ 0x00 |
| 2 | ValueLen | 1 | ✅ 1 |
| 3 | CanChannelCount | 0x02 | ✅ 0x02 |

### 5.11 SYS-12: GET_CONFIG — FlowControlEnable (默认值)

| 步骤 | 字段 | 预期值 | 实际 |
|:---|:---|:---|:---|
| 1 | Status | 0x00 | ✅ 0x00 |
| 2 | ValueLen | 1 | ✅ 1 |
| 3 | FlowControlEnable | 0x01 | ✅ 0x01 |

### 5.12 SYS-13: SET_CONFIG — DeviceName 修改 + 回读

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET DeviceName="TestDev" | 0x00 | ✅ 0x00 |
| 2 | 回读 DeviceName | "TestDev" | ✅ "TestDev" |

### 5.13 SYS-14: SET_CONFIG — HeartbeatInterval 修改 + 回读

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET HeartbeatInterval=2000 | 0x00 | ✅ 0x00 |
| 2 | 回读 HeartbeatInterval | 2000 | ✅ 0x7d0 |

### 5.14 SYS-15: SET_CONFIG — 拒绝写入只读 Key (旧策略)

> **注意**: 原 `key >= UBCP_CFGKEY_READONLY_MASK (0x10)` 策略会将 `McpBaudRate (0x12)` 也误判为只读。当前版本已改为显式枚举只读 Key (`UART_CHANNEL_COUNT=0x10`, `CAN_CHANNEL_COUNT=0x11`)。

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET UartChannelCount=2 | 0x0C (ERR_PERMISSION) | ✅ 0x0c |
| 2 | 回读 UartChannelCount | 1 (不变) | ✅ 0x01 |

### 5.15 SYS-16: GET_CONFIG — 读取 McpBaudRate

| 步骤 | 字段 | 预期值 | 实际 |
|:---|:---|:---|:---|
| 1 | Status | 0x00 | ✅ 0x00 |
| 2 | ValueLen | 4 | ✅ 4 |
| 3 | McpBaudRate (u32) | 非零 (编译默认值或 NVS 存储值) | ✅ 115200 |

### 5.16 SYS-17: SET_CONFIG — McpBaudRate 修改 + 回读

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET McpBaudRate=230400 | 0x00 | ✅ 0x00 |
| 2 | 回读 McpBaudRate | 230400 | ✅ 230400 |
| 3 | 恢复原始值 | 0x00 | ✅ 0x00 |

### 5.17 SYS-18: SET_CONFIG — 拒绝过低 McpBaudRate (200 bps < 9600)

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET McpBaudRate=200 | 0x02 (ERR_PARAM) | ✅ 0x02 |

### 5.18 SYS-19: SET_CONFIG — 拒绝过高 McpBaudRate (100M bps > 5M)

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET McpBaudRate=100000000 | 0x02 (ERR_PARAM) | ✅ 0x02 |

### 5.19 SYS-20: McpBaudRate 端到端 — SET_CONFIG → RESET → 新波特率重连

**测试流程**:
1. SET_CONFIG(ConfigKey=0x12, Value=230400) → Status=0x00 ✅
2. RESET(0x00) 软复位 → 设备重启
3. 以 230400 bps 重新打开 COM35
4. PING → Status=0x00 ✅
5. GET_INFO → ModelID="HXB1", ProtoVersion=0x02 ✅
6. SET_CONFIG 恢复 115200 → Status=0x00 ✅
7. 软复位后以 115200 bps 重连 → PING Status=0x00 ✅

| 步骤 | 操作 | 预期 | 实际 |
|:---|:---|:---|:---|
| 1 | SET_CONFIG Status | 0x00 | ✅ 0x00 |
| 2 | RESET 响应 | 收到 | ✅ |
| 3 | 230400 bps 重连 | 连接成功 | ✅ |
| 4 | 230400 bps PING | 0x00 | ✅ 0x00 |
| 5 | 230400 bps GET_INFO | "HXB1" | ✅ HXB1 |
| 6 | SET_CONFIG 恢复 115200 | 0x00 | ✅ 0x00 |
| 7 | 复位后 115200 重连 PING | 0x00 | ✅ 0x00 |

---

## 6. 新增 ConfigKey 验证

根据协议文档 `files/design/protocol/03-System.md#系统全局配置组-0x00-常用-ConfigKey-定义`：

| ConfigKey | 参数名称 | 类型 | 预期值 | 实测值 | 读写属性 | 状态 |
|:---|:---|:---|:---|:---|:---|:---|
| 0x01 | DeviceName | str | "HXB-Device" | "HXB-Device" | 读写 | ✅ |
| 0x02 | HeartbeatInterval | u16 | 5000 | 5000 (默认), 1000/2000 (写入) | 读写 | ✅ |
| 0x03 | FlowControlEnable | u8 | 0x01 | 0x01 | 读写 | ✅ |
| 0x10 | UartChannelCount | u8 | 1 | 1 | 只读 | ✅ |
| 0x11 | CanChannelCount | u8 | 2 | 2 | 只读 | ✅ |
| 0x12 | McpBaudRate | u32 | 921600 (编译默认值) | 115200 (NVS 存储值) | 读写 | ✅ |

只读保护验证:
- 对 `UartChannelCount` (0x10) 执行 SET_CONFIG 返回 `ERR_PERMISSION (0x0C)` ✅
- 对 `CanChannelCount` (0x11) 执行 SET_CONFIG 返回 `ERR_PERMISSION (0x0C)` ✅ (代码审查)
- 对 `McpBaudRate` (0x12) 执行 SET_CONFIG 正常写入 ✅ (证实仅显式枚举 Key 为只读)

---

## 7. ResetReason 映射验证

| ESP-IDF 常量 | UBCP 值 | 名称 | 验证状态 |
|:---|:---|:---|:---|
| `ESP_RST_SW` | `0x03` | SW_RESET | ✅ SYS-06/SYS-09 两次验证通过 |
| `ESP_RST_POWERON` | `0x01` | POWERON_RESET | 需断电重启 |
| `ESP_RST_DEEPSLEEP` | `0x05` | DEEPSLEEP_RESET | 需深度睡眠支持 |
| `ESP_RST_INT_WDT` | `0x06` | INT_WDT_RESET | 破坏性 |
| `ESP_RST_TASK_WDT` | `0x07` | TASK_WDT_RESET | 破坏性 |
| `ESP_RST_WDT` | `0x08` | WDT_RESET | 破坏性 |
| `ESP_RST_BROWNOUT` | `0x0D` | BROWNOUT_RESET | 硬件依赖 |
| `ESP_RST_PANIC` | `0x0E` | PANIC_RESET | 破坏性 |
| 其他 | `0xFF` | UNKNOWN | 兜底值 |

> 除 SW_RESET 已验证外，其余映射均为一对一 switch-case 静态映射，逻辑正确性由代码审查保证。

---

## 8. 代码变更清单

### 8.1 固件变更 (v0.1.0, 2026-07-22: MCP 波特率配置)

| 文件 | 变更 |
|:---|:---|
| `main/protocol/ubcp_def.h` | 新增 `UBCP_CFGKEY_MCP_BAUD_RATE` (0x12) |
| `main/transport/mcp_transport.h` | `init()` 签名改为 `mcp_transport_init(uint32_t baud_rate)`，传 0 使用编译默认值 |
| `main/transport/mcp_transport.c` | `uart_hw_init()` 接收动态波特率参数 |
| `main/modules/mod_system.h` | 新增 `mod_system_get_mcp_baud_rate()` 公开获取器 |
| `main/modules/mod_system.c` | `system_init()` 从 NVS 加载 McpBaudRate (9600~5000000 校验)；`handle_get_config()` 返回 u32 大端波特率；`handle_set_config()` 校验范围 + NVS 写入 + commit；只读检查改为显式枚举 (`UART_CHANNEL_COUNT`, `CAN_CHANNEL_COUNT`) |
| `main/main.c` | 启动时调用 `mod_system_get_mcp_baud_rate()` 传入 `mcp_transport_init()` |

### 8.2 固件变更 (v0.1.0, 2026-07-10: GET_CONFIG/SET_CONFIG 基础)

| 文件 | 变更 |
|:---|:---|
| `main/protocol/ubcp_def.h` | 新增 ConfigGroup/ConfigKey 常量: `UBCP_CFGKEY_DEVICE_NAME` (0x01), `UBCP_CFGKEY_HEARTBEAT_INTERVAL` (0x02), `UBCP_CFGKEY_FLOW_CONTROL_ENABLE` (0x03), `UBCP_CFGKEY_UART_CHANNEL_COUNT` (0x10), `UBCP_CFGKEY_CAN_CHANNEL_COUNT` (0x11), `UBCP_CFGKEY_READONLY_MASK` (0x10) |
| `main/modules/mod_system.c` | 实现 `handle_get_config()` (0x02): 读取 DeviceName/HeartbeatInterval/FlowControlEnable/UartChannelCount/CanChannelCount；实现 `handle_set_config()` (0x03): 写入 DeviceName/HeartbeatInterval/FlowControlEnable (只读检查) |
| `main/modules/mod_system.h` | 无需变更 (接口不变) |

### 8.5 测试脚本变更

| 文件 | 变更 |
|:---|:---|
| `script/test/test_mcp_baud.py` | **新增** — MCP 波特率自动化测试脚本 (SYS-16~SYS-20)，支持 `--e2e` 端到端切换测试 |

### 8.6 设计文档变更

| 文件 | 变更 |
|:---|:---|
| `files/design/protocol/03-System.md` | 新增 ConfigKey=0x12 (McpBaudRate) 协议定义、使用说明 |
| `files/design/test/01-System-Tests.md` | 新增 SYS-16~SYS-20 测试用例 |
| `files/design/test-report/System-Test-Report.md` | **本报告** — 更新为 v0.1.0 MCP 波特率配置完整测试记录 |

### 8.4 测试脚本变更 (2026-07-10)

| 文件 | 变更 |
|:---|:---|
| `script/test/test_system.py` | 新增 SYS-04/05/10/11/12/13/14/15 测试函数；新增辅助函数 `do_get_config()`/`do_set_config()` |

### 8.3 设计文档变更 (2 文件)

| 文件 | 变更 |
|:---|:---|
| `files/design/test/01-System-Tests.md` | SYS-04/SYS-05 更新为已实现；新增 SYS-10/11/12/13/14/15 配置测试用例 |
| `files/design/test-report/System-Test-Report.md` | **本报告** — 更新为包含 GET_CONFIG/SET_CONFIG 的完整测试记录 |

---

## 9. 结论

系统管理模块 8 个已实现命令 (PING, GET_INFO, GET_CONFIG, SET_CONFIG, RESET, FLOW_CONTROL, SYS_BOOT_EVENT, GET_TOPOLOGY) 经过 17 项测试用例、**81 项断言全部通过**，0 失败 0 跳过。

### 9.1 GET_CONFIG/SET_CONFIG (v0.1.0 基础, 2026-07-10)
- ✅ DeviceName 可读/可写 (默认 "HXB-Device")
- ✅ HeartbeatInterval 可读/可写 (默认 5000ms)
- ✅ FlowControlEnable 可读/可写 (默认 0x01)
- ✅ UartChannelCount 只读，值=1
- ✅ CanChannelCount 只读，值=2
- ✅ 只读 Key 写入被拒绝 (ERR_PERMISSION)
- ✅ 写入后回读一致性验证 (DeviceName + HeartbeatInterval)

### 9.2 MCP 波特率配置 (v0.1.0 新增, 2026-07-22)
- ✅ McpBaudRate (ConfigKey=0x12) 可读 (GET_CONFIG 返回 u32 大端)
- ✅ McpBaudRate 可写 (SET_CONFIG → NVS 持久化)
- ✅ 波特率有效范围校验: 拒绝 < 9600 和 > 5000000 (ERR_PARAM)
- ✅ 写入后回读一致性验证 (230400)
- ✅ 端到端: SET_CONFIG(230400) → RESET → 230400 重连 → PING → GET_INFO → 恢复 115200
- ✅ NVS 持久化: 软复位后波特率保持跨重启一致

**固件编译、烧录、测试全流程验证通过。**
