# 09. 网络模块 MCP 辅助测试用例

> 命令码范围：`0x40-0x4F` (网络配置), `0x50-0x5F` (TCP), `0x60-0x6F` (UDP), `0x70-0x7F` (WebSocket)
> 模块：`mod_network` + `mod_tcp` + `mod_udp` + `mod_ws`
> **CLI 工具**: `python script/cli/hex-bridge-network-cli.py`
> **网络对端工具**: MCP Network Monitor (Kilo Agent 集成)
> **事件监听工具**: Serial Monitor (COM35, Kilo Agent 集成)

---

## 测试拓扑

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         同一台 PC                                          │
│                                                                            │
│  ┌─────────────────────┐          ┌─────────────────────────────┐         │
│  │ hex-bridge-network-  │  COM35   │ Network Monitor               │        │
│  │ cli.py (CLI 命令)   │←────────→│ (TCP/UDP/WS Server/Client)   │        │
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

**数据流说明**:

| 方向 | 路径 |
|:---|:---|
| MCP 命令 | `hex-bridge-network-cli.py` (COM35, 921600 bps) → HEX-Bridge |
| MCP 响应/事件 | HEX-Bridge → COM35 → CLI 输出 / Serial Monitor |
| HEX-Bridge 网络数据发送 | CLI 命令 → HEX-Bridge → Ethernet → MCP Network Monitor |
| HEX-Bridge 网络数据接收 | MCP Network Monitor → Ethernet → HEX-Bridge → MCP 事件 → COM35 |
| DNS 解析 | CLI 命令 → HEX-Bridge → DNS 服务器 → 响应 |

---

## 测试环境

| 项目 | 要求 |
|:---|:---|
| 被测设备 | HEX-Bridge (ESP32, 固件中已实现以太网模块) |
| MCP 通信口 | COM35, UART1, 115200 bps, 8N1 |
| 网络环境 | 局域网 DHCP 服务可用, 网线已连接 |
| 调试输出 | COM34, UART0, 115200 bps |
| CLI 工具 | `python script/cli/hex-bridge-network-cli.py --port COM35 <subcommand>` |
| 网络对端工具 | **MCP Network Monitor** (Kilo Agent, 创建 TCP/UDP/WS Server/Client 作为 HEX-Bridge 网络对端) |
| 事件监听工具 | **Serial Monitor** (Kilo Agent, 仅用于监听 COM35 接收 UBCP 事件帧, 不发送命令) |
| 协议版本 | UBCP v2.0 (`0x02`) |

> **工具分工说明**:
> - **CLI** (`hex-bridge-network-cli.py`): 发送 UBCP 命令, 接收 UBCP 响应 — 这是唯一与 HEX-Bridge 交互的入口。
> - **MCP Network Monitor**: 仅充当 TCP/UDP/WebSocket 网络对端 (Server 或 Client), 用于验证 HEX-Bridge 的网络数据收发。
> - **Serial Monitor**: 仅用于被动监听 COM35 上的 UBCP **事件帧** (TCP_RECV, WS_RECV, DISCONNECT_EVENT 等), 不主动发送命令。
> - **COM34 调试口**: 仅用于查看 ESP32 运行日志, 不参与测试交互。

## 前置条件

1. 固件已烧录并运行, LAN8720 驱动初始化成功
2. 网线已插入, 链路 UP (可通过 COM34 日志确认 `Ethernet Link Up`)
3. DHCP 已获取到 IP 地址 (可通过 `net-status` 命令确认)
4. 完成握手流程：`PING (0x00)` + `GET_INFO (0x01)`
5. Kilo Agent 已加载 `serial-monitor-mcp` 和 `network-monitor-mcp` 工具
6. CLI 基础命令格式 (以下用例中简写): `python script/cli/hex-bridge-network-cli.py --port COM35 <subcommand>`

---

## CLI 命令速查

| CLI 子命令 | 对应 UBCP 命令码 | 说明 |
|:---|:---|:---|
| `net-config` | `0x40` | 网络配置 (DHCP/静态 IP) |
| `net-status` | `0x41` | 查询网络状态 |
| `net-dns` | `0x42` | DNS 域名解析 |
| `net-list-conns` | `0x44` | 全局连接概览 |
| `tcp-server-open` | `0x50` | 创建 TCP Server |
| `tcp-server-close` | `0x51` | 关闭 TCP Server |
| `tcp-client-connect` | `0x52` | TCP Client 连接远端 |
| `tcp-disconnect` | `0x53` | 断开 TCP 连接 |
| `tcp-send` | `0x54` | TCP 发送数据 |
| `tcp-accept` | `0x56` | 手动接受/拒绝客户端 |
| `tcp-close` | `0x57` | 通用关闭 (连接或 Server) |
| `tcp-list-clients` | `0x59` | 查询 Server 客户端列表 |
| `tcp-kick-client` | `0x5A` | 强制断开指定客户端 |
| `tcp-conn-status` | `0x5B` | 查询单连接状态 |
| `udp-server-open` | `0x60` | 创建 UDP Server |
| `udp-server-close` | `0x61` | 关闭 UDP Server |
| `udp-client-create` | `0x62` | 创建 UDP Client |
| `udp-client-delete` | `0x63` | 删除 UDP Client |
| `udp-server-send` | `0x64` | 通过 Server 发送 UDP 数据 |
| `udp-client-send` | `0x66` | 通过 Client 发送 UDP 数据 |
| `ws-server-open` | `0x70` | 创建 WebSocket Server |
| `ws-server-close` | `0x71` | 关闭 WebSocket Server |
| `ws-client-connect` | `0x72` | WebSocket Client 连接远端 |
| `ws-client-disconnect` | `0x73` | WebSocket 断开 |
| `ws-send` | `0x74` | WebSocket 发送数据 |
| `ws-list-clients` | `0x78` | 查询 WS Server 客户端列表 |
| `ws-kick-client` | `0x79` | 强制断开 WS 客户端 |

---

## MCP Network Monitor 操作速查

### 创建网络对端

**TCP Server** (接受 HEX-Bridge 连接):
```
connect_network: connId="nm-tcp-srv", protocol="tcp", role="server", listenPort=9190
```

**TCP Client** (连接 HEX-Bridge Server):
```
connect_network: connId="nm-tcp-cli", protocol="tcp", role="client", host="<HEX_IP>", port=9191
```

**UDP Server** (监听):
```
connect_network: connId="nm-udp-srv", protocol="udp", role="server", listenPort=9192
```

**UDP Client** (向 HEX-Bridge 发送):
```
connect_network: connId="nm-udp-cli", protocol="udp", role="client", host="<HEX_IP>", port=9193
```

**WebSocket Server** (接受 HEX-Bridge 连接):
```
connect_network: connId="nm-ws-srv", protocol="websocket", role="server", listenPort=9194, path="/ws"
```

