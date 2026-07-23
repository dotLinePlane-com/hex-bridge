# HEX-Bridge 网络模块 — 测试报告

> **报告日期**: 2026-07-23 | **固件版本**: — (待实现) | **协议**: UBCP v2.0

---

## 1. 测试概要

| 项目 | 值 |
|:---|:---|
| 被测模块 | 网络配置 (0x40-0x4F) + TCP (0x50-0x5F) + UDP (0x60-0x6F) + WebSocket (0x70-0x7F) |
| 测试用例数 | 121 |
| 测试结果 | **0 PASS / 0 FAIL / 121 PENDING** |
| 测试脚本 | `script/test/test_network.py` + MCP Network Monitor (Kilo Agent 集成) |
| CLI 工具 | `script/cli/hex-bridge-network-cli.py` (25 命令全覆盖) |
| 芯片型号 | ESP32-D0WD-V3 (revision v3.1) |
| IDF 版本 | ESP-IDF v6.0.1 |
| 以太网 PHY | LAN8720 (RMII, PHY_RST=GPIO5) |

> **状态说明**: 固件端网络模块 (`mod_network`, `mod_tcp`, `mod_udp`, `mod_ws`) 尚未实现，测试脚本和 CLI 工具已就绪。本报告记录完整的测试用例计划和预期结果，供固件实现后执行验证。

---

## 2. 测试环境

