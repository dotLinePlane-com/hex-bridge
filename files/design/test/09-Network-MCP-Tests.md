# 09. 网络模块 MCP 辅助测试用例

> 命令码范围：`0x40-0x4F` (网络配置), `0x50-0x5F` (TCP), `0x60-0x6F` (UDP), `0x70-0x7F` (WebSocket)
> 模块：`mod_network` + `mod_tcp` + `mod_udp` + `mod_ws`
> **CLI 工具**: `python script/cli/hex-bridge-network-cli.py`
> **网络对端工具**: MCP Network Monitor (Kilo Agent 集成)
> **事件监听工具**: Serial Monitor (COM4, Kilo Agent 集成)

---

## 测试拓扑

```
┌───────────────────────────────────────────────────────────────────────────�?�?                        同一�?PC                                          �?�?                                                                           �?�? ┌─────────────────────�?         ┌─────────────────────────────�?        �?�? �?hex-bridge-network-  �? COM4   �?Network Monitor               �?       �?�? �?cli.py (CLI 命令)   │←────────→│ (TCP/UDP/WS Server/Client)   �?       �?�? �?UBCP 帧收�?        �? 921600  �?充当网络对端                   �?       �?�? �?                     �?         �?                               �?       �?�? └─────────┬───────────�?         └──────────────┬──────────────�?        �?�?           �?                                     �?                       �?�?           �? UART1 (GPIO4/34)                    �?Ethernet               �?�?           �?                                     �?                       �?�?      ┌──────────────────�?      ┌──────────────────────�?                 �?�?      �?  HEX-Bridge     │←──────�? 路由�?/ DHCP        �?                 �?�?      �?  ESP32+LAN8720  �? 100  �?                     �?                 �?�?      �?                 �? Mbps �?                     �?                 �?�?      �?  UART0          │←──────�?COM5 (调试日志, 115200 bps)            �?�?      └──────────────────�?      └──────────────────────�?                 �?└───────────────────────────────────────────────────────────────────────────�?```

**数据流说�?*:

| 方向 | 路径 |
|:---|:---|
| MCP 命令 | `hex-bridge-network-cli.py` (COM4, 921600 bps) �?HEX-Bridge |
| MCP 响应/事件 | HEX-Bridge �?COM4 �?CLI 输出 / Serial Monitor |
| HEX-Bridge 网络数据发�?| CLI 命令 �?HEX-Bridge �?Ethernet �?MCP Network Monitor |
| HEX-Bridge 网络数据接收 | MCP Network Monitor �?Ethernet �?HEX-Bridge �?MCP 事件 �?COM4 |
| DNS 解析 | CLI 命令 �?HEX-Bridge �?DNS 服务�?�?响应 |

---

## 测试环境