**WebSocket Client** (连接 HEX-Bridge Server):
```
connect_network: connId="nm-ws-cli", protocol="websocket", role="client", url="ws://<HEX_IP>:9195/ws"
```

### 数据与状态操作

| 操作 | MCP NM 调用 |
|:---|:---|
| 发送数据 | `send_network_data(connId="<id>", data="...", format="string")` |
| 发送 Hex | `send_network_data(connId="<id>", data="00 FF 7E", format="hex")` |
| 读取接收 | `read_network_buffer(port="<id>", display="string")` |
| 读取 Hex | `read_network_buffer(port="<id>", display="hex")` |
| 查看客户端 | `get_network_clients(connId="<id>")` |
| 查看状态 | `get_network_status(connId="<id>")` |
| 断开连接 | `disconnect_network(connId="<id>")` |
| 断开客户端 | `disconnect_network_client(connId="<id>", clientId="<client>")` |

---

## 测试约定

> **`<HEX_IP>`** 表示 HEX-Bridge 以太网口的 IP 地址 (由 `net-status` 获取)。
> **`<PC_IP>`** 表示运行 CLI 的 PC 在本局域网的 IP 地址 (由 `ipconfig` 获取)。
> CLI 输出中 `Status=OK` 表示 `0x00`, `ERR 0xNN` 表示错误码 `0xNN`。

---

# 第一部分：网络配置模块 (NET, 0x40-0x4F)

---

## NET-01: net-status — 查询 ETH0 网络状态

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 CLI 可查询 HEX-Bridge 以太网状态 |
| **CLI 命令** | `net-status` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-status
   ```

2. 验证响应:
   - `Status=OK`
   - `Link=UP`
   - `Conn=已连接`
   - `IP` 为有效非零 IP 地址
   - `MAC` 为 6 字节十六进制格式

**判定**: PASS — Status=OK, Link=UP, IP 非零

---

## NET-02: net-status — 查询所有接口 (--index 0xFF)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 InterfaceIndex=0xFF 查询所有接口 |
| **CLI 命令** | `net-status --index 255` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-status --index 255
   ```

2. 验证响应: 与 NET-01 结果一致

**判定**: PASS — 与 NET-01 结果一致

---

## NET-03: net-dns — 域名解析成功

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 DNS 解析返回正确 IP 地址 |
| **CLI 命令** | `net-dns <hostname>` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-dns example.com
   ```

2. 验证响应:
   - `Status=OK`
   - `AddrCount >= 1`
   - IP 地址列表格式正确

**判定**: PASS — Status=OK, AddrCount>=1

---

## NET-04: net-dns — 不存在的域名 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证不存在域名返回 DNS_FAIL |
| **CLI 命令** | `net-dns <non-existent>` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-dns nonexistent-domain.invalid
   ```

2. 预期响应: `Status=ERR 0x46` (ERR_NET_DNS_FAIL)

**判定**: PASS — 返回 DNS_FAIL

---

## NET-05: net-config — 设置静态 IP

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证静态 IP 配置生效 |
| **CLI 命令** | `net-config --ip <IP> --mask <MASK> --gateway <GW> --dns1 <DNS>` |

> **注意**: 此测试会修改 HEX-Bridge 的 IP 地址, 测试后需恢复 DHCP。

**测试步骤**:

1. 记录当前 DHCP IP 地址 (通过 `net-status`)

2. 设置静态 IP:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-config \
       --ip 192.168.1.100 --mask 255.255.255.0 --gateway 192.168.1.1 --dns1 8.8.8.8
   ```

3. 验证响应: `Status=OK`

4. 等待 3 秒后查询状态:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-status
   ```

5. 验证 IP 为 `192.168.1.100`, Mask 为 `255.255.255.0`

6. **恢复 DHCP**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-config --dhcp
   ```

**判定**: PASS — 静态 IP 生效, 恢复 DHCP 成功

---

## NET-06: net-config — 恢复 DHCP 模式

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证从静态 IP 切换到 DHCP 生效 |
| **CLI 命令** | `net-config --dhcp` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-config --dhcp
   ```

2. 验证响应: `Status=OK`

3. 等待 10 秒, 查询状态确认 IP 由 DHCP 分配:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-status
   ```

**判定**: PASS — DHCP 恢复, IP 由 DHCP 分配

---

## NET-07: net-config — 无效 InterfaceIndex (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证无效接口索引返回错误 |
| **CLI 命令** | `net-config --dhcp` 发送到无效接口 |

> CLI 当前固定使用 InterfaceIndex=0x00, 无法直接测试此用例。
> **替代方案**: 通过 Serial Monitor 发送原始 UBCP 帧, InterfaceIndex=0x02。

```
serial-monitor-mcp_send_serial_data
  port="COM35"
  data="AA 55 <frame with cmd=0x40, payload=02 00>" format="hex"
```

**预期响应**: Status=`0x0A` (ERR_CHANNEL_INVALID)

**判定**: PASS — 返回 ERR_CHANNEL_INVALID

---

## NET-08: net-list-conns — 全局连接概览

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证空连接状态下一键汇总正确 |
| **CLI 命令** | `net-list-conns` |

**前置**: 确保无活跃 TCP/UDP/WS 连接

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-list-conns
   ```

2. 验证响应: `Status=OK`, `Connections: 0`

**判定**: PASS — 空列表正确

---

## NET-09: net-status — 网线拔出时查询

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证断线状态正确反映 |
| **CLI 命令** | `net-status` |

**前置**: 拔出网线, 等待 5 秒

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-status
   ```

2. 验证响应:
   - `Link=DOWN`
   - `Conn=未连接`
   - `IP=0.0.0.0`

3. 重新插入网线, 等待获取 IP 后执行 `net-status` 确认恢复

**判定**: PASS — 断线状态正确

---

# 第二部分：TCP 模块 (TCP, 0x50-0x5F)

---

## TCP-01: tcp-server-open + MCP NM Client 端到端收发

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge TCP Server 接受 MCP NM Client 连接并双向收发 |
| **涉及工具** | CLI + MCP NM + Serial Monitor (监听事件) |

**测试步骤**:

1. **[CLI] 创建 TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open \
       --port 9191 --maxconn 3 --accept-mode 1
   ```
   记录 `Status=OK, handle=0x<SH>, port=9191`

2. **[MCP NM] 创建 TCP Client 连接 HEX-Bridge**:
   ```
   connect_network: connId="nm-tcp-cli", protocol="tcp", role="client", host="<HEX_IP>", port=9191
   ```

3. **[Serial Monitor] 等待 TCP_ACCEPT 事件** — 记录 `ClientHandle=0x<CH>`

4. **[MCP NM] 发送数据**:
   ```
   send_network_data(connId="nm-tcp-cli", data="Hello from NM", format="string")
   ```

5. **[Serial Monitor] 等待 TCP_RECV 事件** — 验证 `Data="Hello from NM"`, `ConnHandle=<CH>`