### 2.1 测试拓扑

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         同一台 PC                                          │
│                                                                            │
│  ┌─────────────────────┐          ┌─────────────────────────────┐         │
│  │ Serial Monitor       │  COM35   │ Network Monitor               │        │
│  │ (MCP 通信 + 测试)   │←────────→│ (TCP/UDP/WS Server/Client)   │        │
│  │ UBCP 帧收发         │  921600  │ 充当网络对端                   │        │
│  │                      │          │                                │        │
│  └─────────┬───────────┘          └──────────────┬──────────────┘         │
│            │                                      │                        │
│            │  UART1 (GPIO4/34)                    │ Ethernet               │
│            ▼                                      ▼                        │
│       ┌──────────────────┐       ┌──────────────────────┐                  │
│       │   HEX-Bridge     │←──────│  路由器 / DHCP        │                  │
│       │   ESP32+LAN8720  │  100  │                      │                  │
│       │                  │  Mbps │                      │                  │
│       │   UART0          │←──────│ COM34 (调试日志, 115200 bps)            │
│       └──────────────────┘       └──────────────────────┘                  │
└───────────────────────────────────────────────────────────────────────────┘
```

### 2.2 硬件连接

| 串口 | 功能 | TX | RX | 参数 |
|:---|:---|:---|:---|:---|
| UART0 | 调试/烧录 | GPIO 1 | GPIO 3 | 115200, 8N1 |
| UART1 | MCP 通信 | GPIO 4 | GPIO 34 (GPI) | 921600, 8N1 |
| 以太网 | 网络通信 | LAN8720 RMII 固定引脚 | — | 100Mbps |

### 2.3 软件环境

| 组件 | 版本/说明 |
|:---|:---|
| Python | 3.9+ |
| pyserial | 最新 |
| 测试框架 | ubcp_client.py + mcp_transport.py |
| 网络对端 | MCP Network Monitor (TCP/UDP/WebSocket Server/Client) |
| CLI 工具 | hex-bridge-network-cli.py (25 命令, 100% 覆盖) |
| 串口监视 | Serial Monitor (MCP 通信 + UBCP 事件监听) |

### 2.4 测试前提条件

1. 固件已烧录并运行, LAN8720 驱动初始化成功
2. 网线已插入, 链路 UP (COM34 日志确认 `Ethernet Link Up`)
3. DHCP 已获取 IP 地址 (NET_STATUS 确认)
4. 完成握手: PING (0x00) + GET_INFO (0x01)

---

## 3. 测试结果汇总

### 3.1 以太网驱动层测试 (DRV)

| 用例 | 命令码 | 测试内容 | 结果 |
|:---|:---|:---|:---|
| DRV-01 | 0x43 (事件) | 物理链路 UP 检测 (NET_LINK_EVENT + IP_ACQUIRED) | ⏭ PENDING |
| DRV-02 | 0x43 (事件) | 网线拔出检测 (LINK_DOWN 事件) | ⏭ PENDING |
| DRV-03 | 0x43 (事件) | 网线重新插入的链路恢复 | ⏭ PENDING |
| DRV-04 | 0x41 | DHCP 服务器不可用时 ConnState=0x02 | ⏭ PENDING |
| DRV-05 | 0x43 (事件) | 网线快速插拔 10 次事件不丢失 | ⏭ PENDING |

### 3.2 网络配置模块测试 (NET, 0x40-0x4F)

| 用例 | 命令码 | 测试内容 | 结果 |
|:---|:---|:---|:---|
| NET-01 | 0x41 | NET_STATUS — 正常查询 (InterfaceIndex=0) | ⏭ PENDING |
| NET-02 | 0x41 | NET_STATUS — 查询所有接口 (Index=0xFF) | ⏭ PENDING |
| NET-03 | 0x42 | NET_DNS — 域名解析成功 (example.com) | ⏭ PENDING |
| NET-04 | 0x42 | NET_DNS — 域名解析失败 (不存在域名) | ⏭ PENDING |
| NET-05 | 0x42 | NET_DNS — 域名字符串超长 (ERR_PARAM) | ⏭ PENDING |
| NET-06 | 0x40 | NET_CONFIG — 设置静态 IP | ⏭ PENDING |
| NET-07 | 0x40 | NET_CONFIG — 恢复 DHCP 模式 | ⏭ PENDING |
| NET-08 | 0x40 | NET_CONFIG — 无效 InterfaceIndex (ERR_CHANNEL_INVALID) | ⏭ PENDING |
| NET-09 | 0x40 | NET_CONFIG — 无效 ConfigType (ERR_PARAM) | ⏭ PENDING |
| NET-10 | 0x41 | NET_STATUS — 网线拔出时查询 (LinkState=Down) | ⏭ PENDING |
| NET-11 | 0x42 | NET_DNS — DNS 服务器不可达 (超时返回 DNS_FAIL) | ⏭ PENDING |
| NET-12 | 0x41 | NET_STATUS — DHCP 获取中 (ConnState=0x02) | ⏭ PENDING |
| NET-13 | 0x42 | NET_DNS — 无 IP 时调用 (ERR_NET_NO_IP) | ⏭ PENDING |
| NET-14 | 0x40/0x41 | NET_CONFIG — NVS 持久化验证 (重启后静态 IP 保持) | ⏭ PENDING |
| NET-15 | 0x43 (事件) | NET_LINK_EVENT — IP_CHANGED 事件 | ⏭ PENDING |
| NET-16 | 0x44 | NET_LIST_CONNS — 全局连接查询 | ⏭ PENDING |

### 3.3 TCP 模块测试 (TCP, 0x50-0x5F)

| 用例 | 命令码 | 测试内容 | 结果 |
|:---|:---|:---|:---|
| TCP-01 | 0x50 | TCP_SERVER_OPEN — 创建 TCP Server (正常) | ⏭ PENDING |
| TCP-02 | 0x50 | TCP_SERVER_OPEN — 系统自动分配端口 (Port=0) | ⏭ PENDING |
| TCP-03 | 0x50 | TCP_SERVER_OPEN — 端口已被占用 (ERR_NET_PORT_IN_USE) | ⏭ PENDING |
| TCP-04 | 0x50 | TCP_SERVER_OPEN — 超过最大 Server 数 (ERR_NET_MAX_CONN) | ⏭ PENDING |
| TCP-05 | 0x56 (事件) | TCP_ACCEPT — 客户端连接事件 (自动接受) | ⏭ PENDING |
| TCP-06 | 0x54 | TCP_SEND — Server 端发送数据到客户端 | ⏭ PENDING |
| TCP-07 | 0x55 (事件) | TCP_RECV — 接收客户端发来的数据 | ⏭ PENDING |
| TCP-08 | 0x52 | TCP_CLIENT_CONNECT — 客户端连接远端 Server | ⏭ PENDING |
| TCP-09 | 0x52 | TCP_CLIENT_CONNECT — 连接超时 (ERR_NET_TIMEOUT) | ⏭ PENDING |
| TCP-10 | 0x52 | TCP_CLIENT_CONNECT — 连接被拒绝 (ERR_NET_CONN_REFUSED) | ⏭ PENDING |
| TCP-11 | 0x53 | TCP_CLIENT_DISCONNECT — 正常 FIN 断开 | ⏭ PENDING |
| TCP-12 | 0x53 | TCP_CLIENT_DISCONNECT — 强制 RST 断开 | ⏭ PENDING |
| TCP-13 | 0x58 (事件) | TCP_DISCONNECT_EVENT — 远端断开事件上报 | ⏭ PENDING |
| TCP-14 | 0x54 | TCP_SEND — 广播句柄 0x8000 发送到所有客户端 | ⏭ PENDING |
| TCP-15 | 0x54 | TCP_SEND — 无效句柄 (ERR_NET_HANDLE_INVALID) | ⏭ PENDING |
| TCP-16 | 0x54 | TCP_SEND — 向已断开连接发送 (ERR_NET_DISCONNECTED) | ⏭ PENDING |
| TCP-17 | 0x51 | TCP_SERVER_CLOSE — 关闭 Server (ForceClose=1) | ⏭ PENDING |
| TCP-18 | 0x51 | TCP_SERVER_CLOSE — 无效句柄 (ERR_NET_HANDLE_INVALID) | ⏭ PENDING |
| TCP-19 | 0x57 | TCP_CLOSE — 通用关闭连接 (HandleType=0) | ⏭ PENDING |
| TCP-20 | 0x57 | TCP_CLOSE — 通用关闭 Server (HandleType=1) | ⏭ PENDING |
| TCP-21 | 0x54 | TCP_SEND — 大数据量发送 1024 字节 | ⏭ PENDING |
| TCP-22 | 0x56 | TCP_ACCEPT — 手动接受模式 | ⏭ PENDING |
| TCP-23 | 0x56 | TCP_ACCEPT — 手动拒绝 | ⏭ PENDING |
| TCP-24 | 0x50 | TCP_SERVER_OPEN — 网线拔出时创建 (ERR_NET_NO_IP) | ⏭ PENDING |
| TCP-25 | 全部 TCP | TCP 完整生命周期 (8 步集成) | ⏭ PENDING |
| TCP-26 | 0x54 | TCP_SEND — 发送缓冲区满 (ERR_NET_BUFFER_FULL) | ⏭ PENDING |
| TCP-27 | 0x52 | TCP_CLIENT_CONNECT — 超过最大连接数 (ERR_NET_MAX_CONN) | ⏭ PENDING |
| TCP-28 | 0x51 | TCP_SERVER_CLOSE — 优雅关闭 (ForceClose=0) | ⏭ PENDING |
| TCP-29 | 0x50/0x52 | TCP OPEN/CONNECT — 无 IP 时拒绝 (ERR_NET_NO_IP) | ⏭ PENDING |
| TCP-30 | 0x59 | TCP_LIST_CLIENTS — 查询已连接客户端 | ⏭ PENDING |
| TCP-31 | 0x59 | TCP_LIST_CLIENTS — 空 Server 返回 ClientCount=0 | ⏭ PENDING |
| TCP-32 | 0x5A | TCP_KICK_CLIENT — 强制断开指定客户端 | ⏭ PENDING |
| TCP-33 | 0x5A | TCP_KICK_CLIENT — 无效句柄 (ERR_NET_HANDLE_INVALID) | ⏭ PENDING |
| TCP-34 | 0x5B | TCP_CONN_STATUS — 查询单连接状态 | ⏭ PENDING |
| TCP-35 | 0x5B | TCP_CONN_STATUS — 无效句柄 (ERR_NET_HANDLE_INVALID) | ⏭ PENDING |

### 3.4 UDP 模块测试 (UDP, 0x60-0x6F)

| 用例 | 命令码 | 测试内容 | 结果 |
|:---|:---|:---|:---|
| UDP-01 | 0x60 | UDP_SERVER_OPEN — 创建 UDP Server | ⏭ PENDING |
| UDP-02 | 0x64 | UDP_SERVER_SEND — 发送数据到指定地址 | ⏭ PENDING |
| UDP-03 | 0x65 (事件) | UDP_RECV — 接收外部 UDP 数据 | ⏭ PENDING |
| UDP-04 | 0x62 | UDP_CLIENT_CREATE — 创建 UDP Client | ⏭ PENDING |
| UDP-05 | 0x66 | UDP_CLIENT_SEND — 使用默认地址发送 | ⏭ PENDING |
| UDP-06 | 0x66 | UDP_CLIENT_SEND — 使用指定地址发送 (AddrMode=1) | ⏭ PENDING |
| UDP-07 | 0x60 | UDP_SERVER_OPEN — 启用广播模式 | ⏭ PENDING |
| UDP-08 | 0x60 | UDP_SERVER_OPEN — 多播模式 (MulticastAddr) | ⏭ PENDING |
| UDP-09 | 0x63 | UDP_CLIENT_DELETE — 删除 UDP Client | ⏭ PENDING |
| UDP-10 | 0x61 | UDP_SERVER_CLOSE — 关闭 UDP Server | ⏭ PENDING |
| UDP-11 | 0x60 | UDP_SERVER_OPEN — 超过最大 Server 数 (ERR_NET_MAX_CONN) | ⏭ PENDING |
| UDP-12 | 0x62 | UDP_CLIENT_CREATE — 超过最大 Client 数 (ERR_NET_MAX_CONN) | ⏭ PENDING |
| UDP-13 | 0x61 | UDP_SERVER_CLOSE — 无效句柄 (ERR_NET_HANDLE_INVALID) | ⏭ PENDING |
| UDP-14 | 0x60/0x62 | UDP OPEN/CREATE — 无 IP 时拒绝 (ERR_NET_NO_IP) | ⏭ PENDING |

### 3.5 WebSocket 模块测试 (WS, 0x70-0x7F)

| 用例 | 命令码 | 测试内容 | 结果 |
|:---|:---|:---|:---|
| WS-01 | 0x70 | WS_SERVER_OPEN — 创建 WebSocket Server | ⏭ PENDING |
| WS-02 | 0x76 (事件) | WS_ACCEPT — WebSocket 客户端连接事件 | ⏭ PENDING |
| WS-03 | 0x74 | WS_SEND — 发送 Text 消息 | ⏭ PENDING |
| WS-04 | 0x74 | WS_SEND — 发送 Binary 消息 | ⏭ PENDING |
| WS-05 | 0x75 (事件) | WS_RECV — 接收 WebSocket Text 消息 | ⏭ PENDING |
| WS-06 | 0x74 | WS_SEND — 发送 Ping (心跳) | ⏭ PENDING |
| WS-07 | 0x73 | WS_CLIENT_DISCONNECT — 关闭 WebSocket 连接 | ⏭ PENDING |
| WS-08 | 0x77 (事件) | WS_DISCONNECT_EVENT — 远端断开事件上报 | ⏭ PENDING |
| WS-09 | 0x72 | WS_CLIENT_CONNECT — 客户端连接远端 WS Server | ⏭ PENDING |
| WS-10 | 0x72 | WS_CLIENT_CONNECT — 握手失败 (ERR_NET_WS_HANDSHAKE) | ⏭ PENDING |
| WS-11 | 0x71 | WS_SERVER_CLOSE — 关闭 WebSocket Server | ⏭ PENDING |
| WS-12 | 0x74 | WS_SEND — 发送 Pong (心跳回复) | ⏭ PENDING |
| WS-13 | 全部 WS | WebSocket 完整生命周期 (8 步集成) | ⏭ PENDING |
| WS-14 | — | WS_RECV — 自动回复 Ping (RFC 6455, 不上报 UBCP) | ⏭ PENDING |
| WS-15 | 0x74 | WS_SEND — 发送 Close 帧 (MsgType=0x08) | ⏭ PENDING |
| WS-16 | 0x76 (事件) | WS_ACCEPT — 错误路径请求不触发 ACCEPT | ⏭ PENDING |
| WS-17 | 0x70 | WS_SERVER_OPEN — MaxConn=1 容量限制 | ⏭ PENDING |
| WS-18 | 0x70/0x72 | WS OPEN/CONNECT — 无 IP 时拒绝 (ERR_NET_NO_IP) | ⏭ PENDING |
| WS-19 | 0x78 | WS_LIST_CLIENTS — 查询已连接客户端 | ⏭ PENDING |
| WS-20 | 0x79 | WS_KICK_CLIENT — 强制断开指定客户端 | ⏭ PENDING |
| WS-21 | 0x79 | WS_KICK_CLIENT — 优雅关闭 (ForceFlag=0) | ⏭ PENDING |

### 3.6 压力与边界测试 (STRESS)

| 用例 | 命令码 | 测试内容 | 结果 |
|:---|:---|:---|:---|
| STR-01 | 0x50 | 多 Server 并发 (4 个 TCP Server 同时运行) | ⏭ PENDING |
| STR-02 | 0x50 | 多 Client 并发连接 (MaxConn=3, 第 4 个被拒) | ⏭ PENDING |
| STR-03 | 0x50/0x51 | 快速 OPEN→CLOSE 循环 5 次 (端口不泄漏) | ⏭ PENDING |
| STR-04 | 0x54 | TCP_SEND 广播句柄 (0x8000) | ⏭ PENDING |
| STR-05 | 0x41 | NET_STATUS — 载荷不足 (ERR_PARAM) | ⏭ PENDING |
| STR-06 | 0x5F | 保留命令码返回 ERR_NOT_SUPPORT | ⏭ PENDING |
| STR-07 | 全部 | 内存泄漏 — 100 次 Server 生命周期循环 | ⏭ PENDING |
| STR-08 | 0x41 | 并发命令流水线 (5 条 NET_STATUS 无串扰) | ⏭ PENDING |
| STR-09 | 全部保留 | 所有保留命令码返回 ERR_NOT_SUPPORT | ⏭ PENDING |
| STR-10 | 0x54 | TCP_SEND DataLen 声明不匹配 (ERR_PARAM) | ⏭ PENDING |

### 3.7 MCP Network Monitor 对端测试 (NM)

| 用例 | 涉及命令码 | 测试内容 | 结果 |
|:---|:---|:---|:---|
| NM-TCP-01 | 0x41/0x52/0x54/0x55/0x53 | TCP Client → NM Server 端到端收发 | ⏭ PENDING |
| NM-TCP-02 | 0x50/0x56/0x54/0x55/0x58/0x51 | NM Client → TCP Server 端到端收发 | ⏭ PENDING |
| NM-TCP-03 | 0x50/0x54 | TCP Server 广播发送 (0x8000) 到多 Client | ⏭ PENDING |
| NM-TCP-04 | 0x50/0x56 | TCP Server 手动接受模式 (AcceptMode=0x00) | ⏭ PENDING |
| NM-TCP-05 | 0x50/0x56 | TCP_ACCEPT 手动拒绝 | ⏭ PENDING |
| NM-TCP-06 | 0x50/0x56/0x59/0x5A/0x58 | TCP_LIST_CLIENTS + KICK 端到端 | ⏭ PENDING |
| NM-TCP-07 | 0x50/0x59 | TCP_LIST_CLIENTS 空 Server | ⏭ PENDING |
| NM-UDP-01 | 0x60/0x65/0x64 | UDP Server → NM Client 收发 | ⏭ PENDING |
| NM-UDP-02 | 0x62/0x66/0x63 | UDP Client 创建/发送/删除生命周期 | ⏭ PENDING |
| NM-UDP-03 | 0x60/0x64 | UDP 广播发送 | ⏭ PENDING |
| NM-WS-01 | 0x70/0x76/0x74/0x75/0x73/0x71 | WS Server → NM Client Text 收发 | ⏭ PENDING |
| NM-WS-02 | 0x72/0x74/0x75/0x73 | WS Client → NM Server 端到端 | ⏭ PENDING |
| NM-WS-03 | 0x70/0x74 | WebSocket Binary 消息 (含转义字节 0x7E/0x7D) | ⏭ PENDING |
| NM-WS-04 | 0x70/0x74 | WebSocket Ping/Pong 心跳 | ⏭ PENDING |
| NM-WS-05 | 0x70/0x76/0x78/0x79/0x77 | WS_LIST_CLIENTS + KICK 端到端 | ⏭ PENDING |
| NM-WS-06 | 0x70/0x74 | WebSocket Close 帧 (CloseCode=1000) | ⏭ PENDING |
| NM-INT-01 | TCP/UDP/WS | 3 协议 Server 并发 (不干扰) | ⏭ PENDING |
| NM-INT-02 | TCP/UDP/WS | HEX-Bridge 作为 3 协议 Client 并发 | ⏭ PENDING |
| NM-INT-03 | 0x44 | NET_LIST_CONNS 全局概览 | ⏭ PENDING |
| NM-STR-01 | 0x50/0x54/0x55 | 大数据量 TCP 收发 (1024 字节无丢包) | ⏭ PENDING |

---

## 4. 测试用例详细设计

### 4.1 以太网驱动层 (DRV)

#### DRV-01: 物理链路 UP 检测

| 项目 | 值 |
|:---|:---|
| CmdCode | 0x43 (NET_LINK_EVENT, 设备事件) |
| 方法 | 设备上电后监听 COM35 |

**预期事件帧**: EventType=0x01 (LINK_UP) → EventType=0x02 (IP_ACQUIRED)

#### DRV-02: 网线拔出检测

| 项目 | 值 |
|:---|:---|
| CmdCode | 0x43 (NET_LINK_EVENT) |
| 步骤 | 1. 拔出网线 → 2. 监听 LINK_DOWN 事件 |

**预期**: 2s 内收到 EventType=0x00, IpAddr=0x00000000

#### DRV-03: 网线重新插入恢复

从 LINK_DOWN 重新插入网线，监听 LINK_UP → IP_ACQUIRED 序列

#### DRV-04: DHCP 不可用

断开路由器 DHCP，设备重启后 LAN8720 link UP 但 ConnState=0x02 (获取IP中), IpAddr=0x00000000，设备不崩溃

#### DRV-05: 快速插拔

5 秒内 10 次插拔 → 20 个事件 (10 UP + 10 DOWN)，无丢失无重复

---

### 4.2 网络配置 (NET)

#### NET-01: NET_STATUS 正常查询

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | 0x00 |
| 3 | LinkState | 0x01 (Up) |
| 4 | ConnState | 0x01 (已连接) |
| 5-8 | IpAddr | 有效非零 IP |

#### NET-03: NET_DNS 域名解析

**请求**: NameLen=11, Hostname="example.com"
**预期**: Status=0x00, AddrCount≥1

#### NET-06: NET_CONFIG 设置静态 IP

**请求**: InterfaceIndex=0x00, ConfigType=0x01, IpAddr=192.168.1.100, SubnetMask=255.255.255.0, Gateway=192.168.1.1, DNS1=8.8.8.8

**预期**: Status=0x00, NET_STATUS 确认 IpAddr=192.168.1.100

#### NET-14: NVS 持久化

静态 IP 配置后断电重启 → NET_STATUS 直接报告静态 IP, 无需重新配置

---

### 4.3 TCP 模块

#### TCP-01: TCP_SERVER_OPEN

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | Port | 8080 |
| 2 | MaxConn | 3 |
| 3 | AcceptMode | 0x01 (自动) |
| 4 | KeepAlive | 0x3C (60s) |

**预期**: Status=0x00, ServerHandle 0x0001-0x7FFF, ActualPort=8080

#### TCP-06: TCP_SEND

**前置**: 客户端已连接, ClientHandle=C1

**请求**: ConnHandle=C1, Data="Hello Client" (12 bytes)

**预期**: Status=0x00, ActualLen=12, 对端收到 "Hello Client"

#### TCP-08: TCP_CLIENT_CONNECT

**请求**: DestIP=PC IP, DestPort=9090, TimeoutSec=5

**预期**: Status=0x00, ConnHandle 合法, LocalIP=ESP32 IP

#### TCP-25: 完整生命周期

```
SERVER_OPEN → ACCEPT → SEND → RECV → STATUS → DISCONNECT → DISCONNECT_EVENT → SERVER_CLOSE
```

8 步依次成功

#### TCP-30: TCP_LIST_CLIENTS

**请求**: ServerHandle=SH
**预期**: Status=0x00, ClientCount=2, 条目含 ClientHandle/ClientIP/ClientPort/ConnectTime

#### TCP-32: TCP_KICK_CLIENT

**请求**: ClientHandle=CH, ForceFlag=0x01
**预期**: Status=0x00 → TCP_DISCONNECT_EVENT(CH, Reason=0x01) → LIST_CLIENTS 确认已移除

#### TCP-34: TCP_CONN_STATUS

**请求**: ConnHandle=CH
**预期**: ConnState=0x00 (ESTABLISHED), TxBytes/RxBytes/RemoteIP/LocalPort/ConnectTime 有效

---

### 4.4 UDP 模块

#### UDP-01: UDP_SERVER_OPEN

**请求**: Port=8081, BroadcastMode=0, MulticastAddr=0

**预期**: Status=0x00, ServerHandle 合法, ActualPort=8081

#### UDP-04: UDP_CLIENT_CREATE

**请求**: DefaultDestIP=PC IP, DefaultDestPort=8083, LocalPort=0 (auto)

**预期**: Status=0x00, ClientHandle 合法, ActualPort 非零

#### UDP-05: UDP_CLIENT_SEND

**请求**: ClientHandle=CH, AddrMode=0x00, Data="Client Hello"

**预期**: Status=0x00, 对端收到 12 字节

---

### 4.5 WebSocket 模块

#### WS-01: WS_SERVER_OPEN

**请求**: Port=8084, MaxConn=3, Path="/ws"

**预期**: Status=0x00, ServerHandle 合法, ActualPort=8084

#### WS-03: WS_SEND Text

**请求**: ConnHandle=CH, MsgType=0x01, Data="Hello WS Text" (13 bytes)

**预期**: Status=0x00, 对端收到 Text 消息

#### WS-04: WS_SEND Binary

**请求**: MsgType=0x02, Data=0x00 0xFF 0x42 0x7E

**预期**: Status=0x00, 对端收到 4 字节二进制

#### WS-06: WS_SEND Ping

**请求**: MsgType=0x09 (Ping), Data=""

**预期**: Status=0x00, 客户端收到 Pong 回复

#### WS-13: 完整生命周期

```
SERVER_OPEN → ACCEPT → SEND Text → RECV Text → SEND Binary → SEND Ping → DISCONNECT(1000) → DISCONNECT_EVENT → SERVER_CLOSE
```

#### WS-15: Close 帧

**请求**: MsgType=0x08, DataLen=2, CloseCode=1000

**预期**: Status=0x00, 对端收到 Close 帧, 设备发出 WS_DISCONNECT_EVENT

---

### 4.6 MCP Network Monitor 对端测试 (NM)

MCP NM 测试不依赖外部辅助 PC，利用 Kilo Agent 内置的 `network-monitor-mcp` 工具作为网络对端。

#### NM-TCP-01: TCP Client → NM Server (10 步)

1. `[NM]` 启动 TCP Server: listenPort=9191
2. `[COM35]` NET_STATUS 获取 HEX IP
3. `[COM35]` TCP_CLIENT_CONNECT(PC_IP, 9191) → Status=0x00
4. `[NM]` 验证 client 已连接
5. `[COM35]` TCP_SEND("Hello from HEX-Bridge") → Status=0x00
6. `[NM]` read_network_buffer → 包含 "Hello from HEX-Bridge"
7. `[NM]` send_network_data("Hello from MCP NM")
8. `[COM35]` 等待 TCP_RECV("Hello from MCP NM")
9. `[COM35]` TCP_CLIENT_DISCONNECT → Status=0x00
10. 清理

#### NM-WS-01: WS Server Text 收发 (9 步)

1. `[COM35]` WS_SERVER_OPEN(Port=9199, Path="/test")
2. `[NM]` WS Client 连接 ws://<HEX IP>:9199/test
3. `[COM35]` WS_ACCEPT 事件 (ClientHandle=CH)
4. `[NM]` send_network_data("Hello WebSocket")
5. `[COM35]` WS_RECV(CH, Text, "Hello WebSocket")
6. `[COM35]` WS_SEND(CH, Text, "WS ACK")
7. `[NM]` read_network_buffer → "WS ACK"
8. `[COM35]` WS_CLIENT_DISCONNECT(CH, CloseCode=1000)
9. `[COM35]` WS_SERVER_CLOSE

#### NM-INT-01: 3 协议并发

同一设备上运行 TCP Server (9300) + UDP Server (9301) + WS Server (9302)，NM 同时连接 3 个 Server，交错收发各 2 条消息，验证互不干扰。

---

## 5. 错误码覆盖矩阵

| 错误码 | 名称 | 覆盖用例 | 结果 |
|:---|:---|:---|:---|
| 0x00 | SUCCESS | 所有正常流程 | ⏭ PENDING |
| 0x02 | ERR_PARAM | NET-05, NET-09, STR-05, STR-10 | ⏭ PENDING |
| 0x06 | ERR_NOT_SUPPORT | STR-06, STR-09 | ⏭ PENDING |
| 0x0A | ERR_CHANNEL_INVALID | NET-08 | ⏭ PENDING |
| 0x40 | ERR_NET_DISCONNECTED | TCP-16, TCP-24 | ⏭ PENDING |
| 0x41 | ERR_NET_CONN_REFUSED | TCP-10 | ⏭ PENDING |
| 0x42 | ERR_NET_TIMEOUT | TCP-09 | ⏭ PENDING |
| 0x43 | ERR_NET_HANDLE_INVALID | TCP-15, TCP-18, TCP-33, TCP-35, UDP-13, WS-20 | ⏭ PENDING |
| 0x44 | ERR_NET_BUFFER_FULL | TCP-26 | ⏭ PENDING |
| 0x45 | ERR_NET_PORT_IN_USE | TCP-03 | ⏭ PENDING |
| 0x46 | ERR_NET_DNS_FAIL | NET-04, NET-11 | ⏭ PENDING |
| 0x47 | ERR_NET_NO_IP | NET-13, TCP-29, UDP-14, WS-18 | ⏭ PENDING |
| 0x48 | ERR_NET_MAX_CONN | TCP-04, TCP-27, UDP-11, UDP-12 | ⏭ PENDING |
| 0x49 | ERR_NET_WS_HANDSHAKE | WS-10 | ⏭ PENDING |

---

## 6. 文件清单

### 6.1 固件代码 (待实现)

| 文件 | 说明 | 状态 |
|:---|:---|:---|
| `main/modules/mod_network.h/.c` | 网络配置模块 (NET_CONFIG, NET_STATUS, NET_DNS, NET_LIST_CONNS) | ⬜ 待实现 |
| `main/modules/mod_tcp.h/.c` | TCP 模块 (Server/Client/收发/KICK/LIST_CONNS/CONN_STATUS) | ⬜ 待实现 |
| `main/modules/mod_udp.h/.c` | UDP 模块 (Server/Client/收发/广播/多播) | ⬜ 待实现 |
| `main/modules/mod_ws.h/.c` | WebSocket 模块 (Server/Client/Text/Binary/Ping/Pong/Close/KICK) | ⬜ 待实现 |
| `main/core/msg_bus.h/.c` | 消息总线 (网络事件路由) | ✅ 已实现 |

### 6.2 测试脚本

| 文件 | 说明 | 状态 |
|:---|:---|:---|
| `script/test/test_network.py` | 网络模块自动化测试 (121 用例) | ⬜ 待实现 |
| `script/cli/hex-bridge-network-cli.py` | 网络 CLI 工具 (25 命令, 100% 覆盖) | ✅ 已就绪 |
| `script/test/ubcp_client.py` | UBCP v2.0 协议客户端 | ✅ 已实现 |
| `script/test/mcp_transport.py` | MCP 传输层 (COM35 UBCP 通信) | ✅ 已实现 |

### 6.3 文档

| 文件 | 说明 |
|:---|:---|
| `files/design/test/09-Network-Tests.md` | 网络模块测试用例详细规范 (121 用例) |
| `files/design/test-report/Network-Test-Report.md` | **本报告** |

---

## 7. CLI 命令速查

已实现的 `hex-bridge-network-cli.py` 使用示例:

```bash
# 网络配置
python hex-bridge-network-cli.py --port COM35 --baud 921600 net-status --index 0
python hex-bridge-network-cli.py --port COM35 --baud 921600 net-status --index 0xFF
python hex-bridge-network-cli.py --port COM35 --baud 921600 net-dns example.com
python hex-bridge-network-cli.py --port COM35 --baud 921600 net-config --dhcp
python hex-bridge-network-cli.py --port COM35 --baud 921600 net-config --ip 192.168.1.100 --gateway 192.168.1.1 --dns1 8.8.8.8
python hex-bridge-network-cli.py --port COM35 --baud 921600 net-list-conns

