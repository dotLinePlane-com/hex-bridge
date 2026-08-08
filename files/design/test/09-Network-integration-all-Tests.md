# 09. 网络模块全量集成与端到端自动化测试规�?
> 命令码范围：`0x40-0x4F` (网络配置), `0x50-0x5F` (TCP), `0x60-0x6F` (UDP), `0x70-0x7F` (WebSocket)  
> 模块：`mod_network` + `mod_tcp` + `mod_udp` + `mod_ws`  
> **核心测试脚本**: `script/test/test_network.py` (协议�?离线自测) + `script/test/test_network_integration.py` (端到�?Auto-NM 集成测试)  
> **协议版本**: UBCP v2.0 (`0x02`)  

---

## 1. 测试架构与拓�?
全量网络测试旨在覆盖 HEX-Bridge �?*无网络（拔网线）**�?*有网络（DHCP 连通）**，再�?*复杂多协议端到端收发**的全生命周期�?
```
┌───────────────────────────────────────────────────────────────────────────�?�?                        同一�?PC                                          �?�?                                                                           �?�? ┌───────────────────────────�?    COM4    ┌─────────────────────────�?  �?�? �?1. test_network.py        │←────────────→│ HEX-Bridge ESP32        �?  �?�? �?2. test_network_          �?   UART1     �?+ LAN8720               �?  �?�? �?   integration.py         �?   115200    �?IP: 192.168.1.105       �?  �?�? �?(Auto-NM: Socket/WS)      �?             └────────────┬────────────�?  �?�? └─────────────┬─────────────�?                          �?               �?�?               �?                                        �?               �?�?               �?                              ┌─────────┴──────────�?    �?�?               �?     TCP / UDP / WS           �? 以太�?switch/路由器│     �?�?               └──────────────────────────────→│  192.168.1.0/24    �?    �?�?                      192.168.1.4              └────────────────────�?    �?└───────────────────────────────────────────────────────────────────────────�?```

### 工具与脚本分�?
| 脚本 / 工具 | 主要职责 | 执行条件 / 参数 |
|:---|:---|:---|
| **`test_network.py`** | 负责协议层自测、参数校验、状态查询、错误码抛出、拔网线离线行为检�?| `python script/test/test_network.py --auto` |
| **`test_network_integration.py`** | 负责 Auto-NM 端到端集成测试（Python原生 Socket 模拟 TCP/UDP 对端，`websocket-client` 模拟 WS 对端�?| `python script/test/test_network_integration.py --all --auto-nm` |
| **`hex-bridge-network-cli.py`** | 命令行调试工具，用于手工辅助验证或查看网络连接状�?| `python script/cli/hex-bridge-network-cli.py --port COM4 <cmd>` |

---

## 2. 完整全量测试步骤 (Step-by-Step Flow)

要完成一次完整的网络模块全量测试，需严格按照以下 **4 个阶段（Phase 0 ~ Phase 3�?* 顺序执行�?
```
┌─────────────────�?    ┌─────────────────�?    ┌─────────────────�?    ┌─────────────────�?�?Phase 0         �?    �?Phase 1         �?    �?Phase 2         �?    �?Phase 3         �?�?拔掉网线状态测�?�?�?  �?插入网线恢复    �?�?  �?在线协议层自�? �?�?  �?端到端集成测�?  �?�?(离线边界验证)   �?    �?(DHCP 获取 IP)  �?    �?(test_network)  �?    �?(integration)   �?└─────────────────�?    └─────────────────�?    └─────────────────�?    └─────────────────�?```

---

### Phase 0: 拔掉网线状态测�?(离线边界验证)

**目的**: 验证设备在没有物理网络连接（网线拔出、无 IP）时的健壮性，确保无网络时接口不会崩溃，并能正确抛�?`ERR_NET_NO_IP` (`0x47`) �?`ERR_NET_CONN_REFUSED` (`0x41`)�?
#### 执行步骤�?
1. **拔掉 HEX-Bridge 的以太网�?*�?2. 确保设备上电，COM35 串口通信正常�?3. 执行基础测试脚本�?   ```bash
   python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --auto
   ```