6. **[CLI] TCP_SEND 回复**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-send \
       --handle 0x<CH> --data "Hello from HEX"
   ```
   验证 `Status=OK, sent=15 bytes`

7. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-tcp-cli", display="string")
   ```
   预期包含 `"Hello from HEX"`

8. **清理**:
   - [MCP NM] `disconnect_network(connId="nm-tcp-cli")`
   - [CLI] `tcp-server-close --handle 0x<SH> --force 1`

**判定**: PASS — 双向收发正确

---

## TCP-02: tcp-client-connect + MCP NM Server 端到端收发

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 作为 TCP Client 连接 MCP NM Server |
| **涉及工具** | CLI + MCP NM + Serial Monitor (监听事件) |

**测试步骤**:

1. **[MCP NM] 启动 TCP Server**:
   ```
   connect_network: connId="nm-tcp-srv", protocol="tcp", role="server", listenPort=9192
   ```

2. **[CLI] TCP_CLIENT_CONNECT**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-client-connect \
       --ip <PC_IP> --port 9192 --connect-timeout 5
   ```
   验证 `Status=OK, handle=0x<CH>`, local IP 有效

3. **[MCP NM] 验证 Client 已连接**:
   ```
   get_network_clients(connId="nm-tcp-srv")
   ```
   预期有 1 个 client

4. **[CLI] TCP_SEND 发送数据**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-send \
       --handle 0x<CH> --data "Hello from HEX Client"
   ```
   验证 `Status=OK`

5. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-tcp-srv", display="string")
   ```
   预期包含 `"Hello from HEX Client"`

6. **[MCP NM] 发送回包**:
   ```
   send_network_data(connId="nm-tcp-srv", data="Reply from NM", format="string")
   ```

7. **[Serial Monitor] 等待 TCP_RECV 事件** — 验证 `Data="Reply from NM"`

8. **清理**:
   - [CLI] `tcp-disconnect --handle 0x<CH> --method 0`

**判定**: PASS — HEX-Bridge TCP Client 双向收发正确

---

## TCP-03: tcp-client-connect — 连接超时 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证连接无监听端口时返回超时错误 |
| **CLI 命令** | `tcp-client-connect --ip <IP> --port <无服务端口> --connect-timeout 2` |

**测试步骤**:

1. 执行命令 (连接到未监听端口):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-client-connect \
       --ip 127.0.0.1 --port 19999 --connect-timeout 2
   ```

2. 预期响应: `Status=ERR 0x42` (ERR_NET_TIMEOUT) 或 `0x41` (ERR_NET_CONN_REFUSED)

**判定**: PASS — 返回超时/拒绝错误

---

## TCP-04: tcp-server-open — 端口已被占用 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证端口冲突时返回错误 |
| **CLI 命令** | `tcp-server-open --port <已占用端口>` |

**测试步骤**:

1. 创建第一个 TCP Server:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open --port 9193
   ```
   预期 `Status=OK, handle=0x<SH>`

2. 创建第二个 TCP Server (相同端口):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open --port 9193
   ```

3. 预期响应: `Status=ERR 0x45` (ERR_NET_PORT_IN_USE)

4. **清理**: `tcp-server-close --handle 0x<SH> --force 1`

**判定**: PASS — 端口冲突返回 ERR_NET_PORT_IN_USE

---

## TCP-05: tcp-server-open — 自动分配端口

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 Port=0 时系统自动分配有效端口 |
| **CLI 命令** | `tcp-server-open --port 0` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open --port 0
   ```

2. 验证响应: `Status=OK, handle=0x<SH>, port=<非零值>`

3. **清理**: `tcp-server-close --handle 0x<SH> --force 1`

**判定**: PASS — 自动分配非零端口

---

## TCP-06: tcp-accept — 手动接受模式

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证手动接受模式中 Host 确认后连接才建立 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 TCP Server (手动接受模式)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open \
       --port 9194 --accept-mode 0
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 尝试连接**:
   ```
   connect_network: connId="nm-manual", protocol="tcp", role="client", host="<HEX_IP>", port=9194
   ```

3. **[Serial Monitor] 等待 TCP_ACCEPT 事件** — 记录 `ClientHandle=0x<CH>`

4. 延迟 3 秒不确认 → MCP NM Client 处于等待状态

5. **[CLI] 发送接受确认**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-accept \
       --handle 0x<CH> --decision 0
   ```
   验证 `Status=OK`

6. **[MCP NM] 确认连接建立**:
   ```
   get_network_status(connId="nm-manual")
   ```
   预期 status=connected

7. **清理**:
   - [MCP NM] `disconnect_network(connId="nm-manual")`
   - [CLI] `tcp-server-close --handle 0x<SH> --force 1`

**判定**: PASS — 确认后连接建立

---

## TCP-07: tcp-accept — 手动拒绝

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证手动拒绝后客户端被断开 |
| **CLI 命令** | `tcp-accept --handle <CH> --decision 1` |

**测试步骤**:

1. 创建 TCP Server (手动接受模式, port=9195)
2. MCP NM Client 尝试连接 → 收到 TCP_ACCEPT 事件 `handle=0x<CH>`
3. **[CLI] 拒绝连接**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-accept \
       --handle 0x<CH> --decision 1
   ```
4. [MCP NM] 确认 Client 被拒绝 (disconnected)

**判定**: PASS — Client 被拒绝

---

## TCP-08: tcp-disconnect — 优雅关闭与强制 RST

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证优雅关闭 (FIN) 和强制断开 (RST) 两种方式 |
| **CLI 命令** | `tcp-disconnect --handle <CH> --method 0/1` |

**测试步骤**:

1. **[MCP NM] 启动 TCP Server**:
   ```
   connect_network: connId="nm-disc-srv", protocol="tcp", role="server", listenPort=9196
   ```

2. **[CLI] TCP Client 连接**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-client-connect \
       --ip <PC_IP> --port 9196
   ```
   记录 `handle=0x<CH>`

3. 测试优雅关闭:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-disconnect \
       --handle 0x<CH> --method 0
   ```
   验证 `Status=OK`, [MCP NM] 确认 Client 收到 FIN 后断开

4. 重新连接 (得到新的 `handle=0x<CH2>`), 测试强制 RST:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-disconnect \
       --handle 0x<CH2> --method 1
   ```
   验证 `Status=OK`, [MCP NM] 确认 Client 被 RST

5. **清理**: [MCP NM] `disconnect_network(connId="nm-disc-srv")`

**判定**: PASS — 优雅关闭和强制 RST 均正确

---

## TCP-09: tcp-send + MCP NM 大数据量测试

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 1024 字节 TCP 发送无丢包 |
| **CLI 命令** | `tcp-send --handle <CH> --hex-data <1024 字节 hex>` |

**前置**: 已建立 TCP 连接 (Server 或 Client)

**测试步骤**:

1. 建立连接 (参考 TCP-01 或 TCP-02)

2. 构造 256 字节递增 hex 数据 `00 01 02 ... FF` (重复 4 次 = 1024 字节)