| 项目 | 要求 |
|:---|:---|
| 被测设备 | HEX-Bridge (ESP32, 固件中已实现以太网模�? |
| MCP 通信�?| COM4, UART1, 115200 bps, 8N1 |
| 网络环境 | 局域网 DHCP 服务可用, 网线已连�?|
| 调试输出 | COM5, UART0, 115200 bps |
| CLI 工具 | `python script/cli/hex-bridge-network-cli.py --port COM4 <subcommand>` |
| 网络对端工具 | **MCP Network Monitor** (Kilo Agent, 创建 TCP/UDP/WS Server/Client 作为 HEX-Bridge 网络对端) |
| 事件监听工具 | **Serial Monitor** (Kilo Agent, 仅用于监�?COM4 接收 UBCP 事件�? 不发送命�? |
| 协议版本 | UBCP v2.0 (`0x02`) |

> **工具分工说明**:
> - **CLI** (`hex-bridge-network-cli.py`): 发�?UBCP 命令, 接收 UBCP 响应 �?这是唯一�?HEX-Bridge 交互的入口�?> - **MCP Network Monitor**: 仅充�?TCP/UDP/WebSocket 网络对端 (Server �?Client), 用于验证 HEX-Bridge 的网络数据收发�?> - **Serial Monitor**: 仅用于被动监�?COM4 上的 UBCP **事件�?* (TCP_RECV, WS_RECV, DISCONNECT_EVENT �?, 不主动发送命令�?> - **COM5 调试�?*: 仅用于查�?ESP32 运行日志, 不参与测试交互�?
## 前置条件

1. 固件已烧录并运行, LAN8720 驱动初始化成�?2. 网线已插�? 链路 UP (可通过 COM5 日志确认 `Ethernet Link Up`)
3. DHCP 已获取到 IP 地址 (可通过 `net-status` 命令确认)
4. 完成握手流程：`PING (0x00)` + `GET_INFO (0x01)`
5. Kilo Agent 已加�?`serial-monitor-mcp` �?`network-monitor-mcp` 工具
6. CLI 基础命令格式 (以下用例中简�?: `python script/cli/hex-bridge-network-cli.py --port COM4 <subcommand>`

---

## CLI 命令速查

| CLI 子命�?| 对应 UBCP 命令�?| 说明 |
|:---|:---|:---|
| `net-config` | `0x40` | 网络配置 (DHCP/静�?IP) |
| `net-status` | `0x41` | 查询网络状�?|
| `net-dns` | `0x42` | DNS 域名解析 |
| `net-list-conns` | `0x44` | 全局连接概览 |
| `net-close-all` | `0x45` | 一键关闭所�?TCP/UDP/WS 连接 |
| `tcp-server-open` | `0x50` | 创建 TCP Server |
| `tcp-server-close` | `0x51` | 关闭 TCP Server |
| `tcp-client-connect` | `0x52` | TCP Client 连接远端 |
| `tcp-disconnect` | `0x53` | 断开 TCP 连接 |
| `tcp-send` | `0x54` | TCP 发送数�?|
| `tcp-accept` | `0x56` | 手动接受/拒绝客户�?|
| `tcp-close` | `0x57` | 通用关闭 (连接�?Server) |
| `tcp-list-clients` | `0x59` | 查询 Server 客户端列�?|
| `tcp-kick-client` | `0x5A` | 强制断开指定客户�?|
| `tcp-conn-status` | `0x5B` | 查询单连接状�?|
| `udp-server-open` | `0x60` | 创建 UDP Server |
| `udp-server-close` | `0x61` | 关闭 UDP Server |
| `udp-client-create` | `0x62` | 创建 UDP Client |
| `udp-client-delete` | `0x63` | 删除 UDP Client |
| `udp-server-send` | `0x64` | 通过 Server 发�?UDP 数据 |
| `udp-client-send` | `0x66` | 通过 Client 发�?UDP 数据 |
| `ws-server-open` | `0x70` | 创建 WebSocket Server |
| `ws-server-close` | `0x71` | 关闭 WebSocket Server |
| `ws-client-connect` | `0x72` | WebSocket Client 连接远端 |
| `ws-client-disconnect` | `0x73` | WebSocket 断开 |
| `ws-send` | `0x74` | WebSocket 发送数�?|
| `ws-list-clients` | `0x78` | 查询 WS Server 客户端列�?|
| `ws-kick-client` | `0x79` | 强制断开 WS 客户�?|

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

**UDP Client** (�?HEX-Bridge 发�?:
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

### 数据与状态操�?
| 操作 | MCP NM 调用 |
|:---|:---|
| 发送数�?| `send_network_data(connId="<id>", data="...", format="string")` |
| 发�?Hex | `send_network_data(connId="<id>", data="00 FF 7E", format="hex")` |
| 读取接收 | `read_network_buffer(port="<id>", display="string")` |
| 读取 Hex | `read_network_buffer(port="<id>", display="hex")` |
| 查看客户�?| `get_network_clients(connId="<id>")` |
| 查看状�?| `get_network_status(connId="<id>")` |
| 断开连接 | `disconnect_network(connId="<id>")` |
| 断开客户�?| `disconnect_network_client(connId="<id>", clientId="<client>")` |

---

## 批量自动化测试编�?(一次跑�?

> **核心理念**: �?49 �?MCP 测试用例拆分�?**4 个执行阶�?*, 按依赖链顺序编排, 每阶段一次执行完毕后自动验证, 无需人工穿插操作�?
### 执行阶段总览

| 阶段 | 依赖 | 命令�?| 测试用例 | 执行方式 |
|:---|:---|:--|:---|:---|
| **Phase 0** 无网络自�?| COM4 + 设备上电 | ~42 CLI | NET-08/09/10/12/14/16/17/18, TCP-01/02/03/04/15/18/19/28/29/30/31/32/33, UDP-01/10/11/12/13/14, WS-01/18/19/20, STR-03/04/06/07/08/09/10, DRV-01 | `python script/test/test_network.py --auto` |
| **Phase 1** 基础网络 | 网线插入, DHCP 可用 | 12 CLI + 0 NM | NET-01/02/03/04/05, TCP-09 | `python script/test/test_network.py --test` |
| **Phase 2** Server 对端 | Phase 1 + NM 工具 | 12 CLI + 7 NM | TCP-05/06/07, UDP-01/02/03, WS-01/02/03/04/05 | NM 创建 Client �?CLI 操作 �?NM 验证 |
| **Phase 3** Client 变体 | Phase 2 | 18 CLI + 9 NM | TCP-08/12/20/21/22/23, UDP-05/06, WS-06/07/08/09/10/12/14/15/16/17/21, INT-01/02, NM-TCP-04/05, NM-WS-02, NM-INT-02, NM-STR-01 | NM 创建 Server �?CLI 操作 �?NM 验证 |

### Phase 0: test_network.py --auto (开箱即�?

```bash
# 设备上电即可执行, 无需网线, 无需 NM 工具
CLI="python script/cli/hex-bridge-network-cli.py --port COM4 --baud 115200"
$CLI net-close-all                                          # 清理残留

# 一键执�?python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --auto

# 补充执行 Phase 0 中未覆盖的容�?超时测试 (新版本已包含)
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test TCP-04
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test TCP-09
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test TCP-27
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test TCP-28
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test UDP-11
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test UDP-12
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test STR-07
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test NET-11
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test NET-17
```

### Phase 1: 网络链路确认 (需网线插入)

```bash
# 确认设备�?IP (NET-01, NET-02), DNS 正常 (NET-03/04/05), 连接超时 (TCP-09)
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test NET-01
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test NET-02
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test NET-03
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test NET-04
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --test NET-05

# 获取设备 IP (后续 Phase 2/3 需�?
$CLI net-status | grep ip
# �?ip=192.168.1.105
```

### Phase 2: Server→Client 端到端收�?(需 NM 工具创建 Client)

```bash
HEX_IP=192.168.1.105    # �?Phase 1 获取
PC_IP=192.168.1.4       # PC 本机 IP (ipconfig)
CLI="python script/cli/hex-bridge-network-cli.py --port COM4 --baud 115200"

# ==== �?.1�? TCP Server 端到�?(TCP-05/06/07, NM-TCP-02) ====
$CLI tcp-server-open --port 9191 --maxconn 3 --accept-mode 1
# NM: connect_network(tcp, client, $HEX_IP:9191) �?connId="nm-tcp-cli"
$CLI tcp-list-clients --handle 0x<SH>
# NM: send_network_data(connId="nm-tcp-cli", data="Hello from NM Client")
$CLI tcp-send --handle 0x<SH> --data "Hello from HEX-Bridge"
# NM: read_network_buffer(port="nm-tcp-cli") �?应包�?"Hello from HEX-Bridge"
$CLI tcp-server-close --handle 0x<SH> --force 1
# NM: disconnect_network(connId="nm-tcp-cli")

# ==== �?.2�? UDP Server 端到�?(UDP-01/02/03, NM-UDP-01) ====
$CLI udp-server-open --port 9201
# NM: connect_network(udp, client, $HEX_IP:9201) �?connId="nm-udp-cli"
# NM: send_network_data(connId="nm-udp-cli", data="UDP HELLO")
$CLI udp-server-send --handle 0x<SH> --ip $PC_IP --port <NM_SrcPort> --data "UDP ACK"
$CLI udp-server-close --handle 0x<SH>
# NM: disconnect_network(connId="nm-udp-cli")

# ==== �?.3�? WS Server 端到�?(WS-01/02/03/04/05, NM-WS-01/03) ====
$CLI ws-server-open --port 9201 --path /test --maxconn 3
# NM: connect_network(websocket, client, ws://$HEX_IP:9201/test) �?connId="nm-ws-cli"
$CLI ws-list-clients --handle 0x<SH>                         # should show 1 client
# NM: send_network_data(connId="nm-ws-cli", data="Hello WebSocket")
$CLI ws-send --handle 0xA000 --msg-type 1 --data "WS ACK from HEX"
# NM: read_network_buffer(port="nm-ws-cli") �?"WS ACK from HEX"
$CLI ws-send --handle 0xA000 --msg-type 2 --hex-data "00FF7E7D42"
# NM: read_network_buffer(port="nm-ws-cli", display="hex") �?00 FF 7E 7D 42
$CLI ws-client-disconnect --handle 0xA000 --close-code 1000
$CLI ws-server-close --handle 0x<SH> --force 1
# NM: disconnect_network(connId="nm-ws-cli")
```

### Phase 3: Client 变体 + 集成 (需 NM 工具创建 Server)

```bash
# ==== �?.1�? TCP Client 端到�?+ RST 断开 (TCP-08/12, NM-TCP-01) ====
# NM: connect_network(tcp, server, listenPort=9192) �?connId="nm-tcp-srv"
$CLI tcp-client-connect --ip $PC_IP --port 9192 --connect-timeout 5
$CLI tcp-send --handle 0x9001 --data "Hello from HEX Client"
# NM: read_network_buffer(port="nm-tcp-srv") �?"Hello from HEX Client"
# NM: send_network_data(connId="nm-tcp-srv", data="Reply from NM Server")
$CLI tcp-disconnect --handle 0x9001 --method 1               # TCP-12: RST
# NM: disconnect_network(connId="nm-tcp-srv")

# ==== �?.2�? TCP 手动接受/拒绝 (TCP-22/23, NM-TCP-04/05) ====
$CLI tcp-server-open --port 9194 --accept-mode 0              # manual mode
# NM: connect_network(tcp, client, $HEX_IP:9194) �?connId="nm-manual"
$CLI tcp-list-clients --handle 0x<SH>                        # shows pending client
$CLI tcp-accept --handle 0x<CH> --decision 0                  # accept �?establish
$CLI tcp-send --handle 0x<CH> --data "Manual ACK"
# NM: read_network_buffer(port="nm-manual") �?"Manual ACK"
$CLI tcp-server-close --handle 0x<SH> --force 1
# NM: disconnect_network(connId="nm-manual")

# ==== �?.3�? TCP Close HandleType=0 + 大数�?(TCP-20/21, NM-STR-01) ====
# NM: connect_network(tcp, server, listenPort=9196) �?connId="nm-big-srv"
$CLI tcp-client-connect --ip $PC_IP --port 9196
# 构�?1024 字节递增 hex 数据并发�?$CLI tcp-send --handle 0x9001 --hex-data "<256B递增x4>"
# NM: read_network_buffer(port="nm-big-srv", display="hex") �?1024B 完整
$CLI tcp-close --handle 0x9001 --handle-type 0 --force 0    # TCP-20: FIN
# NM: disconnect_network(connId="nm-big-srv")

# ==== �?.4�? WS Client 端到�?+ Ping/Pong/Close (WS-06/07/09/12, NM-WS-02) ====
# NM: connect_network(websocket, server, listenPort=9202, path="/echo") �?connId="nm-ws-srv"
$CLI ws-client-connect --ip $PC_IP --port 9202 --path /echo
$CLI ws-send --handle 0xA000 --msg-type 1 --data "Hello from HEX WS Client"
# NM: read_network_buffer(port="nm-ws-srv") �?"Hello from HEX WS Client"
$CLI ws-send --handle 0xA000 --msg-type 9                      # Ping
$CLI ws-send --handle 0xA000 --msg-type 10                     # Pong
$CLI ws-send --handle 0xA000 --msg-type 8 --hex-data "03E8"   # Close frame(1000)
$CLI ws-client-disconnect --handle 0xA000 --close-code 1000
# NM: disconnect_network(connId="nm-ws-srv")

# ==== �?.5�? WS 握手失败 + 自动 Pong (WS-10/14) ====
# NM: connect_network(tcp, server, listenPort=9206) �?connId="nm-tcp-not-ws"
$CLI ws-client-connect --ip $PC_IP --port 9206 --path /
# �?预期 ERR 0x49 (ERR_NET_WS_HANDSHAKE)
# NM: disconnect_network(connId="nm-tcp-not-ws")

# ==== �?.6�? WS 错误路径拒绝 + WS KICK (WS-16/21) ====
$CLI ws-server-open --port 9204 --path /ws-test --maxconn 3
# NM: connect_network(websocket, client, ws://$HEX_IP:9204/wrong) �?应被拒绝
$CLI ws-server-close --handle 0x<SH> --force 0               # graceful close
# NM: disconnect_all()

# ==== �?.7�? 三协�?Client 并发 (NM-INT-02) ====
# NM: connect_network(tcp, server, listenPort=9310) �?int-srv-tcp
# NM: connect_network(udp, server, listenPort=9311) �?int-srv-udp
# NM: connect_network(websocket, server, listenPort=9312, path="/echo") �?int-srv-ws
$CLI tcp-client-connect --ip $PC_IP --port 9310
$CLI udp-client-create --ip $PC_IP --port 9311
$CLI ws-client-connect --ip $PC_IP --port 9312 --path /echo
$CLI tcp-send --handle 0x<CH_TCP> --data "CONCURRENT-TCP"
$CLI udp-client-send --handle 0x<CH_UDP> --addr-mode 0 --data "CONCURRENT-UDP"
$CLI ws-send --handle 0xA000 --msg-type 1 --data "CONCURRENT-WS"
# NM: read_network_buffer �?3 protocol data all correct
$CLI net-list-conns                                           # 验证汇�?$CLI net-close-all
# NM: disconnect_all()
```

### 阶段完成检查表

| 阶段 | 验证条件 | 通过标准 |
|:---|:---|:---|
| Phase 0 | `test_network.py --auto` 输出 | PASS �?90, FAIL = 0 |
| Phase 0+ | `--test` 单独用例 | 全部 PASS �?SKIP |
| Phase 1 | NET-01 Link=UP, NET-03 DNS 解析成功 | IP 非零, AddrCount �?1 |
| Phase 2.1 | TCP Server �?NM Client 双向收发 | NM rxBytes �?21, CLI Status=OK |
| Phase 2.2 | UDP Server �?NM Client 双向收发 | CLI Status=OK, NM rxBuff 有数�?|
| Phase 2.3 | WS Server �?NM Client Text+Binary | NM rx: "WS ACK" + `00 FF 7E 7D 42` |
| Phase 3.1 | TCP Client �?NM Server + RST | NM rx: "Hello from HEX Client" |
| Phase 3.2 | TCP 手动接受/发�?| NM rx: "Manual ACK" |
| Phase 3.3 | 1024B 大数�?| NM rx: 1024B 递增序列完整 |
| Phase 3.4 | WS Client Ping/Pong/Close | `ws-send --msg-type 8/9/10` �?Status=OK |
| Phase 3.5 | WS 握手失败 + 自动 Pong | ERR 0x49 / Pong OK |
| Phase 3.6 | WS 错误路径 + KICK | wrong path �?rejected, kick �?disconnected |
| Phase 3.7 | 三协�?Client 并发 | NM 3 Server 各收到正确数�? ConnCount �?3 |

---

## 测试约定

> **`<HEX_IP>`** 表示 HEX-Bridge 以太网口�?IP 地址 (�?`net-status` 获取)�?> **`<PC_IP>`** 表示运行 CLI �?PC 在本局域网�?IP 地址 (�?`ipconfig` 获取)�?> CLI 输出�?`Status=OK` 表示 `0x00`, `ERR 0xNN` 表示错误�?`0xNN`�?
---

# 第一部分：网络配置模�?(NET, 0x40-0x4F)

---

## NET-01: net-status �?查询 ETH0 网络状�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 CLI 可查�?HEX-Bridge 以太网状�?|
| **CLI 命令** | `net-status` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-status
   ```

2. 验证响应:
   - `Status=OK`
   - `Link=UP`
   - `Conn=已连接`
   - `IP` 为有效非�?IP 地址
   - `MAC` �?6 字节十六进制格式

**判定**: PASS �?Status=OK, Link=UP, IP 非零

---

## NET-02: net-status �?查询所有接�?(--index 0xFF)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 InterfaceIndex=0xFF 查询所有接�?|
| **CLI 命令** | `net-status --index 255` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-status --index 255
   ```

2. 验证响应: �?NET-01 结果一�?
**判定**: PASS �?�?NET-01 结果一�?
---

## NET-03: net-dns �?域名解析成功

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 DNS 解析返回正确 IP 地址 |
| **CLI 命令** | `net-dns <hostname>` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-dns example.com
   ```

2. 验证响应:
   - `Status=OK`
   - `AddrCount >= 1`
   - IP 地址列表格式正确

**判定**: PASS �?Status=OK, AddrCount>=1

---

## NET-04: net-dns �?不存在的域名 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证不存在域名返�?DNS_FAIL |
| **CLI 命令** | `net-dns <non-existent>` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-dns nonexistent-domain.invalid
   ```

2. 预期响应: `Status=ERR 0x46` (ERR_NET_DNS_FAIL)

**判定**: PASS �?返回 DNS_FAIL

---

## NET-05: net-config �?设置静�?IP

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证静�?IP 配置生效 |
| **CLI 命令** | `net-config --ip <IP> --mask <MASK> --gateway <GW> --dns1 <DNS>` |

> **注意**: 此测试会修改 HEX-Bridge �?IP 地址, 测试后需恢复 DHCP�?
**测试步骤**:

1. 记录当前 DHCP IP 地址 (通过 `net-status`)

2. 设置静�?IP:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-config \
       --ip 192.168.1.100 --mask 255.255.255.0 --gateway 192.168.1.1 --dns1 8.8.8.8
   ```

3. 验证响应: `Status=OK`

4. 等待 3 秒后查询状�?
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-status
   ```

5. 验证 IP �?`192.168.1.100`, Mask �?`255.255.255.0`

6. **恢复 DHCP**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-config --dhcp
   ```

**判定**: PASS �?静�?IP 生效, 恢复 DHCP 成功

---

## NET-06: net-config �?恢复 DHCP 模式

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证从静�?IP 切换�?DHCP 生效 |
| **CLI 命令** | `net-config --dhcp` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-config --dhcp
   ```

2. 验证响应: `Status=OK`

3. 等待 10 �? 查询状态确�?IP �?DHCP 分配:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-status
   ```

**判定**: PASS �?DHCP 恢复, IP �?DHCP 分配

---

## NET-07: net-config �?无效 InterfaceIndex (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证无效接口索引返回错误 |
| **CLI 命令** | `net-config --dhcp` 发送到无效接口 |

> CLI 当前固定使用 InterfaceIndex=0x00, 无法直接测试此用例�?> **替代方案**: 通过 Serial Monitor 发送原�?UBCP �? InterfaceIndex=0x02�?
```
serial-monitor-mcp_send_serial_data
  port="COM4"
  data="AA 55 <frame with cmd=0x40, payload=02 00>" format="hex"
```

**预期响应**: Status=`0x0A` (ERR_CHANNEL_INVALID)

**判定**: PASS �?返回 ERR_CHANNEL_INVALID

---

## NET-08: net-list-conns �?全局连接概览

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证空连接状态下一键汇总正�?|
| **CLI 命令** | `net-list-conns` |

**前置**: 确保无活�?TCP/UDP/WS 连接

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-list-conns
   ```

2. 验证响应: `Status=OK`, `Connections: 0`

**判定**: PASS �?空列表正�?
---

## NET-09: net-status �?网线拔出时查�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证断线状态正确反�?|
| **CLI 命令** | `net-status` |

**前置**: 拔出网线, 等待 5 �?
**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-status
   ```

2. 验证响应:
   - `Link=DOWN`
   - `Conn=未连接`
   - `IP=0.0.0.0`

3. 重新插入网线, 等待获取 IP 后执�?`net-status` 确认恢复

**判定**: PASS �?断线状态正�?
---

# 第二部分：TCP 模块 (TCP, 0x50-0x5F)

---

## TCP-01: tcp-server-open + MCP NM Client 端到端收�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 HEX-Bridge TCP Server 接受 MCP NM Client 连接并双向收�?|
| **涉及工具** | CLI + MCP NM + Serial Monitor (监听事件) |

**测试步骤**:

1. **[CLI] 创建 TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-open \
       --port 9191 --maxconn 3 --accept-mode 1
   ```
   记录 `Status=OK, handle=0x<SH>, port=9191`

2. **[MCP NM] 创建 TCP Client 连接 HEX-Bridge**:
   ```
   connect_network: connId="nm-tcp-cli", protocol="tcp", role="client", host="<HEX_IP>", port=9191
   ```

3. **[Serial Monitor] 等待 TCP_ACCEPT 事件** �?记录 `ClientHandle=0x<CH>`

4. **[MCP NM] 发送数�?*:
   ```
   send_network_data(connId="nm-tcp-cli", data="Hello from NM", format="string")
   ```

5. **[Serial Monitor] 等待 TCP_RECV 事件** �?验证 `Data="Hello from NM"`, `ConnHandle=<CH>`

6. **[CLI] TCP_SEND 回复**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-send \
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

**判定**: PASS �?双向收发正确

---

## TCP-02: tcp-client-connect + MCP NM Server 端到端收�?
| 项目 | �?|
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
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-client-connect \
       --ip <PC_IP> --port 9192 --connect-timeout 5
   ```
   验证 `Status=OK, handle=0x<CH>`, local IP 有效

3. **[MCP NM] 验证 Client 已连�?*:
   ```
   get_network_clients(connId="nm-tcp-srv")
   ```
   预期�?1 �?client

4. **[CLI] TCP_SEND 发送数�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-send \
       --handle 0x<CH> --data "Hello from HEX Client"
   ```
   验证 `Status=OK`

5. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-tcp-srv", display="string")
   ```
   预期包含 `"Hello from HEX Client"`

6. **[MCP NM] 发送回�?*:
   ```
   send_network_data(connId="nm-tcp-srv", data="Reply from NM", format="string")
   ```

7. **[Serial Monitor] 等待 TCP_RECV 事件** �?验证 `Data="Reply from NM"`

8. **清理**:
   - [CLI] `tcp-disconnect --handle 0x<CH> --method 0`

**判定**: PASS �?HEX-Bridge TCP Client 双向收发正确

---

## TCP-03: tcp-client-connect �?连接超时 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证连接无监听端口时返回超时错误 |
| **CLI 命令** | `tcp-client-connect --ip <IP> --port <无服务端�? --connect-timeout 2` |

**测试步骤**:

1. 执行命令 (连接到未监听端口):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-client-connect \
       --ip 127.0.0.1 --port 19999 --connect-timeout 2
   ```

2. 预期响应: `Status=ERR 0x42` (ERR_NET_TIMEOUT) �?`0x41` (ERR_NET_CONN_REFUSED)

**判定**: PASS �?返回超时/拒绝错误

---

## TCP-04: tcp-server-open �?端口已被占用 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证端口冲突时返回错�?|
| **CLI 命令** | `tcp-server-open --port <已占用端�?` |

**测试步骤**:

1. 创建第一�?TCP Server:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-open --port 9193
   ```
   预期 `Status=OK, handle=0x<SH>`

2. 创建第二�?TCP Server (相同端口):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-open --port 9193
   ```

3. 预期响应: `Status=ERR 0x45` (ERR_NET_PORT_IN_USE)

4. **清理**: `tcp-server-close --handle 0x<SH> --force 1`

**判定**: PASS �?端口冲突返回 ERR_NET_PORT_IN_USE

---

## TCP-05: tcp-server-open �?自动分配端口

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 Port=0 时系统自动分配有效端�?|
| **CLI 命令** | `tcp-server-open --port 0` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-open --port 0
   ```

2. 验证响应: `Status=OK, handle=0x<SH>, port=<非零�?`

3. **清理**: `tcp-server-close --handle 0x<SH> --force 1`

**判定**: PASS �?自动分配非零端口

---

## TCP-06: tcp-accept �?手动接受模式

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证手动接受模式�?Host 确认后连接才建立 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 TCP Server (手动接受模式)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-open \
       --port 9194 --accept-mode 0
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 尝试连接**:
   ```
   connect_network: connId="nm-manual", protocol="tcp", role="client", host="<HEX_IP>", port=9194
   ```

3. **[Serial Monitor] 等待 TCP_ACCEPT 事件** �?记录 `ClientHandle=0x<CH>`

4. 延迟 3 秒不确认 �?MCP NM Client 处于等待状�?
5. **[CLI] 发送接受确�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-accept \
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

**判定**: PASS �?确认后连接建�?
---

## TCP-07: tcp-accept �?手动拒绝

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证手动拒绝后客户端被断开 |
| **CLI 命令** | `tcp-accept --handle <CH> --decision 1` |

**测试步骤**:

1. 创建 TCP Server (手动接受模式, port=9195)
2. MCP NM Client 尝试连接 �?收到 TCP_ACCEPT 事件 `handle=0x<CH>`
3. **[CLI] 拒绝连接**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-accept \
       --handle 0x<CH> --decision 1
   ```
4. [MCP NM] 确认 Client 被拒�?(disconnected)

**判定**: PASS �?Client 被拒�?
---

## TCP-08: tcp-disconnect �?优雅关闭与强�?RST

| 项目 | �?|
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
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-client-connect \
       --ip <PC_IP> --port 9196
   ```
   记录 `handle=0x<CH>`

3. 测试优雅关闭:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-disconnect \
       --handle 0x<CH> --method 0
   ```
   验证 `Status=OK`, [MCP NM] 确认 Client 收到 FIN 后断开

4. 重新连接 (得到新的 `handle=0x<CH2>`), 测试强制 RST:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-disconnect \
       --handle 0x<CH2> --method 1
   ```
   验证 `Status=OK`, [MCP NM] 确认 Client �?RST

5. **清理**: [MCP NM] `disconnect_network(connId="nm-disc-srv")`

**判定**: PASS �?优雅关闭和强�?RST 均正�?
---

## TCP-09: tcp-send + MCP NM 大数据量测试

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 1024 字节 TCP 发送无丢包 |
| **CLI 命令** | `tcp-send --handle <CH> --hex-data <1024 字节 hex>` |

**前置**: 已建�?TCP 连接 (Server �?Client)

**测试步骤**:

1. 建立连接 (参�?TCP-01 �?TCP-02)

2. 构�?256 字节递增 hex 数据 `00 01 02 ... FF` (重复 4 �?= 1024 字节)

3. **[CLI] 发�?1024 字节**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-send \
       --handle 0x<CH> --hex-data "<1024字节hex字符�?"
   ```
   验证 `Status=OK, sent=1024 bytes`

4. **[MCP NM] 验证数据完整�?*:
   ```
   read_network_buffer(port="<connId>", display="hex")
   ```
   验证收到 1024 字节, 序列连续无断�?
5. **[MCP NM] 发�?1024 字节回包**
6. **[Serial Monitor] 等待 TCP_RECV**, 验证完整

**判定**: PASS �?1024 字节无丢�?
---

## TCP-10: tcp-send �?广播句柄 (0x8000)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证广播句柄发送到所有已连接客户�?|
| **CLI 命令** | `tcp-send --handle 0x8000 --data "BROADCAST"` |

**测试步骤**:

1. **[CLI] 创建 TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-open \
       --port 9197 --maxconn 3 --accept-mode 1
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 创建 2 �?TCP Client**:
   ```
   connect_network: connId="nm-bc-A", protocol="tcp", role="client", host="<HEX_IP>", port=9197
   connect_network: connId="nm-bc-B", protocol="tcp", role="client", host="<HEX_IP>", port=9197
   ```

3. [Serial Monitor] 等待 2 �?TCP_ACCEPT 事件

4. **[CLI] 广播发�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-send \
       --handle 0x8000 --data "BROADCAST MSG"
   ```

5. **[MCP NM] 验证两个 Client 都收�?*:
   ```
   read_network_buffer(port="nm-bc-A", display="string")
   read_network_buffer(port="nm-bc-B", display="string")
   ```
   均包�?`"BROADCAST MSG"`

6. **清理**

**判定**: PASS �?两个客户端均收到广播

---

## TCP-11: tcp-list-clients + tcp-kick-client 端到�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证客户端列表查询和踢出功能 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-open \
       --port 9198 --maxconn 3 --accept-mode 1
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 创建 2 �?TCP Client 连接**:
   ```
   connect_network: connId="nm-lc-A", protocol="tcp", role="client", host="<HEX_IP>", port=9198
   connect_network: connId="nm-lc-B", protocol="tcp", role="client", host="<HEX_IP>", port=9198
   ```

3. [Serial Monitor] 等待 2 �?TCP_ACCEPT �?记录 `0x<CH_A>`, `0x<CH_B>`

4. **[CLI] 查询客户端列�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 2`, 包含 `0x<CH_A>` �?`0x<CH_B>`

5. **[CLI] 踢出 CH_A**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-kick-client \
       --handle 0x<CH_A> --force 1
   ```
   验证 `Status=OK`

6. [Serial Monitor] 等待 TCP_DISCONNECT_EVENT(0x<CH_A>)

7. **[CLI] 再次查询**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 1`, 仅包�?`0x<CH_B>`

8. [MCP NM] 确认 nm-lc-B 仍可正常收发

9. **清理**

**判定**: PASS �?KICK 后目标断开, 其他客户端不受影�?
---

## TCP-12: tcp-list-clients �?�?Server 查询

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证无客户端时返�?ClientCount=0 |
| **CLI 命令** | `tcp-list-clients --handle <SH>` |

**测试步骤**:

1. 创建 TCP Server (port=9199, accept-mode=1), 不连接任何客户端
2. 执行查询:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-list-clients \
       --handle 0x<SH>
   ```
3. 验证 `Clients: 0`

**判定**: PASS �?�?Server 返回 Clients: 0

---

## TCP-13: tcp-conn-status �?查询单连接状�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证连接状态和收发统计正确 |
| **CLI 命令** | `tcp-conn-status --handle <CH>` |

**测试步骤**:

1. 建立 TCP 连接 (参�?TCP-01 �?TCP-02)

2. **[CLI] 发送数据后查询状�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-conn-status \
       --handle 0x<CH>
   ```

3. 验证响应:
   - `State=ESTABLISHED`
   - `Tx` 为非�?(已发送数�?
   - `Remote` 为对�?IP:Port
   - `LocalPort` 正确
   - `Uptime` 有效

4. **清理**

**判定**: PASS �?状态和统计正确

---

## TCP-14: tcp-conn-status �?无效句柄 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证无效句柄返回错误 |
| **CLI 命令** | `tcp-conn-status --handle 0xFFFF` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-conn-status \
       --handle 0xFFFF
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID) 或无响应超时

**判定**: PASS �?返回错误

---

## TCP-15: tcp-send �?无效句柄 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证向无效句柄发送数据返回错�?|
| **CLI 命令** | `tcp-send --handle 0x1234 --data "test"` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-send \
       --handle 0x1234 --data "test"
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS �?返回 ERR_NET_HANDLE_INVALID

---

## TCP-16: tcp-server-close �?优雅关闭与强制关�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 优雅关闭 (等待子连�? 和强制关�?两种方式 |
| **CLI 命令** | `tcp-server-close --handle <SH> --force 0/1` |

**测试步骤**:

1. 创建 TCP Server (port=9201), MCP NM Client 连接
2. **[CLI] 优雅关闭** (--force 0):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-close \
       --handle 0x<SH> --force 0
   ```
   验证 `Status=OK`, [Serial Monitor] 收到 TCP_DISCONNECT_EVENT

3. 重新创建 TCP Server (port=9202), Client 连接
4. **[CLI] 强制关闭** (--force 1):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-server-close \
       --handle 0x<SH2> --force 1
   ```
   验证 `Status=OK`

**判定**: PASS �?两种关闭方式均正�?
---

## TCP-17: tcp-close �?通用关闭

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 tcp-close 4 字节载荷 (Handle + HandleType + ForceFlag) 关闭连接�?Server，并上报 DISCONNECT_EVENT |
| **CLI 命令** | `tcp-close --handle <H> --handle-type 0/1 --force 0/1` |

**测试步骤**:

1. 创建 TCP Server (port=9203), MCP NM Client 连接 �?ClientHandle=0x<CH>
2. **[CLI] 关闭连接 (handle-type=0, force=0)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-close \
       --handle 0x<CH> --handle-type 0 --force 0
   ```
   验证 `Status=OK`, [Serial Monitor] 收到 TCP_DISCONNECT_EVENT(Reason=0x00)

3. **[CLI] 关闭 Server (handle-type=1, force=1)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 tcp-close \
       --handle 0x<SH> --handle-type 1 --force 1
   ```
   验证 `Status=OK`, [Serial Monitor] 收到 TCP_DISCONNECT_EVENT(Reason=0x01)

**判定**: PASS �?两种类型均正�? 断开事件已上�?
---

## TCP-18: TCP Server 完整生命周期 (集成)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 TCP Server 创建→接受→收发→断开→关闭完整流�?|
| **顺序命令�?* | `0x50` �?`0x56`(event) �?`0x54` �?`0x59` �?`0x5B` �?`0x5A` �?`0x51` |

**测试步骤**:

1. **SERVER_OPEN**: `tcp-server-open --port 0 --accept-mode 1` �?SH
2. **MCP NM 连接** �?Serial Monitor 收到 TCP_ACCEPT �?CH
3. **SEND**: `tcp-send --handle 0x<CH> --data "Hello"`
4. **LIST**: `tcp-list-clients --handle 0x<SH>` �?Clients: 1
5. **STATUS**: `tcp-conn-status --handle 0x<CH>` �?ESTABLISHED
6. **MCP NM 发回数据** �?Serial Monitor 收到 TCP_RECV
7. **KICK**: `tcp-kick-client --handle 0x<CH> --force 1` �?DISCONNECT_EVENT
8. **SERVER_CLOSE**: `tcp-server-close --handle 0x<SH> --force 1`

**预期**: 全部 8 步依次成�?
**判定**: PASS �?完整生命周期正确

---

# 第三部分：UDP 模块 (UDP, 0x60-0x6F)

---

## UDP-01: udp-server-open + udp-server-send 端到�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 HEX-Bridge UDP Server �?MCP NM UDP Client 双向收发 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 UDP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-open \
       --port 9201
   ```
   验证 `Status=OK, handle=0x<SH>, port=9201`

2. **[MCP NM] 创建 UDP Client**:
   ```
   connect_network: connId="nm-udp-cli", protocol="udp", role="client", host="<HEX_IP>", port=9201
   ```

3. **[MCP NM] 发�?UDP 数据**:
   ```
   send_network_data(connId="nm-udp-cli", data="UDP HELLO", format="string")
   ```

4. **[Serial Monitor] 等待 UDP_RECV 事件** �?验证 `Data="UDP HELLO"`, �?IP/Port 正确

5. **[CLI] UDP_SERVER_SEND 回复** (使用 Serial Monitor 中记录的源端�?:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-send \
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

**判定**: PASS �?UDP 双向收发正确

---

## UDP-02: udp-client-create + udp-client-send 端到�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 HEX-Bridge UDP Client 生命周期 (Create �?Send �?Delete) |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[MCP NM] 创建 UDP Server**:
   ```
   connect_network: connId="nm-udp-srv", protocol="udp", role="server", listenPort=9202
   ```

2. **[CLI] 创建 UDP Client**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-create \
       --ip <PC_IP> --port 9202
   ```
   验证 `Status=OK, handle=0x<CH>, local_port=<实际端口>`

3. **[CLI] 使用默认地址发�?* (--addr-mode 0):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 0 --data "UDP FROM HEX"
   ```
   验证 `Status=OK, sent=13 bytes`

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-udp-srv", display="string")
   ```
   预期包含 `"UDP FROM HEX"`

5. **[MCP NM] 发送回�?* �?[Serial Monitor] 等待 UDP_RECV 事件

6. **[CLI] 删除 Client**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-delete \
       --handle 0x<CH>
   ```
   验证 `Status=OK`

7. **[CLI] 删除后再次发�?(验证句柄失效)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 0 --data "SHOULD FAIL"
   ```
   预期 `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

8. **清理**: [MCP NM] `disconnect_network(connId="nm-udp-srv")`

**判定**: PASS �?生命周期完整, 删除后句柄失�?
---

## UDP-03: udp-client-send �?使用指定地址覆盖

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 AddrMode=1 时使用指定地址而非默认地址 |
| **CLI 命令** | `udp-client-send --handle <CH> --addr-mode 1 --ip <IP> --port <PORT> --data <text>` |

**测试步骤**:

1. [MCP NM] 创建 2 �?UDP Server 监听:
   - `connId="nm-srv-A"`, listenPort=9203
   - `connId="nm-srv-B"`, listenPort=9204

2. **[CLI] 创建 UDP Client** (默认地址 �?Srv A):
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-create \
       --ip <PC_IP> --port 9203
   ```

3. **[CLI] 使用指定地址发送到 Srv B**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 1 --ip <PC_IP> --port 9204 --data "Override to B"
   ```

4. 验证:
   - `read_network_buffer(port="nm-srv-A")` �?�?"Override to B"
   - `read_network_buffer(port="nm-srv-B")` �?包含 "Override to B"

5. **[CLI] 使用默认地址发�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-send \
       --handle 0x<CH> --addr-mode 0 --data "Default to A"
   ```

6. 验证:
   - `read_network_buffer(port="nm-srv-A")` �?包含 "Default to A"
   - `read_network_buffer(port="nm-srv-B")` �?�?"Default to A"

7. **清理**

**判定**: PASS �?地址覆盖和默认地址均正�?
---

## UDP-04: udp-server-open �?广播模式

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 UDP 广播发送到 255.255.255.255 |
| **CLI 命令** | `udp-server-open --port <PORT> --broadcast` |

**测试步骤**:

1. **[CLI] 创建启用广播�?UDP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-open \
       --port 9205 --broadcast
   ```

2. **[MCP NM] 创建 UDP Server 监听**:
   ```
   connect_network: connId="nm-bc-udp", protocol="udp", role="server", listenPort=9205
   ```

3. **[CLI] 广播发�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-send \
       --handle 0x<SH> --ip 255.255.255.255 --port 9205 --data "BROADCAST UDP"
   ```

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-bc-udp", display="string")
   ```
   预期包含 `"BROADCAST UDP"`

5. **清理**

**判定**: PASS �?广播数据到达

---

## UDP-05: udp-server-open �?多播模式

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 UDP 多播组加入和发�?|
| **CLI 命令** | `udp-server-open --port <PORT> --multicast <MULTICAST_IP>` |

**测试步骤**:

1. **[CLI] 创建启用多播�?UDP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-open \
       --port 9206 --multicast 224.0.0.1
   ```

2. **[MCP NM] 创建加入多播组的 UDP Server**:
   ```
   connect_network: connId="nm-mc-udp", protocol="udp", role="server", listenPort=9206, multicastAddress="224.0.0.1"
   ```

3. **[CLI] 发送到多播�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-send \
       --handle 0x<SH> --ip 224.0.0.1 --port 9206 --data "MULTICAST UDP"
   ```

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-mc-udp", display="string")
   ```
   预期包含 `"MULTICAST UDP"`

5. **清理**

**判定**: PASS �?多播数据到达

---

## UDP-06: udp-server-send �?无效句柄 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证无效 ServerHandle 返回错误 |
| **CLI 命令** | `udp-server-send --handle 0x0000 --ip <IP> --port <PORT> --data "test"` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-send \
       --handle 0x0000 --ip 192.168.1.1 --port 9999 --data "test"
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS �?返回 ERR_NET_HANDLE_INVALID

---

## UDP-07: udp-server-close + udp-client-delete �?无效句柄 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证无效句柄关闭/删除返回错误 |
| **CLI 命令** | `udp-server-close --handle 0x0000` / `udp-client-delete --handle 0x0000` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-server-close \
       --handle 0x0000
   ```
   预期 `Status=ERR 0x43`

2. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 udp-client-delete \
       --handle 0x0000
   ```
   预期 `Status=ERR 0x43`

**判定**: PASS �?均返�?ERR_NET_HANDLE_INVALID

---

# 第四部分：WebSocket 模块 (WS, 0x70-0x7F)

---

## WS-01: ws-server-open + MCP NM WS Client Text 收发

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 HEX-Bridge WS Server 握手 + Text 收发 + Close �?|
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 WS Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-server-open \
       --port 9201 --maxconn 3 --path /test
   ```
   验证 `Status=OK, handle=0x<SH>, port=9201`

2. **[MCP NM] WebSocket Client 连接**:
   ```
   connect_network: connId="nm-ws-cli", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9201/test"
   ```

3. **[Serial Monitor] 等待 WS_ACCEPT 事件** �?记录 `ServerHandle=<SH>`, `ClientHandle=0x<CH>`, `Path="/test"`

4. **[MCP NM] 发�?WebSocket Text**:
   ```
   send_network_data(connId="nm-ws-cli", data="Hello WebSocket", format="string")
   ```

5. **[Serial Monitor] 等待 WS_RECV 事件** �?验证 `MsgType=0x01 (Text)`, `Data="Hello WebSocket"`

6. **[CLI] WS_SEND Text 回复**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
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
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-client-disconnect \
       --handle 0x<CH> --close-code 1000
   ```
   验证 `Status=OK`

9. [Serial Monitor] 等待 WS_DISCONNECT_EVENT

10. **清理**: `ws-server-close --handle 0x<SH> --force 1`

**判定**: PASS �?全部步骤通过

---

## WS-02: ws-client-connect + MCP NM WS Server 端到�?
| 项目 | �?|
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
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-client-connect \
       --ip <PC_IP> --port 9202 --path /echo
   ```
   验证 `Status=OK, handle=0x<CH>, result=1`

3. **[CLI] WS_SEND 发送数�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 1 --data "Hello from HEX WS Client"
   ```
   验证 `Status=OK`

4. **[MCP NM] 验证收到**:
   ```
   read_network_buffer(port="nm-ws-srv", display="string")
   ```
   预期包含 `"Hello from HEX WS Client"`

5. **[MCP NM] 发送回�?*:
   ```
   send_network_data(connId="nm-ws-srv", data="Echo from NM WS", format="string")
   ```

6. [Serial Monitor] 等待 WS_RECV �?验证 `Data="Echo from NM WS"`

7. **清理**:
   - [CLI] `ws-client-disconnect --handle 0x<CH> --close-code 1000`
   - [MCP NM] `disconnect_network(connId="nm-ws-srv")`

**判定**: PASS �?HEX-Bridge 成功作为 WS Client 工作

---

## WS-03: ws-send �?Binary 消息含特殊字�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 WebSocket Binary 帧含 UBCP 转义字符时不破损 |
| **CLI 命令** | `ws-send --handle <CH> --msg-type 2 --hex-data "00 FF 7E 7D 42"` |

**测试步骤**:

1. WS_SERVER_OPEN (port=9203, path="/bin")
2. MCP NM WS Client 连接 �?记录 CH
3. **[CLI] 发�?Binary 含特殊字�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 2 --hex-data "00 FF 7E 7D 42"
   ```
   验证 `Status=OK, sent=5 bytes`

4. **[MCP NM] 验证二进制完整�?*:
   ```
   read_network_buffer(port="nm-bin-cli", display="hex")
   ```
   预期收到 `00 FF 7E 7D 42`, 无截断无转义

5. **清理**

**判定**: PASS �?含特殊字节的 Binary 帧收发完�?
---

## WS-04: ws-send �?Ping / Pong 心跳

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 WS_SEND Ping/Pong 不影响连�?|
| **CLI 命令** | `ws-send --handle <CH> --msg-type 9/10 --data ""` |

**测试步骤**:

1. WS_SERVER_OPEN + MCP NM WS Client 连接 �?CH

2. **[CLI] 发�?Ping (msg-type=9)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 9
   ```
   验证 `Status=OK`

3. **[CLI] 发�?Ping �?Payload**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 9 --data "HEARTBEAT"
   ```
   验证 `Status=OK`

4. **[CLI] 发�?Pong (msg-type=10)**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 10
   ```
   验证 `Status=OK`

5. 链路仍处�?ESTABLISHED 状�? 继续发�?Text 验证连接正常

6. **清理**

**判定**: PASS �?Ping/Pong 不影响连�?
---

## WS-05: ws-send �?发�?Close �?(msg-type=8)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 WS_SEND Close 帧能正确关闭连接 |
| **CLI 命令** | `ws-send --handle <CH> --msg-type 8 --hex-data "03E8"` |

**测试步骤**:

1. WS_SERVER_OPEN + MCP NM WS Client 连接 �?CH

2. **[CLI] 发�?Close �?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
       --handle 0x<CH> --msg-type 8 --hex-data "03E8"
   ```
   验证 `Status=OK`

3. [Serial Monitor] 等待 WS_DISCONNECT_EVENT(CH, CloseCode=1000)

4. [MCP NM] 确认连接已断开

5. **清理**

**判定**: PASS �?Close 帧关闭连接正�?
---

## WS-06: ws-list-clients + ws-kick-client 端到�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 WS 客户端列表查询和踢出功能 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 创建 WS Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-server-open \
       --port 9204 --maxconn 3 --path /ws-test
   ```
   记录 `handle=0x<SH>`

2. **[MCP NM] 创建 2 �?WS Client**:
   ```
   connect_network: connId="nm-ws-A", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9204/ws-test"
   connect_network: connId="nm-ws-B", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9204/ws-test"
   ```

3. [Serial Monitor] 等待 2 �?WS_ACCEPT �?记录 `0x<CH_A>`, `0x<CH_B>`

4. **[CLI] 查询客户�?*:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 2`

5. **[CLI] 踢出 CH_A**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-kick-client \
       --handle 0x<CH_A> --force 1
   ```
   验证 `Status=OK`

6. [Serial Monitor] 等待 WS_DISCONNECT_EVENT(CH_A)

7. **[CLI] 再次查询**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-list-clients \
       --handle 0x<SH>
   ```
   验证 `Clients: 1`, 仅包�?CH_B

8. [MCP NM] nm-ws-B 仍可正常收发

9. **清理**

**判定**: PASS �?WS KICK 功能正常

---

## WS-07: ws-kick-client �?优雅关闭 (--force 0)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证优雅关闭发�?Close 帧后断开 |
| **CLI 命令** | `ws-kick-client --handle <CH> --force 0` |

**测试步骤**:

1. WS_SERVER_OPEN + MCP NM WS Client 连接 �?CH
2. **[CLI] 优雅关闭**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-kick-client \
       --handle 0x<CH> --force 0
   ```
3. [Serial Monitor] 等待 WS_DISCONNECT_EVENT(CH, Reason=0x00 正常关闭)
4. [MCP NM] 确认收到 Close �?(code=1000)

**判定**: PASS �?优雅关闭正确

---

## WS-08: ws-server-open �?不同路径 + 子协�?
| 项目 | �?|
|:---|:---|
| **测试目的** | 验证指定路径和子协议�?WS Server 创建 |
| **CLI 命令** | `ws-server-open --port <PORT> --path /specific --subproto "chat"` |

**测试步骤**:

1. **[CLI] 创建指定路径和子协议�?WS Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-server-open \
       --port 9205 --path /specific --subproto "chat"
   ```
   验证 `Status=OK`

2. **[MCP NM] WS Client 连接到正确路�?*:
   ```
   connect_network: connId="nm-ws-path", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9205/specific"
   ```

3. [Serial Monitor] 验证 WS_ACCEPT: `Path="/specific"`, `SubProtoIndex` 可能非零

4. **[MCP NM] 尝试错误路径** �?应被拒绝:
   ```
   connect_network: connId="nm-wrong", protocol="websocket", role="client",
                    url="ws://<HEX_IP>:9205/wrong"
   ```
   预期连接失败

5. **清理**

**判定**: PASS �?路径匹配正确, 错误路径被拒�?
---

## WS-09: ws-client-connect �?握手失败 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证连接�?WS Server 时返回握手错�?|
| **CLI 命令** | `ws-client-connect --ip <PC_IP> --port <TCP_PORT> --path /` |

**测试步骤**:

1. [MCP NM] 创建普�?TCP Server (�?WS):
   ```
   connect_network: connId="nm-tcp-not-ws", protocol="tcp", role="server", listenPort=9206
   ```

2. **[CLI] WS Client 连接�?TCP Server**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-client-connect \
       --ip <PC_IP> --port 9206 --path /
   ```
   预期: `Status=ERR 0x49` (ERR_NET_WS_HANDSHAKE)

3. **清理**: [MCP NM] `disconnect_network(connId="nm-tcp-not-ws")`

**判定**: PASS �?握手失败返回 ERR_NET_WS_HANDSHAKE

---

## WS-10: ws-send �?无效句柄 (错误用例)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证无效句柄返回错误 |
| **CLI 命令** | `ws-send --handle 0xFFFF --msg-type 1 --data "test"` |

**测试步骤**:

1. 执行命令:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 ws-send \
       --handle 0xFFFF --msg-type 1 --data "test"
   ```

2. 预期: `Status=ERR 0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS �?返回 ERR_NET_HANDLE_INVALID

---

## WS-11: WebSocket Server 完整生命周期 (集成)

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 WS Server Open �?Accept �?Text/Binary/Ping �?Disconnect �?Close 完整流程 |
| **命令序列** | `0x70` �?`0x76`(event) �?`0x74`(Text) �?`0x74`(Binary) �?`0x74`(Ping) �?`0x74`(Close) �?`0x71` |

**测试步骤**:

1. **SERVER_OPEN**: `ws-server-open --port 0 --path /lifecycle` �?SH
2. **MCP NM 连接** �?Serial Monitor 收到 WS_ACCEPT �?CH
3. **SEND Text**: `ws-send --handle 0x<CH> --msg-type 1 --data "Hi"` �?OK
4. **SEND Binary**: `ws-send --handle 0x<CH> --msg-type 2 --hex-data "CA FE"` �?OK
5. **SEND Ping**: `ws-send --handle 0x<CH> --msg-type 9` �?OK
6. **MCP NM 发数�?* �?Serial Monitor 收到 WS_RECV
7. **SEND Close**: `ws-send --handle 0x<CH> --msg-type 8 --hex-data "03E8"` �?WS_DISCONNECT_EVENT
8. **SERVER_CLOSE**: `ws-server-close --handle 0x<SH> --force 1` �?OK

**预期**: 全部 8 步依次成�?
**判定**: PASS �?完整生命周期正确

---

# 第五部分：集成测�?(INT)

---

## INT-01: TCP + UDP + WS 三协议并�?Server

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 TCP/UDP/WS Server 同时运行, 互不干扰 |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[CLI] 同时创建 3 �?Server**:
   ```bash
   # TCP Server
   tcp-server-open --port 9210 --maxconn 3 --accept-mode 1
   # UDP Server
   udp-server-open --port 9211
   # WS Server
   ws-server-open --port 9212 --maxconn 3 --path /srv
   ```
   记录 SH_TCP, SH_UDP, SH_WS

2. **[MCP NM] 同时连接 3 �?Server**:
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

5. **[MCP NM] 验证 3 个通道各自收到 2 条消�?*:
   ```
   read_network_buffer(port="int-tcp", display="string")
   read_network_buffer(port="int-udp", display="string")
   read_network_buffer(port="int-ws", display="string")
   ```

6. **[CLI] 关闭所�?Server**

**判定**: PASS �?3 协议并发, 无串�?
---

## INT-02: HEX-Bridge �?Client 并发连接 MCP NM Server

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 同时作为多个协议�?Client |
| **涉及工具** | CLI + MCP NM + Serial Monitor |

**测试步骤**:

1. **[MCP NM] 同时启动 3 �?Server**:
   ```
   connect_network: connId="mc-tcp-srv", protocol="tcp", role="server", listenPort=9213
   connect_network: connId="mc-udp-srv", protocol="udp", role="server", listenPort=9214
   connect_network: connId="mc-ws-srv", protocol="websocket", role="server", listenPort=9215, path="/echo"
   ```

2. **[CLI] 依次创建 3 �?Client**:
   ```bash
   tcp-client-connect --ip <PC_IP> --port 9213   �?CH_TCP
   udp-client-create --ip <PC_IP> --port 9214    �?CH_UDP
   ws-client-connect --ip <PC_IP> --port 9215 --path /echo  �?CH_WS
   ```
   全部 Status=OK

3. **[CLI] 同时发�?*:
   ```bash
   tcp-send --handle 0x<CH_TCP> --data "Multi-TCP"
   udp-client-send --handle 0x<CH_UDP> --addr-mode 0 --data "Multi-UDP"
   ws-send --handle 0x<CH_WS> --msg-type 1 --data "Multi-WS"
   ```

4. **[MCP NM] 验证**:
   ```
   read_network_buffer(port="mc-tcp-srv")  �?"Multi-TCP"
   read_network_buffer(port="mc-udp-srv")  �?"Multi-UDP"
   read_network_buffer(port="mc-ws-srv")   �?"Multi-WS"
   ```

5. **清理**

**判定**: PASS �?�?Client 并发正常

---

## INT-03: net-list-conns �?多类型连接全局概览

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 NET_LIST_CONNS 一站式汇总所有连�?|
| **CLI 命令** | `net-list-conns` |

**测试步骤**:

1. **[CLI] 创建混合连接**:
   ```bash
   tcp-server-open --port 9216 --accept-mode 1   �?SH_TCP
   udp-client-create --ip <PC_IP> --port 9217     �?CH_UDP
   ```

2. **[MCP NM] 创建对端**:
   ```
   connect_network: connId="gc-tcp-cli", protocol="tcp", role="client", host="<HEX_IP>", port=9216
   connect_network: connId="gc-udp-srv", protocol="udp", role="server", listenPort=9217
   ```

3. [Serial Monitor] 等待 TCP_ACCEPT

4. **[CLI] 全局查询**:
   ```bash
   python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600 net-list-conns
   ```

5. 验证响应:
   - `Status=OK`
   - `Connections >= 3`
   - 包含 `[TCP_SERVER]` 条目 (handle=SH_TCP)
   - 包含 `[TCP_CONN]` 条目 (parent=SH_TCP)
   - 包含 `[UDP_CLIENT]` 条目 (handle=CH_UDP)

6. **清理**

**判定**: PASS �?NET_LIST_CONNS 正确汇�?
---

## INT-04: TCP + WS 多客户端列表并行查询

| 项目 | �?|
|:---|:---|
| **测试目的** | 验证 TCP �?WS �?LIST_CLIENTS 在客户端列表上各自独�?|
| **CLI 命令** | `tcp-list-clients`, `ws-list-clients` |

**测试步骤**:

1. **[CLI] 同时创建 TCP Server �?WS Server**:
   ```bash
   tcp-server-open --port 9220 --accept-mode 1   �?SH_TCP
   ws-server-open --port 9221 --path /list         �?SH_WS
   ```

2. **[MCP NM] 各创�?1 �?Client**:
   ```
   # TCP
   connect_network: connId="lp-tcp", protocol="tcp", role="client", host="<HEX_IP>", port=9220
   # WS
   connect_network: connId="lp-ws", protocol="websocket", role="client", url="ws://<HEX_IP>:9221/list"
   ```

3. 等待 TCP_ACCEPT + WS_ACCEPT

4. **[CLI] 并行查询**:
   ```bash
   tcp-list-clients --handle 0x<SH_TCP>   �?Clients: 1 (TCP)
   ws-list-clients --handle 0x<SH_WS>    �?Clients: 1 (WS)
   ```

5. **[CLI] 并行踢出**:
   ```bash
   tcp-kick-client --handle 0x<CH_TCP> --force 1
   ws-kick-client --handle 0x<CH_WS> --force 1
   ```

6. 等待 TCP_DISCONNECT_EVENT + WS_DISCONNECT_EVENT

7. **[CLI] 再次查询**:
   ```bash
   tcp-list-clients --handle 0x<SH_TCP>   �?Clients: 0
   ws-list-clients --handle 0x<SH_WS>    �?Clients: 0
   ```

8. **清理**

**判定**: PASS �?TCP �?WS 客户端列表各自独�?
---

# 第六部分：错误码覆盖矩阵

| 错误�?| 名称 | 覆盖用例 |
|:---|:---|:---|
| `0x00` | SUCCESS | 所有正常流程用�?|
| `0x02` | ERR_PARAM | NET-07 (无效 InterfaceIndex) |
| `0x06` | ERR_NOT_SUPPORT | 保留命令�?|
| `0x0A` | ERR_CHANNEL_INVALID | NET-07 |
| `0x41` | ERR_NET_CONN_REFUSED | TCP-03 (连接拒绝) |
| `0x42` | ERR_NET_TIMEOUT | TCP-03 (连接超时) |
| `0x43` | ERR_NET_HANDLE_INVALID | TCP-14/15, UDP-06/07, WS-10 |
| `0x45` | ERR_NET_PORT_IN_USE | TCP-04 |
| `0x46` | ERR_NET_DNS_FAIL | NET-04 |
| `0x47` | ERR_NET_NO_IP | NET-09 (�?DNS 解析在无 IP 时返回；Server Open/Client Create 使用 bind(INADDR_ANY) 不依�?IP) |
| `0x48` | ERR_NET_MAX_CONN | 创建超过最大连接数 |
| `0x49` | ERR_NET_WS_HANDSHAKE | WS-09 |

---

## 用例索引

| 分组 | 用例编号 | 数量 | 说明 |
|:---|:---|:---|:---|
| 网络配置 | NET-01 ~ NET-09 | 9 | STATUS, DNS, CONFIG (DHCP/静态IP), 错误路径, LIST_CONNS |
| TCP | TCP-01 ~ TCP-18 | 18 | Server/Client 端到端收�? 手动接受/拒绝, 优雅/强制关闭, 广播, 大数据量, LIST/KICK/STATUS, 完整生命周期, 错误用例 |
| UDP | UDP-01 ~ UDP-07 | 7 | Server/Client 端到端收�? 地址覆盖, 广播, 多播, 生命周期, 错误用例 |
| WebSocket | WS-01 ~ WS-11 | 11 | Server/Client 端到�? Text/Binary/Ping/Pong/Close, LIST/KICK, 路径匹配, 优雅关闭, 完整生命周期, 错误用例 |
| 集成测试 | INT-01 ~ INT-04 | 4 | 三协议并�?Server, �?Client 并发, 全局概览, 并行 LIST/KICK |
| **合计** | | **49** | |

---

## 测试执行脚本参�?
```bash
# CLI 基础前缀
CLI="python script/cli/hex-bridge-network-cli.py --port COM4 --baud 921600"

# 获取 HEX-Bridge IP
$CLI net-status
# 记录 IpAddr 处的 IP 地址

# 获取 PC 本机 IP (PowerShell)
ipconfig
# 记录 IPv4 地址

# 端到端测试示�?(TCP Server)
$CLI tcp-server-open --port 9191 --maxconn 3 --accept-mode 1
# �?记录 ServerHandle (SH)

# �?Kilo Agent �? MCP NM 创建 TCP Client
# connect_network: connId="test-cli", protocol="tcp", role="client", host="<HEX_IP>", port=9191

# 发送数�?$CLI tcp-send --handle 0x<CH> --data "Hello World"

# �?Kilo Agent �? MCP NM 验证接收
# read_network_buffer(port="test-cli", display="string")

# 清理
$CLI tcp-server-close --handle 0x<SH> --force 1
```