#### 关键验证项：

| 用例编号 | 测试�?| 预期响应 / 行为 |
|:---|:---|:---|
| **DRV-01** | 物理链路检�?| 上报 `Link=DOWN` |
| **NET-10** | 无网络查�?NET_STATUS | 返回 `Link=DOWN`, `IP=0.0.0.0`, `ConnState=0` |
| **NET-13** | �?IP 时调�?NET_DNS | 返回错误 `0x47 (ERR_NET_NO_IP)` 正确拒绝 |
| **TCP-29** | �?IP �?TCP 操作 | TCP Server OPEN 允许 (`bind INADDR_ANY`)；TCP Client CONNECT 返回 `0x41 (ERR_NET_CONN_REFUSED)` |
| **UDP-14** | �?IP �?UDP 操作 | UDP Server OPEN / Client CREATE 均允许（UDP 无连接状态） |
| **WS-18** | �?IP �?WS 操作 | WS Server OPEN 允许 (`bind INADDR_ANY`) |

> **预期结果**: 无崩溃，所有受网络影响的请求均返回正确的错误码�?
---

### Phase 1: 插入网线与链路恢�?
**目的**: 验证设备重新接入网络后的自动 Link UP 检测和 DHCP 自动获取 IP 能力�?
#### 执行步骤�?
1. **插入以太网线**�?2. 观察 COM5 调试串口日志，确认打�?`Ethernet Link Up`�?3. 等待�?3~5 秒（DHCP 自动分配 IP）�?4. 使用 CLI 查询当前网络状态：
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 115200 net-status
   ```

#### 关键验证项：

* 响应�?`Status=OK`
* `Link=UP`
* `ConnState=1` (已连�?
* `IP` 为局域网分配的有效非零地址（例�?`192.168.1.105`�?
---

### Phase 2: 在线基础协议与功能自动化测试

**目的**: 在网线插好、DHCP 正常工作的情况下，全量执行协议层与功能层自测用例�?
#### 执行步骤�?
1. 执行基础自测命令�?   ```bash
   python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --auto
   ```

#### 关键验证项：

* **驱动�?(DRV)**: DRV-01~05（Link UP 确认、链路稳定性）
* **配置�?(NET)**: NET-01~05, NET-08~18（网络状态查询、域名解析、全局连接列表 NET_LIST_CONNS、一键关�?NET_CLOSE_ALL、DNS 非阻�?Bug#5 验证�?* **TCP 模块 (TCP)**: TCP-01~04, TCP-09, TCP-15~19, TCP-25~35（Server 创建、端口冲突、参数校验、非法句柄拒绝、Kick 客户端、状态查询）
* **UDP 模块 (UDP)**: UDP-01, UDP-04, UDP-10~14（Server/Client 创建与关闭、超最大连接拒绝）
* **WebSocket 模块 (WS)**: WS-01, WS-07, WS-11, WS-18~20（WS Server 创建、非法句柄拦截）
* **压力与边�?(STR)**: STR-03~10（快�?Open/Close 循环�?x8000 广播句柄�? 周期内存泄露测试、命令流水线并发�?
> **预期结果**: **82 PASS / 0 FAIL / 3 SKIP**（SKIP 为设备已�?IP 的条件跳转）�?
---

### Phase 3: 端到端网络集成自动化测试 (Auto-NM)

**目的**: 自动启动 PC 端的 Socket �?WebSocket 客户�?服务端作为网络对端，验证真实局域网数据收发、大数据量传输、断开事件及流量控制�?
#### 执行步骤�?
1. 执行端到端集成测试脚本：
   ```bash
   python script/test/test_network_integration.py --all --auto-nm
   ```

#### 关键验证�?(24 项全量集成用�?�?
| 模块 | 用例编号 | 集成测试内容 | 验证标准 |
|:---|:---|:---|:---|
| **NET** | **NET-06** | 静�?IP 配置 | 设置静�?IP `192.168.1.200` 成功，恢�?DHCP 成功 |
| **NET** | **NET-07** | DHCP 恢复验证 | 恢复 DHCP �?10 秒内成功重新获取 IP |
| **TCP** | **TCP-10** | 连接被拒测试 | 连接未监听端�?49999 返回 `0x41 (CONN_REFUSED)` |
| **TCP** | **TCP-11** | TCP FIN 优雅断开 | PC 客户端连�?HEX TCP Server，发�?FIN 断开响应 `Status=OK` |
| **TCP** | **TCP-13** | 断开事件捕获 | PC 断开连接，CLI `--wait-events` 正确捕获 `0x58 (TCP_DISCONNECT)` 事件 |
| **TCP** | **TCP-20** | HandleType=0 关闭 | `tcp-close --handle-type 0` 成功关闭单个 TCP 连接 |
| **TCP** | **TCP-21** | 1024B 大数据双�?| NM→HEX 发�?1024B (HEX rx_bytes=1024)；HEX→NM 回复 1024B 递增序列完整接收 |
| **TCP** | **TCP-23** | 手动拒绝连接 | Server `accept_mode=0` 下，对待定客户端执行 `decision=1` 成功拒绝 |
| **TCP** | **TCP-26** | 发送缓冲区边界 | 连续发�?20×512B 数据，恢复读取后数据无丢�?|
| **UDP** | **UDP-06** | AddrMode=1 动态覆�?| `udp-client-send --addr-mode 1` 覆盖发送到 PC 指定端口成功 |
| **UDP** | **UDP-07** | UDP 广播发�?| `udp-server-open --broadcast` �?`192.168.1.255` 发送广播成�?|
| **UDP** | **UDP-08** | UDP 多播发�?| 开启多播组 `239.0.0.1` 并成功发�?接收组播报文 |
| **UDP** | **UDP-09** | UDP Client 删除校验 | 删除 Client 句柄后再次发送，正确返回 `0x43 (ERR_NET_HANDLE_INVALID)` |
| **WS** | **WS-08** | WS 断开事件捕获 | PC 客户端断开连接，`0x77 (WS_DISCONNECT)` 事件正确捕获 |
| **WS** | **WS-12** | WS Pong 帧发�?| `ws-send --msg-type 10` 成功发�?Pong 控制�?|
| **WS** | **WS-14** | WS 自动回复 Pong | PC 发�?Ping "HEARTBEAT"，设备端连接保持存活并自动回�?Pong |
| **WS** | **WS-16** | 错误路径请求拒绝 | PC 连接 `ws://<HEX_IP>:port/wrong` 路径，被返回 404 拒绝 |
| **WS** | **WS-17** | MaxConn 容量阻断 | Server `maxconn=2` 下，�?3 个客户端连接被阻断拒�?|
| **WS** | **WS-21** | 优雅踢出 WS 客户�?| `ws-kick-client --force 0` 发�?Close 帧并优雅踢出客户�?|
| **STR** | **STR-02** | 多客户端并发 | 4 个客户端同时连接 `maxconn=3` �?TCP Server，前 3 个成功，�?4 个被�?|
| **NM** | **NM-TCP-05** | 手动拒绝 (NM 变体) | 端到端自动套接字验证 TCP 手动拒绝流程 |
| **NM** | **NM-TCP-06** | List + Kick 组合 | `tcp-list-clients` 获取句柄后执�?`tcp-kick-client --force 1` 成功清理 |
| **NM** | **NM-UDP-03** | UDP 广播 (NM 变体) | Auto-NM UDP Server 成功收到 HEX-Bridge 发出的广播报�?|
| **NM** | **NM-STR-01** | 1024B 双向随机数据 | 1024 字节随机 Byte 序列双向传输无校验错�?|