3. **[CLI] 发送 1024 字节**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-send \
       --handle 0x<CH> --hex-data "<1024字节hex字符串>"
   ```
   验证 `Status=OK, sent=1024 bytes`

4. **[MCP NM] 验证数据完整性**:
   ```
   read_network_buffer(port="<connId>", display="hex")
   ```
   验证收到 1024 字节, 序列连续无断点

5. **[MCP NM] 发送 1024 字节回包**
6. **[Serial Monitor] 等待 TCP_RECV**, 验证完整

**判定**: PASS — 1024 字节无丢包

---

## TCP-10: tcp-send — 广播句柄 (0x8000)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证广播句柄发送到所有已连接客户端 |
| **CLI 命令** | `tcp-send --handle 0x8000 --data "BROADCAST"` |

**测试步骤**:

1. **[CLI] 创建 TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open \
       --port 9197 --maxconn 3 --accept-mode 1
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 创建 2 个 TCP Client**:
   ```
   connect_network: connId="nm-bc-A", protocol="tcp", role="client", host="<HEX_IP>", port=9197
   connect_network: connId="nm-bc-B", protocol="tcp", role="client", host="<HEX_IP>", port=9197
   ```

3. [Serial Monitor] 等待 2 次 TCP_ACCEPT 事件

4. **[CLI] 广播发送**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-send \
       --handle 0x8000 --data "BROADCAST MSG"
   ```

5. **[MCP NM] 验证两个 Client 都收到**:
   ```
   read_network_buffer(port="nm-bc-A", display="string")
   read_network_buffer(port="nm-bc-B", display="string")
   ```
   均包含 `"BROADCAST MSG"`

6. **清理**

**判定**: PASS — 两个客户端均收到广播

---

## TCP-11: tcp-list-clients + tcp-kick-client 端到端

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证客户端列表查询和踢出功能 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-open \
       --port 9198 --maxconn 3 --accept-mode 1
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 创建 2 个 TCP Client 连接**:
   ```
   connect_network: connId="nm-lc-A", protocol="tcp", role="client", host="<HEX_IP>", port=9198
   connect_network: connId="nm-lc-B", protocol="tcp", role="client", host="<HEX_IP>", port=9198
   ```

3. [Serial Monitor] 等待 2 次 TCP_ACCEPT → 记录 `0x<CH_A>`, `0x<CH_B>`

4. **[CLI] 查询客户端列表**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 2`, 包含 `0x<CH_A>` 和 `0x<CH_B>`

5. **[CLI] 踢出 CH_A**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-kick-client \
       --handle 0x<CH_A> --force 1
   ```
   验证 `Status=OK`

6. [Serial Monitor] 等待 TCP_DISCONNECT_EVENT(0x<CH_A>)

7. **[CLI] 再次查询**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 1`, 仅包含 `0x<CH_B>`

8. [MCP NM] 确认 nm-lc-B 仍可正常收发

9. **清理**

**判定**: PASS — KICK 后目标断开, 其他客户端不受影响

---

## TCP-12: tcp-list-clients — 空 Server 查询

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证无客户端时返回 ClientCount=0 |
| **CLI 命令** | `tcp-list-clients --handle <SH>` |

**测试步骤**:

1. 创建 TCP Server (port=9199, accept-mode=1), 不连接任何客户端
2. 执行查询:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-list-clients \
       --handle 0x<SH>
   ```
3. 验证 `Clients: 0`

**判定**: PASS — 空 Server 返回 Clients: 0

---

## TCP-13: tcp-conn-status — 查询单连接状态

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证连接状态和收发统计正确 |
| **CLI 命令** | `tcp-conn-status --handle <CH>` |

**测试步骤**:

1. 建立 TCP 连接 (参考 TCP-01 或 TCP-02)

2. **[CLI] 发送数据后查询状态**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-conn-status \
       --handle 0x<CH>
   ```

3. 验证响应:
   - `State=ESTABLISHED`
   - `Tx` 为非零 (已发送数据)
   - `Remote` 为对端 IP:Port
   - `LocalPort` 正确
   - `Uptime` 有效

4. **清理**

**判定**: PASS — 状态和统计正确

---

## TCP-14: tcp-conn-status — 无效句柄 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证无效句柄返回错误 |
| **CLI 命令** | `tcp-conn-status --handle 0xFFFF` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-conn-status \
       --handle 0xFFFF
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID) 或无响应超时

**判定**: PASS — 返回错误

---

## TCP-15: tcp-send — 无效句柄 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证向无效句柄发送数据返回错误 |
| **CLI 命令** | `tcp-send --handle 0x1234 --data "test"` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-send \
       --handle 0x1234 --data "test"
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS — 返回 ERR_NET_HANDLE_INVALID

---

## TCP-16: tcp-server-close — 优雅关闭与强制关闭

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 优雅关闭 (等待子连接) 和强制关闭 两种方式 |
| **CLI 命令** | `tcp-server-close --handle <SH> --force 0/1` |

**测试步骤**:

1. 创建 TCP Server (port=9201), MCP NM Client 连接
2. **[CLI] 优雅关闭** (--force 0):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-close \
       --handle 0x<SH> --force 0
   ```
   验证 `Status=OK`, [Serial Monitor] 收到 TCP_DISCONNECT_EVENT

3. 重新创建 TCP Server (port=9202), Client 连接
4. **[CLI] 强制关闭** (--force 1):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-server-close \
       --handle 0x<SH2> --force 1
   ```
   验证 `Status=OK`

**判定**: PASS — 两种关闭方式均正确

---

## TCP-17: tcp-close — 通用关闭

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 tcp-close 可同时关闭连接或 Server |
| **CLI 命令** | `tcp-close --handle <H> --handle-type 0/1 --force 0/1` |

**测试步骤**:

1. 创建 TCP Server (port=9203), MCP NM Client 连接 → ClientHandle=0x<CH>
2. **[CLI] 关闭连接 (handle-type=0)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-close \
       --handle 0x<CH> --handle-type 0 --force 0
   ```
   验证 `Status=OK`