# TCP Server
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open --port 8080 --maxconn 3 --accept-mode 1 --keepalive 60
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-list-clients --handle 0x1
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-kick-client --handle 0x8001 --force 1
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-close --handle 0x1 --force 1

# TCP Client
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-client-connect --ip 192.168.1.100 --port 9090
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-send --handle 0x8001 --data "Hello"
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-conn-status --handle 0x8001
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-disconnect --handle 0x8001

# TCP 手动接受
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-accept --handle 0x8002 --decision 0
python hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-close --handle 0x8001 --handle-type 0 --force 0

# UDP
python hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-open --port 8081 --broadcast
python hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-open --port 8081 --multicast 224.0.0.1
python hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-send --handle 0x1 --ip 192.168.1.100 --port 9090 --data "Hello"
python hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-create --ip 192.168.1.100 --port 8083
python hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-send --handle 0x8001 --addr-mode 0 --data "Hello"
python hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-delete --handle 0x8001
python hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-close --handle 0x1

# WebSocket
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-server-open --port 8080 --path /ws --maxconn 3
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send --handle 0x8001 --msg-type 1 --data "Hello WS"
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send --handle 0x8001 --msg-type 2 --hex-data "00 FF 7E 7D"
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send --handle 0x8001 --msg-type 9
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-list-clients --handle 0x1
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-kick-client --handle 0x8001 --force 1
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-client-connect --ip 192.168.1.100 --port 9090 --path /ws
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-client-disconnect --handle 0x8001 --close-code 1000
python hex-bridge-network-cli.py --port COM35 --baud 921600 ws-server-close --handle 0x1 --force 1
```

---

## 8. 结论

网络模块测试方案完整覆盖:

- **4 个子模块**: 网络配置 / TCP / UDP / WebSocket
- **25 个命令码**: 100% CLI 工具覆盖 (`hex-bridge-network-cli.py`)
- **121 个测试用例**: 涵盖正常流程、错误路径、边界条件、压力测试、集成测试
- **14 个错误码**: 全覆盖矩阵

当前固件侧网络模块尚未实现，CLI 工具和测试方案已就绪，待固件开发完成后可立即执行自动化验证。