> **预期结果**: **24 PASS / 0 FAIL / 0 SKIP**�?
---

## 3. 全量测试用例清单矩阵 (122 用例全览)

| 模块 | 用例范围 | 数量 | 归属脚本 | 执行阶段 | 结果标准 |
|:---|:---|:---|:---|:---|:---|
| **以太网驱�?(DRV)** | `DRV-01` ~ `DRV-05` | 5 | `test_network.py` | Phase 0 & Phase 2 | 全部 PASS |
| **网络配置 (NET)** | `NET-01` ~ `NET-05`, `NET-08` ~ `NET-18` | 16 | `test_network.py` | Phase 0 & Phase 2 | 全部 PASS |
| **网络配置 (NET)** | `NET-06`, `NET-07` | 2 | `test_network_integration.py` | Phase 3 | 全部 PASS |
| **TCP 模块 (TCP)** | `TCP-01`~`04`, `09`, `15`~`19`, `24`~`25`, `27`~`35` | 19 | `test_network.py` | Phase 0 & Phase 2 | 全部 PASS |
| **TCP 模块 (TCP)** | `TCP-10`, `11`, `13`, `20`, `21`, `23`, `26` | 7 | `test_network_integration.py` | Phase 3 | 全部 PASS |
| **UDP 模块 (UDP)** | `UDP-01`, `04`, `10` ~ `14` | 7 | `test_network.py` | Phase 0 & Phase 2 | 全部 PASS |
| **UDP 模块 (UDP)** | `UDP-06` ~ `UDP-09` | 4 | `test_network_integration.py` | Phase 3 | 全部 PASS |
| **WebSocket (WS)** | `WS-01`, `07`, `11`, `18` ~ `20` | 6 | `test_network.py` | Phase 0 & Phase 2 | 全部 PASS |
| **WebSocket (WS)** | `WS-08`, `12`, `14`, `16`, `17`, `21` | 6 | `test_network_integration.py` | Phase 3 | 全部 PASS |
| **压力边界 (STR)** | `STR-01`, `STR-03` ~ `STR-10` | 9 | `test_network.py` | Phase 2 | 全部 PASS |
| **压力边界 (STR)** | `STR-02` | 1 | `test_network_integration.py` | Phase 3 | 全部 PASS |
| **NM 变体 (NM)** | `NM-TCP-05`, `NM-TCP-06`, `NM-UDP-03`, `NM-STR-01` | 4 | `test_network_integration.py` | Phase 3 | 全部 PASS |
| **全量总计** | **122 用例** | **122** | **两脚本组�?* | **Phase 0 ~ Phase 3** | **100% PASS** |