3. **[CLI] 关闭 Server (handle-type=1)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 tcp-close \
       --handle 0x<SH> --handle-type 1 --force 1
   ```
   验证 `Status=OK`

**判定**: PASS — tcp-close 两种类型均正确

---

## TCP-18: TCP Server 完整生命周期 (集成)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 TCP Server 创建→接受→收发→断开→关闭完整流程 |
| **顺序命令码** | `0x50` → `0x56`(event) → `0x54` → `0x59` → `0x5B` → `0x5A` → `0x51` |

**测试步骤**:

1. **SERVER_OPEN**: `tcp-server-open --port 0 --accept-mode 1` → SH
2. **MCP NM 连接** → Serial Monitor 收到 TCP_ACCEPT → CH
3. **SEND**: `tcp-send --handle 0x<CH> --data "Hello"`
4. **LIST**: `tcp-list-clients --handle 0x<SH>` → Clients: 1
5. **STATUS**: `tcp-conn-status --handle 0x<CH>` → ESTABLISHED
6. **MCP NM 发回数据** → Serial Monitor 收到 TCP_RECV
7. **KICK**: `tcp-kick-client --handle 0x<CH> --force 1` → DISCONNECT_EVENT
8. **SERVER_CLOSE**: `tcp-server-close --handle 0x<SH> --force 1`

**预期**: 全部 8 步依次成功

**判定**: PASS — 完整生命周期正确

---

# 第三部分：UDP 模块 (UDP, 0x60-0x6F)

---

## UDP-01: udp-server-open + udp-server-send 端到端

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge UDP Server 与 MCP NM UDP Client 双向收发 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 UDP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-open \
       --port 9201
   ```
   验证 `Status=OK, handle=0x<SH>, port=9201`

2. **[MCP NM] 创建 UDP Client**:
   ```
   connect_network: connId="nm-udp-cli", protocol="udp", role="client", host="<HEX_IP>", port=9201
   ```

3. **[MCP NM] 发送 UDP 数据**:
   ```
   send_network_data(connId="nm-udp-cli", data="UDP HELLO", format="string")
   ```

4. **[Serial Monitor] 等待 UDP_RECV 事件** — 验证 `Data="UDP HELLO"`, 源 IP/Port 正确

5. **[CLI] UDP_SERVER_SEND 回复** (使用 Serial Monitor 中记录的源端口):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-send \
       --handle 0x<SH> --ip <PC_IP> --port <SrcPort> --data "UDP ACK"
   ```
   验证 `Status=OK, sent=7 bytes`

6. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-udp-cli", display="string")
   ```
   预期包含 `"UDP ACK"`

7. **清理**:
   - [MCP NM] `disconnect_network(connId="nm-udp-cli")`
   - [CLI] `udp-server-close --handle 0x<SH>`

**判定**: PASS — UDP 双向收发正确

---

## UDP-02: udp-client-create + udp-client-send 端到端

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge UDP Client 生命周期 (Create → Send → Delete) |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[MCP NM] 创建 UDP Server**:
   ```
   connect_network: connId="nm-udp-srv", protocol="udp", role="server", listenPort=9202
   ```

2. **[CLI] 创建 UDP Client**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-create \
       --ip <PC_IP> --port 9202
   ```
   验证 `Status=OK, handle=0x<CH>, local_port=<实际端口>`

3. **[CLI] 使用默认地址发送** (--addr-mode 0):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 0 --data "UDP FROM HEX"
   ```
   验证 `Status=OK, sent=13 bytes`

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-udp-srv", display="string")
   ```
   预期包含 `"UDP FROM HEX"`

5. **[MCP NM] 发送回包** → [Serial Monitor] 等待 UDP_RECV 事件

6. **[CLI] 删除 Client**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-delete \
       --handle 0x<CH>
   ```
   验证 `Status=OK`

7. **[CLI] 删除后再次发送 (验证句柄失效)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 0 --data "SHOULD FAIL"
   ```
   预期 `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

8. **清理**: [MCP NM] `disconnect_network(connId="nm-udp-srv")`

**判定**: PASS — 生命周期完整, 删除后句柄失效

---

## UDP-03: udp-client-send — 使用指定地址覆盖

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 AddrMode=1 时使用指定地址而非默认地址 |
| **CLI 命令** | `udp-client-send --handle <CH> --addr-mode 1 --ip <IP> --port <PORT> --data <text>` |

**测试步骤**:

1. [MCP NM] 创建 2 个 UDP Server 监听:
   - `connId="nm-srv-A"`, listenPort=9203
   - `connId="nm-srv-B"`, listenPort=9204

2. **[CLI] 创建 UDP Client** (默认地址 → Srv A):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-create \
       --ip <PC_IP> --port 9203
   ```

3. **[CLI] 使用指定地址发送到 Srv B**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 1 --ip <PC_IP> --port 9204 --data "Override to B"
   ```

4. 验证:
   - `read_network_buffer(port="nm-srv-A")` → 无 "Override to B"
   - `read_network_buffer(port="nm-srv-B")` → 包含 "Override to B"

5. **[CLI] 使用默认地址发送**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 0 --data "Default to A"
   ```

6. 验证:
   - `read_network_buffer(port="nm-srv-A")` → 包含 "Default to A"
   - `read_network_buffer(port="nm-srv-B")` → 无 "Default to A"

7. **清理**

**判定**: PASS — 地址覆盖和默认地址均正确

---

## UDP-04: udp-server-open — 广播模式

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 UDP 广播发送到 255.255.255.255 |
| **CLI 命令** | `udp-server-open --port <PORT> --broadcast` |

**测试步骤**:

1. **[CLI] 创建启用广播的 UDP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-open \
       --port 9205 --broadcast
   ```

2. **[MCP NM] 创建 UDP Server 监听**:
   ```
   connect_network: connId="nm-bc-udp", protocol="udp", role="server", listenPort=9205
   ```

3. **[CLI] 广播发送**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-send \
       --handle 0x<SH> --ip 255.255.255.255 --port 9205 --data "BROADCAST UDP"
   ```

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-bc-udp", display="string")
   ```
   预期包含 `"BROADCAST UDP"`

5. **清理**

**判定**: PASS — 广播数据到达

---

## UDP-05: udp-server-open — 多播模式

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 UDP 多播组加入和发送 |
| **CLI 命令** | `udp-server-open --port <PORT> --multicast <MULTICAST_IP>` |

**测试步骤**:

1. **[CLI] 创建启用多播的 UDP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-open \
       --port 9206 --multicast 224.0.0.1
   ```

2. **[MCP NM] 创建加入多播组的 UDP Server**:
   ```
   connect_network: connId="nm-mc-udp", protocol="udp", role="server", listenPort=9206, multicastAddress="224.0.0.1"
   ```

3. **[CLI] 发送到多播组**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-send \
       --handle 0x<SH> --ip 224.0.0.1 --port 9206 --data "MULTICAST UDP"
   ```

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-mc-udp", display="string")
   ```
   预期包含 `"MULTICAST UDP"`

5. **清理**

**判定**: PASS — 多播数据到达

---

## UDP-06: udp-server-send — 无效句柄 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证无效 ServerHandle 返回错误 |
| **CLI 命令** | `udp-server-send --handle 0x0000 --ip <IP> --port <PORT> --data "test"` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-send \
       --handle 0x0000 --ip 192.168.1.1 --port 9999 --data "test"
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS — 返回 ERR_NET_HANDLE_INVALID

---

## UDP-07: udp-server-close + udp-client-delete — 无效句柄 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证无效句柄关闭/删除返回错误 |
| **CLI 命令** | `udp-server-close --handle 0x0000` / `udp-client-delete --handle 0x0000` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-server-close \
       --handle 0x0000
   ```
   预期 `Status=ERR 0x43`

2. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 udp-client-delete \
       --handle 0x0000
   ```
   预期 `Status=ERR 0x43`

**判定**: PASS — 均返回 ERR_NET_HANDLE_INVALID

---

# 第四部分：WebSocket 模块 (WS, 0x70-0x7F)

---

## WS-01: ws-server-open + MCP NM WS Client Text 收发

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge WS Server 握手 + Text 收发 + Close 码 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 WS Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-server-open \
       --port 9201 --maxconn 3 --path /test
   ```
   验证 `Status=OK, handle=0x<SH>, port=9201`

2. **[MCP NM] WebSocket Client 连接**:
   ```
   connect_network: connId="nm-ws-cli", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9201/test"
   ```

3. **[Serial Monitor] 等待 WS_ACCEPT 事件** — 记录 `ServerHandle=<SH>`, `ClientHandle=0x<CH>`, `Path="/test"`

4. **[MCP NM] 发送 WebSocket Text**:
   ```
   send_network_data(connId="nm-ws-cli", data="Hello WebSocket", format="string")
   ```

5. **[Serial Monitor] 等待 WS_RECV 事件** — 验证 `MsgType=0x01 (Text)`, `Data="Hello WebSocket"`

6. **[CLI] WS_SEND Text 回复**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 1 --data "WS ACK from HEX"
   ```
   验证 `Status=OK, sent=17 bytes`

7. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-ws-cli", display="string")
   ```
   预期包含 `"WS ACK from HEX"`

8. **[CLI] WS_CLIENT_DISCONNECT**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-client-disconnect \
       --handle 0x<CH> --close-code 1000
   ```
   验证 `Status=OK`

9. [Serial Monitor] 等待 WS_DISCONNECT_EVENT

10. **清理**: `ws-server-close --handle 0x<SH> --force 1`

**判定**: PASS — 全部步骤通过

---

## WS-02: ws-client-connect + MCP NM WS Server 端到端

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 作为 WS Client 连接远端 WS Server |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[MCP NM] 创建 WS Server**:
   ```
   connect_network: connId="nm-ws-srv", protocol="websocket", role="server",
                    listenPort=9202, path="/echo"
   ```

2. **[CLI] WS_CLIENT_CONNECT**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-client-connect \
       --ip <PC_IP> --port 9202 --path /echo
   ```
   验证 `Status=OK, handle=0x<CH>, result=1`

3. **[CLI] WS_SEND 发送数据**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 1 --data "Hello from HEX WS Client"
   ```
   验证 `Status=OK`

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-ws-srv", display="string")
   ```
   预期包含 `"Hello from HEX WS Client"`

5. **[MCP NM] 发送回包**:
   ```
   send_network_data(connId="nm-ws-srv", data="Echo from NM WS", format="string")
   ```

6. [Serial Monitor] 等待 WS_RECV → 验证 `Data="Echo from NM WS"`

7. **清理**:
   - [CLI] `ws-client-disconnect --handle 0x<CH> --close-code 1000`
   - [MCP NM] `disconnect_network(connId="nm-ws-srv")`

**判定**: PASS — HEX-Bridge 成功作为 WS Client 工作

---

## WS-03: ws-send — Binary 消息含特殊字节

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 WebSocket Binary 帧含 UBCP 转义字符时不破损 |
| **CLI 命令** | `ws-send --handle <CH> --msg-type 2 --hex-data "00 FF 7E 7D 42"` |

**测试步骤**:

1. WS_SERVER_OPEN (port=9203, path="/bin")
2. MCP NM WS Client 连接 → 记录 CH
3. **[CLI] 发送 Binary 含特殊字节**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 2 --hex-data "00 FF 7E 7D 42"
   ```
   验证 `Status=OK, sent=5 bytes`

4. **[MCP NM] 验证二进制完整性**:
   ```
   read_network_buffer(port="nm-bin-cli", display="hex")
   ```
   预期收到 `00 FF 7E 7D 42`, 无截断无转义

5. **清理**

**判定**: PASS — 含特殊字节的 Binary 帧收发完整

---

## WS-04: ws-send — Ping / Pong 心跳

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 WS_SEND Ping/Pong 不影响连接 |
| **CLI 命令** | `ws-send --handle <CH> --msg-type 9/10 --data ""` |

**测试步骤**:

1. WS_SERVER_OPEN + MCP NM WS Client 连接 → CH

2. **[CLI] 发送 Ping (msg-type=9)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 9
   ```
   验证 `Status=OK`

3. **[CLI] 发送 Ping 带 Payload**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 9 --data "HEARTBEAT"
   ```
   验证 `Status=OK`

4. **[CLI] 发送 Pong (msg-type=10)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 10
   ```
   验证 `Status=OK`

5. 链路仍处于 ESTABLISHED 状态, 继续发送 Text 验证连接正常

6. **清理**

**判定**: PASS — Ping/Pong 不影响连接

---

## WS-05: ws-send — 发送 Close 帧 (msg-type=8)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 WS_SEND Close 帧能正确关闭连接 |
| **CLI 命令** | `ws-send --handle <CH> --msg-type 8 --hex-data "03E8"` |

**测试步骤**:

1. WS_SERVER_OPEN + MCP NM WS Client 连接 → CH

2. **[CLI] 发送 Close 帧**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 8 --hex-data "03E8"
   ```
   验证 `Status=OK`

3. [Serial Monitor] 等待 WS_DISCONNECT_EVENT(CH, CloseCode=1000)

4. [MCP NM] 确认连接已断开

5. **清理**

**判定**: PASS — Close 帧关闭连接正确

---

## WS-06: ws-list-clients + ws-kick-client 端到端

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 WS 客户端列表查询和踢出功能 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 WS Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-server-open \
       --port 9204 --maxconn 3 --path /ws-test
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 创建 2 个 WS Client**:
   ```
   connect_network: connId="nm-ws-A", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9204/ws-test"
   connect_network: connId="nm-ws-B", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9204/ws-test"
   ```

3. [Serial Monitor] 等待 2 次 WS_ACCEPT → 记录 `0x<CH_A>`, `0x<CH_B>`

4. **[CLI] 查询客户端**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 2`

5. **[CLI] 踢出 CH_A**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-kick-client \
       --handle 0x<CH_A> --force 1
   ```
   验证 `Status=OK`

6. [Serial Monitor] 等待 WS_DISCONNECT_EVENT(CH_A)

7. **[CLI] 再次查询**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 1`, 仅包含 CH_B

8. [MCP NM] nm-ws-B 仍可正常收发

9. **清理**

**判定**: PASS — WS KICK 功能正常

---

## WS-07: ws-kick-client — 优雅关闭 (--force 0)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证优雅关闭发送 Close 帧后断开 |
| **CLI 命令** | `ws-kick-client --handle <CH> --force 0` |

**测试步骤**:

1. WS_SERVER_OPEN + MCP NM WS Client 连接 → CH
2. **[CLI] 优雅关闭**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-kick-client \
       --handle 0x<CH> --force 0
   ```
3. [Serial Monitor] 等待 WS_DISCONNECT_EVENT(CH, Reason=0x00 正常关闭)
4. [MCP NM] 确认收到 Close 帧 (code=1000)

**判定**: PASS — 优雅关闭正确

---

## WS-08: ws-server-open — 不同路径 + 子协议

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证指定路径和子协议的 WS Server 创建 |
| **CLI 命令** | `ws-server-open --port <PORT> --path /specific --subproto "chat"` |

**测试步骤**:

1. **[CLI] 创建指定路径和子协议的 WS Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-server-open \
       --port 9205 --path /specific --subproto "chat"
   ```
   验证 `Status=OK`

2. **[MCP NM] WS Client 连接到正确路径**:
   ```
   connect_network: connId="nm-ws-path", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9205/specific"
   ```

3. [Serial Monitor] 验证 WS_ACCEPT: `Path="/specific"`, `SubProtoIndex` 可能非零

4. **[MCP NM] 尝试错误路径** — 应被拒绝:
   ```
   connect_network: connId="nm-wrong", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9205/wrong"
   ```
   预期连接失败

5. **清理**

**判定**: PASS — 路径匹配正确, 错误路径被拒绝

---

## WS-09: ws-client-connect — 握手失败 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证连接非 WS Server 时返回握手错误 |
| **CLI 命令** | `ws-client-connect --ip <PC_IP> --port <TCP_PORT> --path /` |

**测试步骤**:

1. [MCP NM] 创建普通 TCP Server (非 WS):
   ```
   connect_network: connId="nm-tcp-not-ws", protocol="tcp", role="server", listenPort=9206
   ```

2. **[CLI] WS Client 连接到 TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-client-connect \
       --ip <PC_IP> --port 9206 --path /
   ```
   预期: `Status=ERR 0x49` (ERR_NET_WS_HANDSHAKE)

3. **清理**: [MCP NM] `disconnect_network(connId="nm-tcp-not-ws")`

**判定**: PASS — 握手失败返回 ERR_NET_WS_HANDSHAKE

---

## WS-10: ws-send — 无效句柄 (错误用例)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证无效句柄返回错误 |
| **CLI 命令** | `ws-send --handle 0xFFFF --msg-type 1 --data "test"` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 ws-send \
       --handle 0xFFFF --msg-type 1 --data "test"
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS — 返回 ERR_NET_HANDLE_INVALID

---

## WS-11: WebSocket Server 完整生命周期 (集成)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 WS Server Open → Accept → Text/Binary/Ping → Disconnect → Close 完整流程 |
| **命令序列** | `0x70` → `0x76`(event) → `0x74`(Text) → `0x74`(Binary) → `0x74`(Ping) → `0x74`(Close) → `0x71` |

**测试步骤**:

1. **SERVER_OPEN**: `ws-server-open --port 0 --path /lifecycle` → SH
2. **MCP NM 连接** → Serial Monitor 收到 WS_ACCEPT → CH
3. **SEND Text**: `ws-send --handle 0x<CH> --msg-type 1 --data "Hi"` → OK
4. **SEND Binary**: `ws-send --handle 0x<CH> --msg-type 2 --hex-data "CA FE"` → OK
5. **SEND Ping**: `ws-send --handle 0x<CH> --msg-type 9` → OK
6. **MCP NM 发数据** → Serial Monitor 收到 WS_RECV
7. **SEND Close**: `ws-send --handle 0x<CH> --msg-type 8 --hex-data "03E8"` → WS_DISCONNECT_EVENT
8. **SERVER_CLOSE**: `ws-server-close --handle 0x<SH> --force 1` → OK

**预期**: 全部 8 步依次成功

**判定**: PASS — 完整生命周期正确

---

# 第五部分：集成测试 (INT)

---

## INT-01: TCP + UDP + WS 三协议并发 Server

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 TCP/UDP/WS Server 同时运行, 互不干扰 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 同时创建 3 个 Server**:
   ```bash
   # TCP Server
   tcp-server-open --port 9210 --maxconn 3 --accept-mode 1
   # UDP Server
   udp-server-open --port 9211
   # WS Server
   ws-server-open --port 9212 --maxconn 3 --path /srv
   ```
   记录 SH_TCP, SH_UDP, SH_WS

2. **[MCP NM] 同时连接 3 个 Server**:
   ```
   connect_network: connId="int-tcp", protocol="tcp", role="client", host="<HEX_IP>", port=9210
   connect_network: connId="int-udp", protocol="udp", role="client", host="<HEX_IP>", port=9211
   connect_network: connId="int-ws", protocol="websocket", role="client", url="ws://<HEX_IP>:9212/srv"
   ```

3. [Serial Monitor] 等待 TCP_ACCEPT, WS_ACCEPT 事件

4. **[CLI] 交错收发**:
   ```bash
   tcp-send --handle 0x<CH_TCP> --data "TCP-DATA-1"
   udp-server-send --handle 0x<SH_UDP> --ip <PC_IP> --port <PORT> --data "UDP-DATA-1"
   ws-send --handle 0x<CH_WS> --msg-type 1 --data "WS-DATA-1"
   tcp-send --handle 0x<CH_TCP> --data "TCP-DATA-2"
   udp-server-send --handle 0x<SH_UDP> --ip <PC_IP> --port <PORT> --data "UDP-DATA-2"
   ws-send --handle 0x<CH_WS> --msg-type 1 --data "WS-DATA-2"
   ```
   全部 Status=OK

5. **[MCP NM] 验证 3 个通道各自收到 2 条消息**:
   ```
   read_network_buffer(port="int-tcp", display="string")
   read_network_buffer(port="int-udp", display="string")
   read_network_buffer(port="int-ws", display="string")
   ```

6. **[CLI] 关闭所有 Server**

**判定**: PASS — 3 协议并发, 无串扰

---

## INT-02: HEX-Bridge 多 Client 并发连接 MCP NM Server

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 同时作为多个协议的 Client |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[MCP NM] 同时启动 3 个 Server**:
   ```
   connect_network: connId="mc-tcp-srv", protocol="tcp", role="server", listenPort=9213
   connect_network: connId="mc-udp-srv", protocol="udp", role="server", listenPort=9214
   connect_network: connId="mc-ws-srv", protocol="websocket", role="server", listenPort=9215, path="/echo"
   ```

2. **[CLI] 依次创建 3 个 Client**:
   ```bash
   tcp-client-connect --ip <PC_IP> --port 9213   → CH_TCP
   udp-client-create --ip <PC_IP> --port 9214    → CH_UDP
   ws-client-connect --ip <PC_IP> --port 9215 --path /echo  → CH_WS
   ```
   全部 Status=OK

3. **[CLI] 同时发送**:
   ```bash
   tcp-send --handle 0x<CH_TCP> --data "Multi-TCP"
   udp-client-send --handle 0x<CH_UDP> --addr-mode 0 --data "Multi-UDP"
   ws-send --handle 0x<CH_WS> --msg-type 1 --data "Multi-WS"
   ```

4. **[MCP NM] 验证**:
   ```
   read_network_buffer(port="mc-tcp-srv")  → "Multi-TCP"
   read_network_buffer(port="mc-udp-srv")  → "Multi-UDP"
   read_network_buffer(port="mc-ws-srv")   → "Multi-WS"
   ```

5. **清理**

**判定**: PASS — 多 Client 并发正常

---

## INT-03: net-list-conns — 多类型连接全局概览

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 NET_LIST_CONNS 一站式汇总所有连接 |
| **CLI 命令** | `net-list-conns` |

**测试步骤**:

1. **[CLI] 创建混合连接**:
   ```bash
   tcp-server-open --port 9216 --accept-mode 1   → SH_TCP
   udp-client-create --ip <PC_IP> --port 9217     → CH_UDP
   ```

2. **[MCP NM] 创建对端**:
   ```
   connect_network: connId="gc-tcp-cli", protocol="tcp", role="client", host="<HEX_IP>", port=9216
   connect_network: connId="gc-udp-srv", protocol="udp", role="server", listenPort=9217
   ```

3. [Serial Monitor] 等待 TCP_ACCEPT

4. **[CLI] 全局查询**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600 net-list-conns
   ```