---

## 4. 自动化回归测试一键指令速查

在持续集�?(CI/CD) 或常规回归测试中，依次复制并执行以下控制台命令：

```bash
# =================================================================
# 1. 离线阶段 (拔掉网线状态下)
# =================================================================
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --auto

# =================================================================
# 2. 插上网线，等�?DHCP 获取 IP，确�?IP 连通�?# =================================================================
python script/cli/hex-bridge-network-cli.py --port COM4 --baud 115200 net-status

# =================================================================
# 3. 在线阶段：协议层与功能层全量自测
# =================================================================
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --auto

# =================================================================
# 4. 集成阶段：端到端网络数据收发�?Auto-NM 自动化对端测�?# =================================================================
python script/test/test_network_integration.py --all --auto-nm
```

---

## 5. 结论与判定标�?
1. **Phase 0 (拔网�?**：所有无 IP 用例正确返回错误码（�?`0x47 ERR_NET_NO_IP` �?`0x41 ERR_NET_CONN_REFUSED`），无固件死机崩溃�?2. **Phase 2 (在线自测)**：`test_network.py --auto` 结果�?`PASS: 82, FAIL: 0, SKIP: 3`�?3. **Phase 3 (端到端集�?**：`test_network_integration.py --all --auto-nm` 结果�?`PASS: 24, FAIL: 0, SKIP: 0`�?4. **通过判定**�? 个阶段全流程顺利跑完，没有任�?`FAIL` 报错，即认定 HEX-Bridge 网络模块固件质量达标，通过全量集成测试�?