5. 验证响应:
   - `Status=OK`
   - `Connections >= 3`
   - 包含 `[TCP_SERVER]` 条目 (handle=SH_TCP)
   - 包含 `[TCP_CONN]` 条目 (parent=SH_TCP)
   - 包含 `[UDP_CLIENT]` 条目 (handle=CH_UDP)

6. **清理**

**判定**: PASS — NET_LIST_CONNS 正确汇总

---

## INT-04: TCP + WS 多客户端列表并行查询

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 TCP 和 WS 的 LIST_CLIENTS 在客户端列表上各自独立 |
| **CLI 命令** | `tcp-list-clients`, `ws-list-clients` |

**测试步骤**:

1. **[CLI] 同时创建 TCP Server 和 WS Server**:
   ```bash
   tcp-server-open --port 9220 --accept-mode 1   → SH_TCP
   ws-server-open --port 9221 --path /list         → SH_WS
   ```

2. **[MCP NM] 各创建 1 个 Client**:
   ```
   # TCP
   connect_network: connId="lp-tcp", protocol="tcp", role="client", host="<HEX_IP>", port=9220
   # WS
   connect_network: connId="lp-ws", protocol="websocket", role="client", url="ws://<HEX_IP>:9221/list"
   ```

3. 等待 TCP_ACCEPT + WS_ACCEPT

4. **[CLI] 并行查询**:
   ```bash
   tcp-list-clients --handle 0x<SH_TCP>   → Clients: 1 (TCP)
   ws-list-clients --handle 0x<SH_WS>    → Clients: 1 (WS)
   ```

5. **[CLI] 并行踢出**:
   ```bash
   tcp-kick-client --handle 0x<CH_TCP> --force 1
   ws-kick-client --handle 0x<CH_WS> --force 1
   ```

6. 等待 TCP_DISCONNECT_EVENT + WS_DISCONNECT_EVENT

7. **[CLI] 再次查询**:
   ```bash
   tcp-list-clients --handle 0x<SH_TCP>   → Clients: 0
   ws-list-clients --handle 0x<SH_WS>    → Clients: 0
   ```

8. **清理**

**判定**: PASS — TCP 和 WS 客户端列表各自独立

---

# 第六部分：错误码覆盖矩阵

| 错误码 | 名称 | 覆盖用例 |
|:---|:---|:---|
| `0x00` | SUCCESS | 所有正常流程用例 |
| `0x02` | ERR_PARAM | NET-07 (无效 InterfaceIndex) |
| `0x06` | ERR_NOT_SUPPORT | 保留命令码 |
| `0x0A` | ERR_CHANNEL_INVALID | NET-07 |
| `0x41` | ERR_NET_CONN_REFUSED | TCP-03 (连接拒绝) |
| `0x42` | ERR_NET_TIMEOUT | TCP-03 (连接超时) |
| `0x43` | ERR_NET_HANDLE_INVALID | TCP-14/15, UDP-06/07, WS-10 |
| `0x45` | ERR_NET_PORT_IN_USE | TCP-04 |
| `0x46` | ERR_NET_DNS_FAIL | NET-04 |
| `0x47` | ERR_NET_NO_IP | NET-09 (断线时所有 OPEN/CONNECT 均返回) |
| `0x48` | ERR_NET_MAX_CONN | 创建超过最大连接数 |
| `0x49` | ERR_NET_WS_HANDSHAKE | WS-09 |

---

## 用例索引

| 分组 | 用例编号 | 数量 | 说明 |
|:---|:---|:---|:---|
| 网络配置 | NET-01 ~ NET-09 | 9 | STATUS, DNS, CONFIG (DHCP/静态IP), 错误路径, LIST_CONNS |
| TCP | TCP-01 ~ TCP-18 | 18 | Server/Client 端到端收发, 手动接受/拒绝, 优雅/强制关闭, 广播, 大数据量, LIST/KICK/STATUS, 完整生命周期, 错误用例 |
| UDP | UDP-01 ~ UDP-07 | 7 | Server/Client 端到端收发, 地址覆盖, 广播, 多播, 生命周期, 错误用例 |
| WebSocket | WS-01 ~ WS-11 | 11 | Server/Client 端到端, Text/Binary/Ping/Pong/Close, LIST/KICK, 路径匹配, 优雅关闭, 完整生命周期, 错误用例 |
| 集成测试 | INT-01 ~ INT-04 | 4 | 三协议并发 Server, 多 Client 并发, 全局概览, 并行 LIST/KICK |
| **合计** | | **49** | |

---

## 测试执行脚本参考

```bash
# CLI 基础前缀
CLI="python script/cli/hex-bridge-network-cli.py --port COM35 --baud 921600"

# 获取 HEX-Bridge IP
$CLI net-status
# 记录 IpAddr 处的 IP 地址

# 获取 PC 本机 IP (PowerShell)
ipconfig
# 记录 IPv4 地址

# 端到端测试示例 (TCP Server)
$CLI tcp-server-open --port 9191 --maxconn 3 --accept-mode 1
# → 记录 ServerHandle (SH)

# 在 Kilo Agent 中: MCP NM 创建 TCP Client
# connect_network: connId="test-cli", protocol="tcp", role="client", host="<HEX_IP>", port=9191

# 发送数据
$CLI tcp-send --handle 0x<CH> --data "Hello World"

# 在 Kilo Agent 中: MCP NM 验证接收
# read_network_buffer(port="test-cli", display="string")

# 清理
$CLI tcp-server-close --handle 0x<SH> --force 1
```
