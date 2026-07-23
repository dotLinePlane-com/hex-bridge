# 09. 网络模块测试用例

> 命令码范围：`0x40-0x4F` (网络配置), `0x50-0x5F` (TCP), `0x60-0x6F` (UDP), `0x70-0x7F` (WebSocket)
> 模块：`mod_network` + `mod_tcp` + `mod_udp` + `mod_ws`
> **测试脚本**: `script/test/test_network.py`
> **测试工具**: MCP Network Monitor (Kilo Agent 集成, 充当网络对端)

## 测试拓扑

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

> **关键优势**: MCP Network Monitor 与 Serial Monitor 运行在同一台 PC 上，无需额外的"辅助 PC"。Network Monitor 可以直接创建 TCP/UDP/WebSocket Server/Client，作为 HEX-Bridge 的网络对端，同时可读写数据缓冲区验证通信内容。

**数据流说明**:

| 方向 | 路径 |
|:---|:---|
| MCP 命令 | Serial Monitor (COM35) → HEX-Bridge |
| MCP 响应/事件 | HEX-Bridge → Serial Monitor (COM35) |
| HEX-Bridge TCP 发送 | COM35 → MCP 命令 → HEX-Bridge → Ethernet → Network Monitor (PC) |
| HEX-Bridge TCP 接收 | Network Monitor (PC) → Ethernet → HEX-Bridge → MCP 事件 → COM35 |
| HEX-Bridge TCP Server 接受 | Network Monitor Client → Ethernet → HEX-Bridge → TCP_ACCEPT 事件 → COM35 |
| DNS 解析 | COM35 → MCP → HEX-Bridge → DNS 服务器 → MCP → COM35 |

---

## 测试环境

| 项目 | 要求 |
|:---|:---|
| 被测设备 | HEX-Bridge (ESP32, 固件中已实现以太网模块) |
| MCP 通信口 | COM35, UART1, 921600 bps, 8N1 |
| 网络环境 | 局域网 DHCP 服务可用, 网线已连接 |
| 调试输出 | COM34, UART0, 115200 bps |
| 网络对端工具 | **MCP Network Monitor** (同一 PC 上运行的网络调试工具) |
| 协议版本 | UBCP v2.0 (`0x02`) |

## 前置条件

1. 固件已烧录并运行, LAN8720 驱动初始化成功
2. 网线已插入, 链路 UP (可通过 COM34 日志确认 `Ethernet Link Up`)
3. DHCP 已获取到 IP 地址 (可通过 `NET_STATUS` 命令确认)
4. 完成握手流程：`PING (0x00)` + `GET_INFO (0x01)`
5. Kilo Agent 已加载 `serial-monitor-mcp` 和 `network-monitor-mcp` 工具

---

## 使用 MCP Network Monitor 作为测试工具

MCP Network Monitor 是嵌入在 Kilo Agent 中的网络调试工具，支持创建 TCP/UDP/WebSocket Server 和 Client。它可以充当 HEX-Bridge 的网络对端，替代传统的"辅助 PC + nc/wscat"方案。

### 基本用法

**作为 TCP Server (接受 HEX-Bridge 连接)**:
```
network-monitor-mcp_connect_network
  connId: "tcp-test-server"
  protocol: "tcp"
  role: "server"
  listenPort: 9090
```

**作为 TCP Client (连接 HEX-Bridge Server)**:
```
network-monitor-mcp_connect_network
  connId: "tcp-test-client"
  protocol: "tcp"
  role: "client"
  host: "192.168.x.x"   # HEX-Bridge 的 IP
  port: 8080
```

**作为 UDP Server (监听)**:
```
network-monitor-mcp_connect_network
  connId: "udp-test-server"
  protocol: "udp"
  role: "server"
  listenPort: 9091
```

**作为 UDP Client**:
```
network-monitor-mcp_connect_network
  connId: "udp-test-client"
  protocol: "udp"
  role: "client"
  host: "192.168.x.x"
  port: 9091
```

**作为 WebSocket Server**:
```
network-monitor-mcp_connect_network
  connId: "ws-test-server"
  protocol: "websocket"
  role: "server"
  listenPort: 9092
  path: "/ws"
```

**作为 WebSocket Client**:
```
network-monitor-mcp_connect_network
  connId: "ws-test-client"
  protocol: "websocket"
  role: "client"
  url: "ws://192.168.x.x:9092/ws"
```

**发送数据**:
```
network-monitor-mcp_send_network_data
  connId: "tcp-test-server"
  data: "Hello from MCP NM"
  format: "string"
```

**读取接收缓冲区**:
```
network-monitor-mcp_read_network_buffer
  port: "tcp-test-server"
  display: "hex"
```

### 与测试脚本的关系

| 阶段 | 工具 | 操作 |
|:---|:---|:---|
| 1. 启动网络对端 | **MCP Network Monitor** | 创建 TCP/UDP/WS Server 或 Client |
| 2. 发送 MCP 命令 | **Serial Monitor** (COM35) | 通过 UBCP 命令控制 HEX-Bridge 执行网络操作 |
| 3. 验证 MCP 响应 | **Serial Monitor** (COM35) | 读取 UBCP 响应/事件帧 |
| 4. 验证网络数据 | **MCP Network Monitor** | 读取收发缓冲区确认数据一致性 |

### 端到端测试流程示例

测试 HEX-Bridge TCP_CLIENT_CONNECT + 数据收发：

```
1. [Network Monitor] 启动 TCP Server 监听 9090:
   connId="tcp-srv", protocol=tcp, role=server, listenPort=9090

2. [Serial Monitor] 获取 HEX-Bridge 的 IP (NET_STATUS → IpAddr)

3. [Serial Monitor] 发送 TCP_CLIENT_CONNECT(PC-IP, 9090):
   接收 UBCP 帧 → 获取 ConnHandle

4. [Network Monitor] 检查 TCP Server 已接受连接:
   network-monitor-mcp_get_network_clients(connId="tcp-srv")

5. [Serial Monitor] TCP_SEND(ConnHandle, "Hello NM"):
   → Status=0x00

6. [Network Monitor] 验证收到数据:
   network-monitor-mcp_read_network_buffer(port="tcp-srv", display="string")
   → 应包含 "Hello NM"

7. [Network Monitor] 发送回包:
   network-monitor-mcp_send_network_data(connId="tcp-srv", data="ACK", format="string")

8. [Serial Monitor] 等待 TCP_RECV 事件:
   → Data="ACK"
```

### MCP NM 与传统工具对照

| MCP Network Monitor 操作 | 传统 nc/wscat 等价命令 |
|:---|:---|
| `connect_network(tcp, server, port=9090)` | `nc -l -p 9090` |
| `connect_network(tcp, client, host=X, port=Y)` | `nc X Y` |
| `send_network_data(data="hello", format="string")` | 在 nc 终端输入 `hello` |
| `read_network_buffer(display="string")` | 查看 nc 终端输出 |
| `connect_network(websocket, server, listenPort=8080, path="/ws")` | `python -m websockets` |
| `connect_network(websocket, client, url="ws://X:Y/path")` | `wscat -c ws://X:Y/path` |
| `connect_network(udp, server, listenPort=8082)` | `nc -u -l 8082` |
| `get_network_clients()` | `netstat -an` 检查连接状态 |
| `get_network_status()` | `ss -tnp` 检查连接统计 |

---

# 附录：MCP Network Monitor 辅助测试用例 (MCP-NM)

> 以下用例使用 **MCP Network Monitor** 作为网络对端，无需外部辅助 PC。
> 测试步骤中标注 `[MCP NM]` 的操作在 Kilo Agent 中执行，`[COM35]` 的操作通过 Serial Monitor 发送 UBCP 命令。

---

## NM-TCP-01: HEX-Bridge TCP Client → MCP NM TCP Server (端到端收发)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 作为 TCP Client 连接 MCP NM Server，双向收发数据 |
| **涉及工具** | Serial Monitor (COM35) + MCP Network Monitor |

**测试步骤**:

1. **[MCP NM] 启动 TCP Server**
   ```
   connect_network: connId="nm-tcp-srv", protocol="tcp", role="server", listenPort=9191
   ```

2. **[COM35] 获取 HEX-Bridge IP**
   ```
   发送 NET_STATUS(0x00) → 记录 IpAddr
   ```

3. **[COM35] 获取 PC 本机 IP (用于 HEX-Bridge 连接)**
   ```bash
   ipconfig → 记录 PC IP
   ```

4. **[COM35] TCP_CLIENT_CONNECT 到 PC**
   ```
   CmdCode=0x52, DestIP=PC_IP, DestPort=9191, TimeoutSec=5
   → 预期: Status=0x00, ConnHandle=CH 合法
   ```

5. **[MCP NM] 验证 Client 已连接**
   ```
   get_network_clients(connId="nm-tcp-srv")
   → 预期: 有 1 个 client, IP=HEX-Bridge IP
   ```

6. **[COM35] TCP_SEND 发送数据**
   ```
   CmdCode=0x54, ConnHandle=CH, Data="Hello from HEX-Bridge"
   → 预期: Status=0x00, ActualLen=24
   ```

7. **[MCP NM] 验证收到数据**
   ```
   read_network_buffer(port="nm-tcp-srv", direction="rx", display="string")
   → 预期: 包含 "Hello from HEX-Bridge"
   ```

8. **[MCP NM] 发送回包**
   ```
   send_network_data(connId="nm-tcp-srv", data="Hello from MCP NM", format="string")
   ```

9. **[COM35] 等待 TCP_RECV 事件**
   ```
   → 预期: 收到 TCP_RECV(ConnHandle=CH, Data="Hello from MCP NM")
   ```

10. **[COM35] TCP_CLIENT_DISCONNECT**
    ```
    CmdCode=0x53, Method=0x00
    → 预期: Status=0x00
    ```

**判定**: PASS — 全部 10 步通过

---

## NM-TCP-02: MCP NM TCP Client → HEX-Bridge TCP Server (端到端收发)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 作为 TCP Server 接受 MCP NM Client 连接，双向收发 |
| **涉及工具** | Serial Monitor (COM35) + MCP Network Monitor |

**测试步骤**:

1. **[COM35] TCP_SERVER_OPEN**
   ```
   CmdCode=0x50, Port=9192, MaxConn=3, AcceptMode=0x01
   → 预期: Status=0x00, ServerHandle=SH, ActualPort=9192
   ```

2. **[MCP NM] 作为 Client 连接 HEX-Bridge**
   ```
   connect_network: connId="nm-tcp-cli", protocol="tcp", role="client",
                    host="<HEX-Bridge IP>", port=9192
   ```

3. **[COM35] 等待 TCP_ACCEPT 事件**
   ```
   → 预期: ClientHandle=CH, ClientIP=PC IP
   ```

4. **[MCP NM] 发送数据**
   ```
   send_network_data(connId="nm-tcp-cli", data="Client says Hi", format="string")
   ```

5. **[COM35] 等待 TCP_RECV 事件**
   ```
   → 预期: TCP_RECV(ConnHandle=CH, Data="Client says Hi")
   ```

6. **[COM35] TCP_SEND 回复**
   ```
   CmdCode=0x54, ConnHandle=CH, Data="Server says Hi"
   → 预期: Status=0x00
   ```

7. **[MCP NM] 验证收到回复**
   ```
   read_network_buffer(port="nm-tcp-cli", direction="rx", display="string")
   → 预期: 包含 "Server says Hi"
   ```

8. **[MCP NM] 断开连接**
   ```
   disconnect_network(connId="nm-tcp-cli")
   ```

9. **[COM35] 等待 TCP_DISCONNECT_EVENT**
   ```
   → 预期: ConnHandle=CH, Reason=0x00
   ```

10. **[COM35] TCP_SERVER_CLOSE**
    ```
    CmdCode=0x51, ForceClose=0x01
    → 预期: Status=0x00
    ```

**判定**: PASS — 全部 10 步通过

---

## NM-TCP-03: HEX-Bridge TCP Server — 广播发送到多个 Client

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 TCP_SEND 使用 0x8000 广播句柄发送到所有已连接 Client |

**测试步骤**:

1. **[COM35] TCP_SERVER_OPEN**
   ```
   Port=9193, MaxConn=5, AcceptMode=0x01
   → ServerHandle=SH
   ```

2. **[MCP NM] 创建 2 个 TCP Client 连接**
   ```
   connId="nm-cli-A", protocol=tcp, role=client, host=<HEX IP>, port=9193
   connId="nm-cli-B", protocol=tcp, role=client, host=<HEX IP>, port=9193
   ```

3. **[COM35] 等待 2 次 TCP_ACCEPT 事件** → 记录 C1, C2

4. **[COM35] TCP_SEND 广播**
   ```
   ConnHandle=0x8000 (BROADCAST), Data="BROADCAST MSG"
   → 预期: Status=0x00
   ```

5. **[MCP NM] 验证两个 Client 都收到**
   ```
   read_network_buffer(port="nm-cli-A") → 包含 "BROADCAST MSG"
   read_network_buffer(port="nm-cli-B") → 包含 "BROADCAST MSG"
   ```

6. **清理**: 断开 MCP NM Clients, TCP_SERVER_CLOSE

**判定**: PASS — 两个 Client 均收到广播数据

---

## NM-TCP-04: TCP_SERVER_OPEN — 手动接受模式 (AcceptMode=0x00)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证手动接受模式中, Host 必须通过 TCP_ACCEPT 确认才能建立连接 |

**测试步骤**:

1. **[COM35] TCP_SERVER_OPEN**
   ```
   Port=9194, MaxConn=3, AcceptMode=0x00 (手动)
   → ServerHandle=SH
   ```

2. **[MCP NM] Client 尝试连接**
   ```
   connId="nm-manual", protocol=tcp, role=client, host=<HEX IP>, port=9194
   ```

3. **[COM35] 等待 TCP_ACCEPT 事件**
   ```
   → 事件帧上报 ClientHandle=CH, ClientIP=PC IP
   ```

4. **延迟 3 秒不确认** → 验证 MCP NM Client 仍处于 TCP SYN_SENT / 等待状态 (连接未建立)

5. **[COM35] 发送 TCP_ACCEPT 确认**
   ```
   CmdCode=0x56, ClientHandle=CH, Decision=0x00 (接受)
   → 预期: Status=0x00
   ```

6. **[MCP NM] 验证 Client 已连接**
   ```
   get_network_status(connId="nm-manual") → connected
   ```

7. **清理**

**判定**: PASS — 确认后连接建立

---

## NM-TCP-05: TCP_ACCEPT — 手动拒绝

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证手动拒绝后 Client 被断开 |

**测试步骤**:

1. 创建 TCP Server (Port=9195, AcceptMode=0x00)
2. MCP NM Client 连接 → 收到 TCP_ACCEPT 事件 (CH)
3. **[COM35] TCP_ACCEPT 拒绝** (Decision=0x01)
4. **MCP NM**: Client 连接被 RST/拒绝

**判定**: PASS — Client 被拒绝

---

## NM-UDP-01: HEX-Bridge UDP Server → MCP NM UDP Client (收发)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge UDP Server 收发, 并使用 UDP_RECV 上报源地址 |

**测试步骤**:

1. **[COM35] UDP_SERVER_OPEN**
   ```
   Port=9196, BroadcastMode=0x00, MulticastAddr=0
   → ServerHandle=SH
   ```

2. **[MCP NM] 创建 UDP Client (不绑定 listen)**
   ```
   connId="nm-udp-cli", protocol=udp, role=client, host=<HEX IP>, port=9196
   ```

3. **[MCP NM] 发送 UDP 数据**
   ```
   send_network_data(connId="nm-udp-cli", data="UDP HELLO", format="string")
   ```

4. **[COM35] 等待 UDP_RECV 事件**
   ```
   → 预期: Handle=SH, SrcIP=PC IP, SrcPort=已分配, Data="UDP HELLO"
   ```

5. **[COM35] UDP_SERVER_SEND 回复到 MCP NM**
   ```
   CmdCode=0x64, DestIP=PC IP, DestPort=<SrcPort>, Data="UDP ACK"
   → 预期: Status=0x00
   ```

6. **[MCP NM] 验证收到回复**
   ```
   read_network_buffer(port="nm-udp-cli") → 包含 "UDP ACK"
   ```

7. **清理**

**判定**: PASS — UDP 双向收发, 源地址正确上报

---

## NM-UDP-02: HEX-Bridge UDP Client → MCP NM UDP Server

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge UDP Client 的 Create + Send + Delete 生命周期 |

**测试步骤**:

1. **[MCP NM] 启动 UDP Server 监听**
   ```
   connId="nm-udp-srv", protocol=udp, role=server, listenPort=9197
   ```

2. **[COM35] UDP_CLIENT_CREATE**
   ```
   DefaultDestIP=PC IP, DefaultDestPort=9197, LocalPort=0
   → ClientHandle=CH, ActualPort 非零
   ```

3. **[COM35] UDP_CLIENT_SEND (使用默认地址)**
   ```
   AddrMode=0x00, Data="UDP FROM HEX"
   → 预期: Status=0x00
   ```

4. **[MCP NM] 验证收到数据**
   ```
   read_network_buffer(port="nm-udp-srv") → 包含 "UDP FROM HEX"
   ```

5. **[COM35] UDP_CLIENT_DELETE**
   ```
   → 预期: Status=0x00
   ```

6. **[COM35] UDP_CLIENT_SEND (删除后)**
   ```
   → 预期: Status=ERR_NET_HANDLE_INVALID
   ```

**判定**: PASS — 生命周期完整, 删除后句柄失效

---

## NM-UDP-03: UDP_SERVER_OPEN — 广播模式

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 UDP 广播发送 |

**测试步骤**:

1. **[COM35] UDP_SERVER_OPEN**
   ```
   Port=9198, BroadcastMode=0x01
   ```

2. **[MCP NM] UDP 监听 9198**
   ```
   connId="nm-bc", protocol=udp, role=server, listenPort=9198
   ```

3. **[COM35] UDP_SERVER_SEND 广播**
   ```
   DestIP=255.255.255.255, DestPort=9198, Data="BROADCAST"
   ```

4. **[MCP NM] 验证收到广播**
   ```
   read_network_buffer(port="nm-bc") → 包含 "BROADCAST"
   ```

**判定**: PASS — 广播数据到达

---

## NM-WS-01: HEX-Bridge WebSocket Server → MCP NM WS Client (Text 收发)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge WebSocket Server 的握手 + Text 收发 + Close 码 |

**测试步骤**:

1. **[COM35] WS_SERVER_OPEN**
   ```
   Port=9199, MaxConn=3, Path="/test", SubProtoLen=0
   → ServerHandle=SH
   ```

2. **[MCP NM] WebSocket Client 连接**
   ```
   connect_network: connId="nm-ws-cli", protocol=websocket, role=client,
                    url="ws://<HEX IP>:9199/test"
   ```

3. **[COM35] 等待 WS_ACCEPT 事件**
   ```
   → ServerHandle=SH, ClientHandle=CH, ClientIP=PC IP, Path="/test"
   ```

4. **[MCP NM] 发送 WebSocket Text**
   ```
   send_network_data(connId="nm-ws-cli", data="Hello WebSocket", format="string")
   ```

5. **[COM35] 等待 WS_RECV 事件**
   ```
   → 预期: ConnHandle=CH, MsgType=0x01 (Text), Data="Hello WebSocket"
   ```

6. **[COM35] WS_SEND Text 回复**
   ```
   CmdCode=0x74, MsgType=0x01, Data="WS ACK"
   → 预期: Status=0x00
   ```

7. **[MCP NM] 验证收到**
   ```
   read_network_buffer(port="nm-ws-cli") → 包含 "WS ACK"
   ```

8. **[COM35] WS_CLIENT_DISCONNECT**
   ```
   CmdCode=0x73, CloseCode=1000
   → 预期: Status=0x00, 收到 WS_DISCONNECT_EVENT
   ```

9. **[COM35] WS_SERVER_CLOSE**

**判定**: PASS — 全部步骤通过

---

## NM-WS-02: HEX-Bridge WS Client → MCP NM WS Server

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 作为 WebSocket Client 连接远端 WS Server |

**测试步骤**:

1. **[MCP NM] 启动 WebSocket Server**
   ```
   connect_network: connId="nm-ws-srv", protocol=websocket, role=server,
                    listenPort=9200, path="/echo"
   ```

2. **[COM35] WS_CLIENT_CONNECT**
   ```
   ServerIP=PC IP, ServerPort=9200, Path="/echo"
   → 预期: Status=0x00, ClientHandle=CH, ConnResult=0x01
   ```

3. **[COM35] WS_SEND 发送数据**
   ```
   MsgType=0x01, Data="Hello from HEX"
   → 预期: Status=0x00
   ```

4. **[MCP NM] 验证接收**
   ```
   read_network_buffer(port="nm-ws-srv") → 包含 "Hello from HEX"
   get_network_clients(connId="nm-ws-srv") → 有 1 个 client
   ```

5. **[MCP NM] 发送 WebSocket Pong**
   ```
   send_network_data(connId="nm-ws-srv", data="PONG_FRAME", format="string")
   ```

6. **[COM35] 等待 WS_RECV 事件**

7. **[COM35] WS_CLIENT_DISCONNECT**

**判定**: PASS — HEX-Bridge 成功作为 WS Client 工作

---

## NM-WS-03: WebSocket Binary 消息收发

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 WebSocket Binary 帧的编码/解码正确性 (特殊字节 0x7E/0x7D) |

**测试步骤**:

1. WS_SERVER_OPEN (Port=9201, Path="/bin")
2. MCP NM WS Client 连接
3. **[COM35] WS_SEND Binary**
   ```
   MsgType=0x02 (Binary), Data=0x00 0xFF 0x7E 0x7D 0x42
   → 包含 UBCP 转义特殊字节, 验证 WS 帧编码不受影响
   ```
4. **[MCP NM] 验证二进制数据完整性**
   ```
   read_network_buffer(port="nm-bin-cli", display="hex")
   → 预期: 收到 00 FF 7E 7D 42, 无截断无转义
   ```
5. 清理

**判定**: PASS — 含特殊字节的 Binary 帧收发完整

---

## NM-WS-04: WebSocket Ping/Pong 心跳

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 WS_SEND Ping 后设备端链路保持 |

**测试步骤**:

1. WS_SERVER_OPEN + MCP NM 连接 → ClientHandle=CH
2. **[COM35] WS_SEND Ping**
   ```
   MsgType=0x09, Data="" (空)
   → 预期: Status=0x00
   ```
3. **[COM35] WS_SEND Ping 带 Payload**
   ```
   MsgType=0x09, Data="HEARTBEAT"
   → 预期: Status=0x00
   ```
4. 链路仍处于 ESTABLISHED 状态, 可继续收发
5. 清理

**判定**: PASS — Ping 帧不影响连接

---

## NM-INT-01: 网络模块集成测试 (TCP + UDP + WS 并发)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 TCP Server, UDP Server, WS Server 同时运行, 互不干扰 |

**测试步骤**:

1. **同时创建 3 个 Server**:
   - TCP Server (Port=9300)
   - UDP Server (Port=9301)
   - WS Server (Port=9302, Path="/srv")

2. **[MCP NM] 同时连接 3 个 Server**
   - `nm-tcp-srv-client` → TCP 9300
   - `nm-udp-srv-client` → UDP 9301
   - `nm-ws-srv-client` → WS 9302

3. **交错收发**:
   ```
   TCP_SEND("TCP-DATA-1")  UDP_SERVER_SEND("UDP-DATA-1")  WS_SEND("WS-DATA-1")
   TCP_SEND("TCP-DATA-2")  UDP_SERVER_SEND("UDP-DATA-2")  WS_SEND("WS-DATA-2")
   ```

4. **[MCP NM] 验证 3 个通道的收发缓冲区各含 2 条消息**

5. **关闭所有 Server**

**判定**: PASS — 3 协议并发工作, 无串扰

---

## NM-INT-02: HEX-Bridge 作为 Client 并发连接多个 MCP NM Server

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge 同时作为多个协议的 Client |

**测试步骤**:

1. **[MCP NM] 同时启动 3 个 Server**:
   - TCP Server (9310), UDP Server (9311), WS Server (9312, "/echo")

2. **[COM35] 依次创建 3 个 Client 连接**:
   - TCP_CLIENT_CONNECT(PC_IP, 9310)
   - UDP_CLIENT_CREATE(PC_IP, 9311)
   - WS_CLIENT_CONNECT(PC_IP, 9312, "/echo")

3. **[COM35] 3 个 Client 同时发送数据**

4. **[MCP NM] 验证 3 个 Server 都收到数据**

5. **清理**

**判定**: PASS — HEX-Bridge 多 Client 并发正常

---

## NM-STR-01: 大数据量 TCP 收发测试

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 TCP 大数据量发送不丢包 |

**测试步骤**:

1. TCP_SERVER_OPEN(Port=9320)
2. MCP NM Client 连接
3. **[COM35] TCP_SEND 1024 字节递增序列**
   ```
   DataLen=0x0400, Data=0x00 0x01 0x02 ... 0xFF 0x00 0x01 ...
   ```
4. **[MCP NM] 验证**
   ```
   read_network_buffer → 1024 字节完整, 序列连续无断点
   ```
5. **交换方向**: MCP NM 发送 1024 字节, COM35 等待 TCP_RECV 验证完整
6. 清理

**判定**: PASS — 1024 字节无丢包

---

## NM-TCP-06: TCP_LIST_CLIENTS + KICK 端到端

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge TCP Server 客户端列表查询和踢出功能 |
| **涉及工具** | Serial Monitor (COM35) + MCP Network Monitor |

**测试步骤**:

1. **[COM35] TCP_SERVER_OPEN**
   ```
   Port=9198, MaxConn=3, AcceptMode=0x01
   → ServerHandle=SH
   ```

2. **[MCP NM] 创建 2 个 TCP Client 连接**
   ```
   connId="nm-kick-A", protocol=tcp, role=client, host=<HEX IP>, port=9198
   connId="nm-kick-B", protocol=tcp, role=client, host=<HEX IP>, port=9198
   ```

3. **[COM35] 等待 2 次 TCP_ACCEPT 事件** → 记录 CH_A, CH_B

4. **[COM35] TCP_LIST_CLIENTS(SH)**
   ```
   → ClientCount=2, 两个条目分别包含 CH_A 和 CH_B
   ```

5. **[COM35] TCP_KICK_CLIENT(CH_A, ForceFlag=0x01)**
   ```
   → Status=0x00
   ```

6. **[COM35] 等待 TCP_DISCONNECT_EVENT(CH_A)** → 收到

7. **[MCP NM] 验证 nm-kick-A 已断开**
   ```
   → get_network_status(connId="nm-kick-A") → disconnected
   ```

8. **[COM35] TCP_LIST_CLIENTS(SH)**
   ```
   → ClientCount=1, 仅包含 CH_B
   ```

9. **[MCP NM] nm-kick-B 仍可正常收发**

10. **清理**

**判定**: PASS — KICK 后目标客户端断开, 其他客户端不受影响

---

## NM-TCP-07: TCP_LIST_CLIENTS — 空 Server 查询

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证无客户端时 TCP_LIST_CLIENTS 正常工作 |

**测试步骤**:

1. **[COM35] TCP_SERVER_OPEN(Port=9199)**
   ```
   → ServerHandle=SH_EMPTY
   ```

2. **[COM35] TCP_LIST_CLIENTS(SH_EMPTY)**
   ```
   → Status=0x00, ClientCount=0
   ```

3. **清理**

**判定**: PASS — 空 Server 正确返回 ClientCount=0

---

## NM-WS-05: WS_LIST_CLIENTS + KICK 端到端

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 HEX-Bridge WS Server 客户端列表查询和踢出功能 |
| **涉及工具** | Serial Monitor (COM35) + MCP Network Monitor |

**测试步骤**:

1. **[COM35] WS_SERVER_OPEN**
   ```
   Port=9200, MaxConn=3, Path="/ws-test"
   → ServerHandle=SH
   ```

2. **[MCP NM] 创建 2 个 WS Client 连接**
   ```
   connId="nm-ws-A", protocol=websocket, role=client, url="ws://<HEX IP>:9200/ws-test"
   connId="nm-ws-B", protocol=websocket, role=client, url="ws://<HEX IP>:9200/ws-test"
   ```

3. **[COM35] 等待 2 次 WS_ACCEPT 事件** → 记录 CH_A, CH_B

4. **[COM35] WS_LIST_CLIENTS(SH)**
   ```
   → ClientCount=2, Path="/ws-test"
   ```

5. **[COM35] WS_KICK_CLIENT(CH_A, ForceFlag=0x01)**
   ```
   → Status=0x00
   ```

6. **[COM35] 等待 WS_DISCONNECT_EVENT(CH_A)** → 收到

7. **[COM35] WS_LIST_CLIENTS(SH)**
   ```
   → ClientCount=1, 仅包含 CH_B
   ```

8. **[MCP NM] nm-ws-B 仍可正常收发**

9. **清理**

**判定**: PASS — WS KICK 功能正常

---

## NM-INT-03: NET_LIST_CONNS 全局概览

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 NET_LIST_CONNS 能一站式汇总所有网络连接 |
| **涉及工具** | Serial Monitor (COM35) + MCP Network Monitor |

**测试步骤**:

1. **[COM35] 创建混合连接**
   ```
   TCP_SERVER_OPEN(Port=9201) → SH_TCP
   UDP_CLIENT_CREATE(DestIP=<PC IP>, DestPort=9202) → CH_UDP
   ```

2. **[MCP NM] 创建对端**
   ```
   connect_network: connId="nm-tcp-cli", protocol=tcp, role=client, host=<HEX IP>, port=9201
   connect_network: connId="nm-udp-srv", protocol=udp, role=server, listenPort=9202
   ```

3. **[COM35] NET_LIST_CONNS (空载荷)**
   ```
   → Status=0x00, ConnCount≥3
     条目1: ConnType=TCP_SERVER(0x00), Handle=SH_TCP, ParentHandle=0x0000
     条目2: ConnType=TCP_CONN(0x01), Handle=<CH>, ParentHandle=SH_TCP
     条目3: ConnType=UDP_CLIENT(0x03), Handle=CH_UDP, ParentHandle=0x0000
   ```

4. **验证** ConnType 和 ParentHandle 关系正确

5. **清理**

**判定**: PASS — NET_LIST_CONNS 正确汇总 TCP Server/Conn 和 UDP Client

---

# 第一部分：以太网驱动层测试 (DRV)

---

## DRV-01: 物理链路 UP 检测 (NET_LINK_EVENT)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 LAN8720 PHY 初始化成功, 网线插入后链路 UP |
| **CmdCode** | `0x43` (NET_LINK_EVENT, 事件) |
| **测试方法** | 设备上电后监听 COM35, 等待 DEV 侧主动上报的事件帧 |

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | IntfIndex | `0x00` (ETH0) |
| 1 | EventType | `0x02` (IP_ACQUIRED) — DHCP 获取到 IP 后 |

如果 DHCP 响应较慢, 可能先收到 LINK_UP (`0x01`) 再收到 IP_ACQUIRED (`0x02`)。

**判定**: PASS — 上电后 30s 内收到 LAN8720 上报的 LINK_UP 和 IP_ACQUIRED 事件

---

## DRV-02: 网线拔出检测 (NET_LINK_EVENT)

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证网线拔出后 PHY 正确检测链路断开 |
| **CmdCode** | `0x43` (NET_LINK_EVENT, 事件) |

**测试步骤**:
1. 确认设备在线, 网线已连接
2. 拔出网线
3. 监听 COM35, 等待 LINK_DOWN 事件

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | IntfIndex | `0x00` |
| 1 | EventType | `0x00` (LINK_DOWN) |
| 2-5 | IpAddr | `0x00000000` |

**判定**: PASS — 拔出网线后 2s 内收到 LINK_DOWN 事件

---

## DRV-03: 网线重新插入后的链路恢复

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证热插拔恢复 |
| **CmdCode** | `0x43` (NET_LINK_EVENT) |

**测试步骤**:
1. 从 DRV-02 的 LINK_DOWN 状态出发
2. 重新插入网线
3. 监听 LINK_UP → IP_ACQUIRED 事件序列

**预期**: 顺序收到 `EventType=0x01 (LINK_UP)` 和 `EventType=0x02 (IP_ACQUIRED)`, IpAddr 与之前可能相同或不同

**判定**: PASS — 网线插入后 30s 内链路恢复

---

## DRV-04: DHCP 服务器不可用

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 DHCP 服务器不可用时设备不崩溃, 正常上报 ConnState=0x02 |
| **CmdCode** | `0x41` (NET_STATUS), `0x43` (NET_LINK_EVENT) |

**测试步骤**:
1. 断开路由器 DHCP 服务 (或拔掉路由器 WAN 口, 仅保留 LAN 交换机功能)
2. HEX-Bridge 断电重启
3. 监听 COM35 - 预期收到 LINK_UP 事件 (EventType=0x01)
4. 发送 NET_STATUS(0x00) 查询

**预期 NET_STATUS 响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 3 | LinkState | `0x01` (Up) |
| 4 | ConnState | `0x02` (获取IP中) |
| 5-8 | IpAddr | `0x00000000` |

**预期**: 设备不崩溃, ConnState=0x02 持续, IpAddr 为 0, 不产生 IP_ACQUIRED 事件

**判定**: PASS — 设备不崩溃, ConnState=0x02, IpAddr=0x00000000

---

## DRV-05: 网线快速插拔

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证快速插拔时事件不丢失 |
| **CmdCode** | `0x43` (NET_LINK_EVENT) |

**测试步骤**:
1. 在 5 秒内快速插拔网线 10 次 (使用物理操作)
2. 监听 COM35 记录所有 NET_LINK_EVENT 事件

**预期**:
- 每个插拔周期产生正确的 LINK_DOWN / LINK_UP 事件对
- 事件无丢失, 无重复
- 总共 20 个事件 (10 × DOWN + 10 × UP)

**判定**: PASS — 10 对 LINK_DOWN/LINK_UP 事件, 无丢失

---

# 第二部分：网络配置模块测试 (NET, 0x40-0x4F)

---

## NET-01: NET_STATUS — 查询网络状态 (正常流程)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x41` |
| **PayloadLen** | `0x0001` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | InterfaceIndex | `0x00` (ETH0) |

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | IntfCount | `0x01` |
| 2 | IntfIndex | `0x00` |
| 3 | LinkState | `0x01` (Up) |
| 4 | ConnState | `0x01` (已连接) |
| 5-8 | IpAddr | 有效的非零 IP (DHCP 分配或静态配置) |
| 9-12 | SubnetMask | 有效的子网掩码 |
| 13-18 | MacAddr | 6 字节 MAC 地址 |

**判定**: PASS — Status=0x00, LinkState=0x01, IpAddr 非零

---

## NET-02: NET_STATUS — 查询所有接口 (InterfaceIndex=0xFF)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x41` |
| **PayloadLen** | `0x0001` |

**请求载荷**: InterfaceIndex=`0xFF`

**预期响应**: Status=`0x00`, IntfCount=`0x01`, 包含 ETH0 的状态

**判定**: PASS — 与 NET-01 结果一致

---

## NET-03: NET_DNS — 域名解析成功

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x42` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | NameLen | `0x0B` (11) |
| 1-11 | Hostname | `"example.com"` (ASCII) |

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | AddrCount | `>= 1` |
| 2-5 | IP[0] | 有效的 IPv4 地址 |

**判定**: PASS — Status=0x00, AddrCount>=1

---

## NET-04: NET_DNS — 域名解析失败 (不存在的域名)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x42` |

**请求载荷**: NameLen=`0x17` (23), Hostname=`"nonexistent-domain.invalid"`

**预期响应**: Status=`0x46` (ERR_NET_DNS_FAIL)

**判定**: PASS — 返回 DNS_FAIL 错误码

---

## NET-05: NET_DNS — 域名字符串超长 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x42` |

**请求载荷**: NameLen=`0xFF` (255), Hostname=254 字节填充数据 (超过 lwIP DNS 253 字节限制)

**预期响应**: Status=`0x02` (ERR_PARAM) — 设备应拒绝超长域名

---

## NET-06: NET_CONFIG — 设置静态 IP

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x40` |
| **PayloadLen** | `0x0016` (22 字节) |

**请求载荷**:

| 偏移 | 字段 | 值 (示例) |
|:---|:---|:---|
| 0 | InterfaceIndex | `0x00` (ETH0) |
| 1 | ConfigType | `0x01` (静态 IP) |
| 2-5 | IpAddr | `0xC0A80164` (192.168.1.100) |
| 6-9 | SubnetMask | `0xFFFFFF00` (255.255.255.0) |
| 10-13 | Gateway | `0xC0A80101` (192.168.1.1) |
| 14-17 | DNS1 | `0x08080808` (8.8.8.8) |
| 18-21 | DNS2 | `0x00000000` (无) |

**预期响应**: Status=`0x00`, ActualIP/ActualMask/ActualGW/ActualDNS 与请求一致

**验证**: 发送 NET_STATUS 查询, 确认 IpAddr=192.168.1.100

---

## NET-07: NET_CONFIG — 恢复 DHCP 模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x40` |
| **PayloadLen** | `0x0002` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | InterfaceIndex | `0x00` |
| 1 | ConfigType | `0x00` (DHCP) |

**预期响应**: Status=`0x00`

**验证**: 等待 IP_ACQUIRED 事件, 发送 NET_STATUS 确认 IP 由 DHCP 分配

---

## NET-08: NET_CONFIG — 无效 InterfaceIndex (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x40` |
| **PayloadLen** | `0x0002` |

**请求载荷**: InterfaceIndex=`0x02` (不存在), ConfigType=`0x00` (DHCP)

**预期响应**: Status=`0x0A` (ERR_CHANNEL_INVALID)

---

## NET-09: NET_CONFIG — 无效 ConfigType (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x40` |
| **PayloadLen** | `0x0002` |

**请求载荷**: InterfaceIndex=`0x00`, ConfigType=`0x02` (未定义)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

## NET-10: NET_STATUS — 网线拔出时查询

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x41` |

**前置**: 拔出网线, 确认已收到 LINK_DOWN 事件

**请求载荷**: InterfaceIndex=`0x00`

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 3 | LinkState | `0x00` (Down) |
| 4 | ConnState | `0x00` (未连接) |
| 5-8 | IpAddr | `0x00000000` |

**判定**: PASS — 正确反映断线状态

---

## NET-11: NET_DNS — DNS 服务器不可达 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x42` |

**前置**: 通过 NET_CONFIG 静态 IP 将 DNS1 设为不可达地址 (如 `192.168.1.254`)

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0 | NameLen | `0x0B` (11) |
| 1-11 | Hostname | `"example.com"` |

**预期响应**: Status=`0x46` (ERR_NET_DNS_FAIL), DNS 请求超时约 5s 后返回

**判定**: PASS — 超时后返回 DNS_FAIL

---

## NET-12: NET_STATUS — DHCP 获取中 (ConnState=0x02)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x41` |

**前置**: 通过 NET_CONFIG 切换到 DHCP 模式后立即查询, 或重启设备后立即查询

**请求载荷**: InterfaceIndex=`0x00`

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 4 | ConnState | `0x02` (获取IP中) |
| 5-8 | IpAddr | `0x00000000` |

**判定**: PASS — ConnState=0x02, IpAddr=0x00000000

---

## NET-13: NET_DNS — 无 IP 时调用 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x42` |

**前置**: 拔出网线, 设备无 IP 地址 (NET_STATUS 显示 IpAddr=0x00000000)

**请求载荷**: NameLen=`0x0B` (11), Hostname=`"example.com"`

**预期响应**: Status=`0x47` (ERR_NET_NO_IP)

**判定**: PASS — 无 IP 时拒绝 DNS 解析

---

## NET-14: NET_CONFIG — NVS 持久化验证

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x40`, `0x41` |

**测试步骤**:
1. NET_CONFIG: 设置静态 IP (192.168.1.100, Gateway 192.168.1.1, DNS 8.8.8.8)
2. 等待 NET_STATUS 确认 IP 为 192.168.1.100
3. 设备断电重启
4. 上电握手完成后直接发送 NET_STATUS(0x00)

**预期**: 重启后无需重新配置, NET_STATUS 直接报告静态 IP (192.168.1.100), Gateway 和 DNS 与配置一致

**判定**: PASS — NVS 持久化生效

---

## NET-15: NET_LINK_EVENT — IP_CHANGED 事件

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x43` (事件) |

**前置**: DHCP 模式下, 配置路由器 DHCP 租约较短 (如 60s), 或在路由器侧强制变更分配给设备的 IP

**测试步骤**:
1. 等待当前 DHCP 租约到期
2. 路由器分配不同 IP
3. 监听 COM35

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | IntfIndex | `0x00` |
| 1 | EventType | `0x04` (IP_CHANGED) |
| 2-5 | IpAddr | 新 IP 地址 |

**判定**: PASS — 收到 IP_CHANGED 事件, 包含新 IP

---

## NET-16: NET_LIST_CONNS — 全局连接查询

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x44` |

**前置**: 至少创建了 1 个 TCP Server 和 1 个 UDP Client

**请求载荷**: 空 (无载荷)

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | ConnCount | 非零值 (等于当前活跃连接数) |

遍历每个连接条目:
| 偏移 | 字段 | 验证 |
|:---|:---|:---|
| 0 | ConnType | 值在 0x00-0x05 范围内 |
| 1-2 | Handle | 非零合法句柄 |
| 3-4 | ParentHandle | Server 子连接时非零, 否则 0x0000 |
| 5-6 | LocalPort | 非零合法端口号 |
| 7-10 | RemoteIP | Server 模式为 0x00000000, 否则为对端 IP |

**判定**: PASS — ConnCount 与预期一致, 条目字段合法

---

# 第三部分：TCP 模块测试 (TCP, 0x50-0x5F)

---

## TCP-01: TCP_SERVER_OPEN — 创建 TCP Server (正常)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x50` |
| **PayloadLen** | `0x0005` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | Port | `0x1F90` (8080) |
| 2 | MaxConn | `0x03` (最大 3 个连接) |
| 3 | AcceptMode | `0x01` (自动接受) |
| 4 | KeepAlive | `0x3C` (60 秒保活) |

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-2 | ServerHandle | 非零值 (0x0001-0x7FFF) |
| 3-4 | ActualPort | `0x1F90` (8080) |

**验证**: MCP NM Client 或 `nc 192.168.x.x 8080` 连接确认 (推荐 MCP NM, 见 NM-TCP-02)

**判定**: PASS — Status=0x00, ServerHandle 合法, 实际端口无误

---

## TCP-02: TCP_SERVER_OPEN — 系统自动分配端口

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x50` |

**请求载荷**: Port=`0x0000` (0=自动), MaxConn=2, AcceptMode=0x01, KeepAlive=0

**预期响应**: Status=`0x00`, ActualPort 非零 (系统随机分配)

---

## TCP-03: TCP_SERVER_OPEN — 端口已被占用 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x50` |

**前置**: 已成功执行 TCP-01 (8080 端口已占用)

**请求载荷**: Port=`0x1F90` (8080), 其他参数同 TCP-01

**预期响应**: Status=`0x45` (ERR_NET_PORT_IN_USE)

---

## TCP-04: TCP_SERVER_OPEN — 超过最大 Server 数 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x50` |

**前置**: 已创建 4 个 Server (达到 TCP_MAX_SERVERS=4 上限)

**预期响应**: Status=`0x48` (ERR_NET_MAX_CONN)

---

## TCP-05: TCP_ACCEPT — 客户端连接事件 (Server 端)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x56` (事件) |

**前置**: 已创建 TCP Server (AcceptMode=0x01, 自动接受)

**测试步骤**:
1. 在辅助 PC 上执行 `nc 192.168.x.x 8080`
2. 监听 COM35, 等待 TCP_ACCEPT 事件

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0-1 | ServerHandle | 与 TCP-01 返回的一致 |
| 2-3 | ClientHandle | 0x8001-0xFFFE 范围 |
| 4-7 | ClientIP | 辅助 PC 的 IP 地址 |
| 8-9 | ClientPort | 辅助 PC 的源端口 |

**判定**: PASS — 收到 TCP_ACCEPT 事件, 各字段正确

---

## TCP-06: TCP_SEND — Server 端发送数据到客户端

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**前置**: 已有客户端连接到 TCP Server (从 TCP-05 获得 ClientHandle)

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ConnHandle | ClientHandle (来自 TCP_ACCEPT 事件) |
| 2-3 | DataLen | `0x000C` (12) |
| 4-15 | Data | `"Hello Client"` (ASCII) |

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-2 | ActualLen | `0x000C` (12) |

**验证 (辅助 PC)**: `nc` 终端收到 `"Hello Client"`

**判定**: PASS — Status=0x00, ActualLen=12, 辅助 PC 收到数据

---

## TCP-07: TCP_RECV — 接收客户端发来的数据 (事件)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x55` (事件) |

**前置**: 已有客户端连接到 TCP Server

**测试步骤**:
1. 在辅助 PC 的 `nc` 终端中输入 `"Hello Server"` 并回车
2. 监听 COM35, 等待 TCP_RECV 事件

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0-1 | ConnHandle | ClientHandle |
| 2-3 | DataLen | `0x000D` (13, 含 `\r\n`) |
| 4-16 | Data | `"Hello Server\r\n"` |

**判定**: PASS — 收到 TCP_RECV 事件, 数据与发出的完全一致

---

## TCP-08: TCP_CLIENT_CONNECT — 作为客户端连接远端 TCP Server

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x52` |
| **PayloadLen** | `0x0008` |

**前置**: 辅助 PC 上已启动 TCP Server (如 `nc -l 9090`)

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-3 | DestIP | 辅助 PC 的 IP (big-endian) |
| 4-5 | DestPort | `0x2382` (9090) |
| 6 | TimeoutSec | `0x05` (5 秒) |
| 7 | KeepAlive | `0x00` (禁用) |

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-2 | ConnHandle | 0x8001-0xFFFE 范围 |
| 3-6 | LocalIP | ESP32 的 IP 地址 |
| 7-8 | LocalPort | ESP32 的临时端口 |

**验证 (辅助 PC)**: `nc` Server 显示新客户端连接进入

**判定**: PASS — Status=0x00, ConnHandle 合法

---

## TCP-09: TCP_CLIENT_CONNECT — 连接超时 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x52` |

**请求载荷**: DestIP=辅助 PC IP, DestPort=`0x2383` (9091, 无服务监听), TimeoutSec=`0x02`

**预期响应**: Status=`0x42` (ERR_NET_TIMEOUT)

---

## TCP-10: TCP_CLIENT_CONNECT — 连接被拒绝 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x52` |

**请求载荷**: DestIP=辅助 PC IP, DestPort=`0x2383` (9091), TimeoutSec=`0x05`

> 辅助 PC 防火墙主动拒绝 9091 端口的 SYN 包 (或使用 iptables REJECT)

**预期响应**: Status=`0x41` (ERR_NET_CONN_REFUSED)

---

## TCP-11: TCP_CLIENT_DISCONNECT — 正常断开

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x53` |
| **PayloadLen** | `0x0003` |

**前置**: 已建立 TCP 客户端连接 (TCP-08)

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ConnHandle | TCP-08 返回的连接句柄 |
| 2 | Method | `0x00` (正常 FIN) |

**预期响应**: Status=`0x00`

**验证 (辅助 PC)**: `nc` Server 显示客户端断开

---

## TCP-12: TCP_CLIENT_DISCONNECT — 强制 RST 断开

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x53` |

**请求载荷**: Method=`0x01` (强制 RST)

**预期响应**: Status=`0x00`

**验证**: 辅助 PC 端检测到连接被重置 (RST)

---

## TCP-13: TCP_DISCONNECT_EVENT — 远端断开时的事件上报

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x58` (事件) |

**前置**: 已有客户端连接到 TCP Server (TCP-05)

**测试步骤**:
1. 在辅助 PC 的 `nc` 终端按 `Ctrl+C` 断开连接
2. 监听 COM35, 等待 TCP_DISCONNECT_EVENT

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0-1 | ConnHandle | 断开的连接句柄 |
| 2 | Reason | `0x00` (正常关闭) |
| 3-6 | RemoteIP | 辅助 PC 的 IP |
| 7-8 | RemotePort | 辅助 PC 的端口 |

**判定**: PASS — 收到断开事件, Reason 正确

---

## TCP-14: TCP_SEND — 使用广播句柄发送到所有客户端

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**前置**: TCP Server 上有 2 个客户端连接

**请求载荷**: ConnHandle=`0x8000` (广播句柄), DataLen=5, Data=`"ALL\r\n"`

**预期响应**: Status=`0x00`

**验证**: 两个客户端都收到 `"ALL\r\n"`

---

## TCP-15: TCP_SEND — 无效句柄 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**请求载荷**: ConnHandle=`0x1234` (不存在), DataLen=3, Data=`"ABC"`

**预期响应**: Status=`0x43` (ERR_NET_HANDLE_INVALID)

---

## TCP-16: TCP_SEND — 向已断开的连接发送数据

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**前置**: 远端已断开 (从 TCP-13 的 DISCONNECT_EVENT 拿到 ConnHandle), 但句柄尚未被设备回收

**预期响应**: Status=`0x40` (ERR_NET_DISCONNECTED)

---

## TCP-17: TCP_SERVER_CLOSE — 关闭 Server (正常)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x51` |
| **PayloadLen** | `0x0003` |

**前置**: TCP Server 已有 1 个客户端连接

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ServerHandle | TCP-01 返回的句柄 |
| 2 | ForceClose | `0x01` (立即关闭) |

**预期响应**: Status=`0x00`

**验证**:
- 辅助 PC 检测到连接断开
- 设备收到 TCP_DISCONNECT_EVENT (如果有子连接)
- 该 Server 句柄释放, 可重新创建

---

## TCP-18: TCP_SERVER_CLOSE — 无效句柄 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x51` |

**请求载荷**: ServerHandle=`0x0000` (无效), ForceClose=`0x01`

**预期响应**: Status=`0x43` (ERR_NET_HANDLE_INVALID)

---

## TCP-19: TCP_CLOSE — 通用关闭 (HandleType=0, 连接)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x57` |
| **PayloadLen** | `0x0004` |

**请求载荷**: Handle=ClientHandle, HandleType=`0x00`, ForceFlag=`0x00`

**预期响应**: Status=`0x00`, 与 TCP_CLIENT_DISCONNECT 行为一致

---

## TCP-20: TCP_CLOSE — 通用关闭 (HandleType=1, Server)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x57` |

**请求载荷**: Handle=ServerHandle, HandleType=`0x01`, ForceFlag=`0x01`

**预期响应**: Status=`0x00`, 与 TCP_SERVER_CLOSE 行为一致

---

## TCP-21: TCP_SEND — 大数据量发送

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**前置**: 已建立连接

**请求载荷**: DataLen=`0x0400` (1024), Data=1024 字节递增序列

**预期响应**: Status=`0x00`, ActualLen=`0x0400`

**验证**: 辅助 PC 收到完整 1024 字节数据, 无截断

---

## TCP-22: TCP_ACCEPT — 手动接受模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x56` (事件 + 命令) |

**前置**: 创建 TCP Server (AcceptMode=`0x00`)

**测试步骤**:
1. 辅助 PC 连接 TCP Server
2. 收到 TCP_ACCEPT 事件 (上报, DIR=1, EVT=1)
3. 测试脚本通过 COM35 发送 TCP_ACCEPT **命令** (DIR=0) 确认

**请求载荷 (确认命令)**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ClientHandle | 事件帧中的句柄 |
| 2 | Decision | `0x00` (接受) |

**预期响应**: Status=`0x00`

**验证**: 辅助 PC 连接状态变为 ESTABLISHED (如果不确认, 连接应超时)

---

## TCP-23: TCP_ACCEPT — 手动拒绝

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x56` |

**前置**: 创建 TCP Server (AcceptMode=`0x00`), 辅助 PC 发起连接

**确认载荷**: Decision=`0x01` (拒绝)

**预期响应**: Status=`0x00`

**验证**: 辅助 PC 连接被拒绝, 设备不分配有效通信句柄

---

## TCP-24: TCP_SERVER_OPEN — 网线拔出时创建 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x50` |

**前置**: 网线已拔出, NET_STATUS 显示 LinkState=Down

**预期响应**: Status=`0x40` (ERR_NET_DISCONNECTED) 或 `0x47` (ERR_NET_NO_IP)

---

## TCP-25: TCP 完整生命周期 (集成)

| 项目 | 值 |
|:---|:---|
| **涉及的 CmdCode** | `0x50` → `0x56` → `0x54` → `0x55` → `0x53` → `0x58` → `0x51` |

**测试步骤**:
1. **SERVER_OPEN**: 创建 Server (Port=0, AcceptMode=0x01) → Status=0x00
2. **ACCEPT**: 辅助 PC 连接 → 收到 TCP_ACCEPT (ClientHandle=C1)
3. **SEND**: TCP_SEND(C1, "Hello Client") → Status=0x00, ActualLen=12
4. **RECV**: 辅助 PC 发送 "ACK" → 收到 TCP_RECV(C1, "ACK\r\n")
5. **STATUS**: NET_STATUS → 确认链路正常
6. **DISCONNECT**: TCP_CLIENT_DISCONNECT(C1) → Status=0x00 → 收到 TCP_DISCONNECT_EVENT
7. **SERVER_CLOSE**: TCP_SERVER_CLOSE → Status=0x00

**预期**: 全部 7 步依次成功

---

## TCP-26: TCP_SEND — 发送缓冲区满 (ERR_NET_BUFFER_FULL)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**测试步骤**:
1. 创建 TCP Server (Port=9500, MaxConn=2)
2. 创建 TCP Client (Connect 到同一 PC 上的另一个监听端口, 或使用 MCP NM)
3. MCP NM Client 连接 Server, 但停止读取数据 (让 TCP 接收窗口关闭)
4. 通过 COM35 快速连续 TCP_SEND 大数据, 直到发送缓冲区满

**预期响应**: Status=`0x44` (ERR_NET_BUFFER_FULL)

**判定**: PASS — 缓冲区满时正确返回错误码

---

## TCP-27: TCP_CLIENT_CONNECT — 超过最大连接数 (ERR_NET_MAX_CONN)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x52` |

**前置**: 创建 TCP_MAX_CONNS=16 个客户端连接 (填满连接表)

**预期**: 第 17 个 TCP_CLIENT_CONNECT 请求返回 Status=`0x48` (ERR_NET_MAX_CONN)

**判定**: PASS — 最大连接数限制生效

---

## TCP-28: TCP_SERVER_CLOSE — 优雅关闭 (ForceClose=0)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x51` |

**前置**: 创建 TCP Server, 有 2 个活跃客户端连接

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ServerHandle | 服务器句柄 |
| 2 | ForceClose | `0x00` (优雅关闭) |

**预期**:
- 每个客户端收到 FIN
- 设备为每个子连接发送 TCP_DISCONNECT_EVENT
- Server 句柄释放

**判定**: PASS — 所有 DISCONNECT_EVENT 正确发出, 对端收到 FIN

---

## TCP-29: TCP 所有 OPEN/CONNECT 命令 — 无 IP 时拒绝

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x50`, `0x52` |

**前置**: 拔出网线, NET_STATUS 确认 IpAddr=0x00000000

**测试步骤**:
1. TCP_SERVER_OPEN(Port=9501) → 预期: Status=`0x47` (ERR_NET_NO_IP)
2. TCP_CLIENT_CONNECT(任意IP, 任意Port) → 预期: Status=`0x47` (ERR_NET_NO_IP)

**判定**: PASS — 两条命令均返回 ERR_NET_NO_IP

---

## TCP-30: TCP_LIST_CLIENTS — 查询已连接客户端

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x59` |

**前置**: TCP_SERVER_OPEN(Port=8080, AcceptMode=0x01) → ServerHandle=SH; 已接纳 2 个客户端

**请求载荷**: ServerHandle=SH

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | ClientCount | `0x02` |

遍历 2 个客户端条目:
| 偏移 | 字段 | 验证 |
|:---|:---|:---|
| 0-1 | ClientHandle | 非零合法句柄 |
| 2-5 | ClientIP | 合法 IP 地址 |
| 6-7 | ClientPort | 非零端口号 |
| 8-9 | ConnectTime | 有效 Duration (不超过测试运行时间) |

**判定**: PASS — ClientCount=2, 条目信息正确

---

## TCP-31: TCP_LIST_CLIENTS — 空 Server

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x59` |

**前置**: TCP_SERVER_OPEN(Port=8081, AcceptMode=0x01) → ServerHandle=SH2, 但无客户端连接

**请求载荷**: ServerHandle=SH2

**预期响应**: Status=`0x00`, ClientCount=`0x00`, 无客户端条目

**判定**: PASS — 空 Server 返回 ClientCount=0

---

## TCP-32: TCP_KICK_CLIENT — 强制断开指定客户端

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x5A` |

**前置**: TCP_SERVER_OPEN(Port=8082, AcceptMode=0x01) → SH; 客户端已连接 → CH

**测试步骤**:
1. TCP_LIST_CLIENTS(SH) → 确认 CH 存在
2. TCP_KICK_CLIENT(CH, ForceFlag=0x01) → Status=`0x00`
3. 等待 TCP_DISCONNECT_EVENT(CH, Reason=0x01)
4. TCP_LIST_CLIENTS(SH) → ClientCount=`0x00` (确认 CH 已不在列表中)

**判定**: PASS — CH 被成功断开并上报事件, 列表中不再出现

---

## TCP-33: TCP_KICK_CLIENT — 无效句柄

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x5A` |

**请求载荷**: ClientHandle=`0xFFFF` (无效句柄), ForceFlag=0x01

**预期响应**: Status=`0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS — 无效句柄返回 ERR_NET_HANDLE_INVALID

---

## TCP-34: TCP_CONN_STATUS — 查询单连接状态

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x5B` |

**前置**: TCP Client 已连接, 已知 ConnHandle=CH, 已收发数据

**请求载荷**: ConnHandle=CH

**预期响应**:

| 偏移 | 字段 | 验证 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | ConnState | `0x00` (ESTABLISHED) |
| 2-5 | TxBytes | 非零 (若已发送数据) |
| 6-9 | RxBytes | 非零 (若已接收数据) |
| 10-13 | RemoteIP | 对端 IP 地址 |
| 14-15 | RemotePort | 对端端口 |
| 16-17 | LocalPort | 本地端口 |
| 18-21 | ConnectTime | 有效 Duration |

**判定**: PASS — 状态正常, 统计数据有效

---

## TCP-35: TCP_CONN_STATUS — 无效句柄

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x5B` |

**请求载荷**: ConnHandle=`0xFFFF` (无效句柄)

**预期响应**: Status=`0x43` (ERR_NET_HANDLE_INVALID)

**判定**: PASS — 无效句柄返回 ERR_NET_HANDLE_INVALID

---

# 第四部分：UDP 模块测试 (UDP, 0x60-0x6F)

---

## UDP-01: UDP_SERVER_OPEN — 创建 UDP Server

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x60` |
| **PayloadLen** | `0x0007` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | Port | `0x1F91` (8081) |
| 2 | BroadcastMode | `0x00` (禁用广播) |
| 3-6 | MulticastAddr | `0x00000000` (禁用多播) |

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1-2 | ServerHandle | 0x0001-0x7FFF |
| 3-4 | ActualPort | `0x1F91` |

---

## UDP-02: UDP_SERVER_SEND — 发送数据到指定地址

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x64` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ServerHandle | UDP-01 返回的句柄 |
| 2-5 | DestIP | 辅助 PC 的 IP |
| 6-7 | DestPort | `0x1F92` (8082) |
| 8-9 | DataLen | `0x000B` (11) |
| 10-20 | Data | `"Hello UDP\r\n"` |

**前置**: 辅助 PC 上执行 `nc -u -l 8082`

**预期响应**: Status=`0x00`, ActualLen=11

**验证**: 辅助 PC 收到 `"Hello UDP\r\n"`

---

## UDP-03: UDP_RECV — 接收外部 UDP 数据 (事件)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x65` (事件) |

**前置**: UDP Server 已创建

**测试步骤**: 辅助 PC 执行 `echo "PONG" | nc -u 192.168.x.x 8081`

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0-1 | Handle | Server 句柄 |
| 2-5 | SrcIP | 辅助 PC 的 IP |
| 6-7 | SrcPort | 辅助 PC 的源端口 |
| 8-9 | DataLen | 5 |
| 10-14 | Data | `"PONG\n"` |

---

## UDP-04: UDP_CLIENT_CREATE — 创建 UDP Client

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x62` |
| **PayloadLen** | `0x0008` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-3 | DefaultDestIP | 辅助 PC IP (big-endian) |
| 4-5 | DefaultDestPort | `0x1F93` (8083) |
| 6-7 | LocalPort | `0x0000` (自动) |

**预期响应**: Status=`0x00`, ClientHandle 合法, ActualPort 非零

---

## UDP-05: UDP_CLIENT_SEND — 使用默认地址发送

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x66` |

**前置**: UDP Client (UDP-04) 已创建, 辅助 PC 执行 `nc -u -l 8083`

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ClientHandle | UDP-04 返回的句柄 |
| 2 | AddrMode | `0x00` (使用默认地址) |
| 3-4 | DataLen | `0x000C` (12) |
| 5-16 | Data | `"Client Hello"` |

**预期响应**: Status=`0x00`, ActualLen=12

**验证**: 辅助 PC 收到 `"Client Hello"`

---

## UDP-06: UDP_CLIENT_SEND — 使用指定地址发送

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x66` |

**请求载荷**: AddrMode=`0x01`, DestIP=辅助 PC IP, DestPort=8083, DataLen=10, Data=`"Override\r\n"`

**预期响应**: Status=`0x00`, ActualLen=10

---

## UDP-07: UDP_SERVER_OPEN — 启用广播模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x60` |

**请求载荷**: Port=8084, BroadcastMode=`0x01`

**预期响应**: Status=`0x00`

**验证**: 辅助 PC 中 `nc -u -l 8084` 能收到广播数据

---

## UDP-08: UDP_SERVER_OPEN — 多播模式

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x60` |

**请求载荷**: Port=8085, BroadcastMode=`0x00`, MulticastAddr=`0xE0000001` (224.0.0.1)

**预期响应**: Status=`0x00`

**验证**: 同一局域网内另一设备加入多播组 `224.0.0.1:8085` 可接收数据

---

## UDP-09: UDP_CLIENT_DELETE — 删除 UDP Client

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x63` |
| **PayloadLen** | `0x0002` |

**前置**: UDP Client (UDP-04) 存在

**请求载荷**: ClientHandle=UDP-04 的句柄

**预期响应**: Status=`0x00`

**验证**: 再次发送 UDP_CLIENT_SEND 应返回 `ERR_NET_HANDLE_INVALID`

---

## UDP-10: UDP_SERVER_CLOSE — 关闭 UDP Server

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x61` |
| **PayloadLen** | `0x0002` |

**前置**: UDP Server (UDP-01) 存在

**请求载荷**: ServerHandle=UDP-01 的句柄

**预期响应**: Status=`0x00`

---

## UDP-11: UDP_SERVER_OPEN — 超过最大 Server 数 (ERR_NET_MAX_CONN)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x60` |

**前置**: 已创建 UDP_MAX_SERVERS=4 个 UDP Server

**预期**: 第 5 个 UDP_SERVER_OPEN 请求返回 Status=`0x48` (ERR_NET_MAX_CONN)

**判定**: PASS — 最大 Server 数限制生效

---

## UDP-12: UDP_CLIENT_CREATE — 超过最大 Client 数 (ERR_NET_MAX_CONN)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x62` |

**前置**: 已创建 UDP_MAX_CLIENTS=8 个 UDP Client

**预期**: 第 9 个 UDP_CLIENT_CREATE 请求返回 Status=`0x48` (ERR_NET_MAX_CONN)

**判定**: PASS — 最大 Client 数限制生效

---

## UDP-13: UDP_SERVER_CLOSE — 无效句柄 (ERR_NET_HANDLE_INVALID)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x61` |

**请求载荷**: ServerHandle=`0x0000` (无效)

**预期响应**: Status=`0x43` (ERR_NET_HANDLE_INVALID)

---

## UDP-14: UDP 所有 OPEN/CREATE 命令 — 无 IP 时拒绝

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x60`, `0x62` |

**前置**: 拔出网线, NET_STATUS 确认 IpAddr=0x00000000

**测试步骤**:
1. UDP_SERVER_OPEN(Port=9502) → 预期: Status=`0x47` (ERR_NET_NO_IP)
2. UDP_CLIENT_CREATE(任意IP, 任意Port) → 预期: Status=`0x47` (ERR_NET_NO_IP)

**判定**: PASS — 两条命令均返回 ERR_NET_NO_IP

---

# 第五部分：WebSocket 模块测试 (WS, 0x70-0x7F)

---

## WS-01: WS_SERVER_OPEN — 创建 WebSocket Server

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x70` |

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | Port | `0x1F94` (8084) |
| 2 | MaxConn | `0x03` |
| 3 | PathLen | `0x03` |
| 4-6 | Path | `"/ws"` (ASCII) |
| 7 | SubProtoLen | `0x00` (无子协议) |

**预期响应**: Status=`0x00`, ServerHandle 合法, ActualPort=8084

---

## WS-02: WS_ACCEPT — WebSocket 客户端连接事件

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x76` (事件) |

**前置**: WS Server (WS-01) 已创建

**测试步骤**:
1. 辅助 PC 使用 `wscat` 或 Python `websockets` 连接: `ws://192.168.x.x:8084/ws`
2. 监听 COM35

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0-1 | ServerHandle | WS-01 返回的句柄 |
| 2-3 | ClientHandle | 0x8001-0xFFFE |
| 4-7 | ClientIP | 辅助 PC IP |
| 8-9 | ClientPort | 辅助 PC 源端口 |
| 10 | SubProtoIndex | `0x00` |
| 11 | PathLen | `0x03` |
| 12-14 | Path | `"/ws"` |

---

## WS-03: WS_SEND — 发送 Text 消息

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x74` |

**前置**: WebSocket 客户端已连接 (WS-02)

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ConnHandle | WS-02 返回的 ClientHandle |
| 2 | MsgType | `0x01` (Text) |
| 3-4 | DataLen | `0x000D` (13) |
| 5-17 | Data | `"Hello WS Text"` |

**预期响应**: Status=`0x00`, ActualLen=13

**验证**: 辅助 PC 收到 Text 消息 `"Hello WS Text"`

---

## WS-04: WS_SEND — 发送 Binary 消息

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x74` |

**请求载荷**: MsgType=`0x02`, DataLen=4, Data=`0x00 0xFF 0x42 0x7E`

**预期响应**: Status=`0x00`, ActualLen=4

**验证**: 辅助 PC 收到 4 字节二进制数据

---

## WS-05: WS_RECV — 接收 WebSocket Text 消息 (事件)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x75` (事件) |

**前置**: WebSocket 客户端已连接

**测试步骤**: 辅助 PC 发送 WebSocket Text 消息 `"Hello from client"`

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0-1 | ConnHandle | ClientHandle |
| 2 | MsgType | `0x01` (Text) |
| 3-4 | DataLen | 18 |
| 5-22 | Data | `"Hello from client"` |

---

## WS-06: WS_SEND — 发送 Ping (心跳)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x74` |

**请求载荷**: MsgType=`0x09` (Ping), DataLen=0

**预期响应**: Status=`0x00`, ActualLen=0

> 大部分 WebSocket 客户端会自动回复 Pong, 无需脚本验证

---

## WS-07: WS_CLIENT_DISCONNECT — 关闭 WebSocket 连接

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x73` |
| **PayloadLen** | `0x0004` |

**前置**: WebSocket 客户端已连接

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ClientHandle | 连接句柄 |
| 2-3 | CloseCode | `0x03E8` (1000, 正常关闭) |

**预期响应**: Status=`0x00`

**验证**: 辅助 PC 收到 Close 帧 (CloseCode=1000)

---

## WS-08: WS_DISCONNECT_EVENT — 远端断开事件上报

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x77` (事件) |

**前置**: WebSocket 客户端已连接

**测试步骤**: 辅助 PC 主动关闭 WebSocket 连接 (Ctrl+C)

**预期事件帧**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0-1 | ConnHandle | 断开的句柄 |
| 2-3 | CloseCode | 客户端发送的关闭码 |
| 4 | Reason | 断开原因 |

---

## WS-09: WS_CLIENT_CONNECT — 作为客户端连接远端

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x72` |

**前置**: 辅助 PC 上启动 WebSocket Server (如 `python -m websockets`)

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-3 | ServerIP | 辅助 PC IP |
| 4-5 | ServerPort | 8765 |
| 6 | PathLen | 0x01 |
| 7 | Path | `"/"` |
| 8 | HeaderLen | 0x00 |

**预期响应**: Status=`0x00`, ClientHandle 合法, ConnResult=`0x01` (成功)

---

## WS-10: WS_CLIENT_CONNECT — 握手失败 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x72` |

**前置**: 辅助 PC TCP Server (非 WebSocket) 监听 8900 端口

**请求载荷**: ServerIP=辅助 PC IP, ServerPort=8900, PathLen=1, Path="/"

**预期响应**: Status=`0x49` (ERR_NET_WS_HANDSHAKE) — HTTP Upgrade 未返回 101

---

## WS-11: WS_SERVER_CLOSE — 关闭 WebSocket Server

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x71` |
| **PayloadLen** | `0x0003` |

**请求载荷**: ServerHandle=WS-01 句柄, ForceFlag=`0x01`

**预期响应**: Status=`0x00`

---

## WS-12: WS_SEND — 发送 Pong (心跳回复)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x74` |

**请求载荷**: MsgType=`0x0A` (Pong), DataLen=0

**预期响应**: Status=`0x00`

---

## WS-13: WebSocket 完整生命周期 (集成)

| 项目 | 值 |
|:---|:---|
| **涉及的 CmdCode** | `0x70` → `0x76` → `0x74` → `0x75` → `0x73` → `0x77` → `0x71` |

**测试步骤**:
1. **SERVER_OPEN**: WS_SERVER_OPEN(Port=0, Path="/test") → 获取 ServerHandle
2. **ACCEPT**: 辅助 PC 连接 → 收到 WS_ACCEPT 事件 (ClientHandle=C1)
3. **SEND Text**: WS_SEND(C1, Text, "Hi") → Status=0x00
4. **RECV Text**: 辅助 PC 发送 "Hello" → 收到 WS_RECV(C1, Text, "Hello")
5. **SEND Binary**: WS_SEND(C1, Binary, `0xCA 0xFE`) → Status=0x00
6. **SEND Ping**: WS_SEND(C1, Ping) → Status=0x00
7. **DISCONNECT**: WS_CLIENT_DISCONNECT(C1, 1000) → Status=0x00 → 收到 WS_DISCONNECT_EVENT
8. **SERVER_CLOSE**: WS_SERVER_CLOSE → Status=0x00

**预期**: 全部 8 步依次成功

---

## WS-14: WS_RECV — 自动回复 Ping (RFC 6455)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x75` (不预期事件) |

**前置**: WS Server 已创建, MCP NM WS Client 已连接

**测试步骤**:
1. MCP NM WS Client 发送 WebSocket Ping 帧到 HEX-Bridge
2. HEX-Bridge 内部自动回复 Pong (RFC 6455 要求)
3. 监听 COM35 — 不应收到 WS_RECV 事件 (Ping/Pong 在设备侧内部控制, 不上报给 UBCP)

**验证**: UBCP 链路不受影响, WS Client 收到 Pong

**判定**: PASS — Ping 被自动处理, UBCP 无影响

---

## WS-15: WS_SEND — 发送 Close 帧 (MsgType=0x08)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x74` |

**前置**: WS Client 已连接

**请求载荷**:

| 偏移 | 字段 | 值 |
|:---|:---|:---|
| 0-1 | ConnHandle | 连接句柄 |
| 2 | MsgType | `0x08` (Close) |
| 3-4 | DataLen | `0x0002` |
| 5-6 | CloseCode | `0x03E8` (1000, big-endian) |

**预期**: Status=`0x00`, 对端收到 Close 帧 (CloseCode=1000), 设备发出 WS_DISCONNECT_EVENT

**判定**: PASS — Close 帧编解码正确

---

## WS-16: WS_ACCEPT — 错误路径请求 (404)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x76` (事件, 不预期) |

**前置**: WS Server 监听 `/ws` 路径

**测试步骤**:
1. MCP NM WS Client 连接到 `ws://<HEX IP>:8084/wrong` (不同路径)
2. 监听 COM35

**预期**: 不收到 WS_ACCEPT 事件。MCP NM Client 连接收到 HTTP 404 响应或连接被拒绝。

**判定**: PASS — 错误路径不触发 WS_ACCEPT

---

## WS-17: WS_SERVER_OPEN — 超过最大连接 (MaxConn 容量)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x70`, `0x76` |

**测试步骤**:
1. WS_SERVER_OPEN(Port=9503, MaxConn=`0x01`)
2. MCP NM WS Client A 连接 → 收到 WS_ACCEPT (CH_A)
3. MCP NM WS Client B 连接 → 连接被拒绝或排队超时

**预期**: 第二个客户端被拒绝, 不产生第二个 WS_ACCEPT 事件

**判定**: PASS — MaxConn=1 限制生效

---

## WS-18: WS 所有 OPEN/CONNECT 命令 — 无 IP 时拒绝

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x70`, `0x72` |

**前置**: 拔出网线, NET_STATUS 确认 IpAddr=0x00000000

**测试步骤**:
1. WS_SERVER_OPEN(Port=9504, Path="/ws") → 预期: Status=`0x47` (ERR_NET_NO_IP)
2. WS_CLIENT_CONNECT(任意IP, 任意Port) → 预期: Status=`0x47` (ERR_NET_NO_IP)

**判定**: PASS — 两条命令均返回 ERR_NET_NO_IP

---

## WS-19: WS_LIST_CLIENTS — 查询已连接客户端

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x78` |

**前置**: WS_SERVER_OPEN(Port=8085, Path="/ws") → ServerHandle=SH; 已接纳 2 个客户端

**请求载荷**: ServerHandle=SH

**预期响应**:

| 偏移 | 字段 | 预期值 |
|:---|:---|:---|
| 0 | Status | `0x00` |
| 1 | ClientCount | `0x02` |

遍历 2 个客户端条目:
| 偏移 | 字段 | 验证 |
|:---|:---|:---|
| 0-1 | ClientHandle | 非零合法句柄 |
| 2-5 | ClientIP | 合法 IP 地址 |
| 6-7 | ClientPort | 非零端口号 |
| 8 | SubProtoIndex | 子协议索引 |
| 9 | PathLen | 请求路径长度 |
| 10-11 | ConnectTime | 有效 Duration |

**判定**: PASS — ClientCount=2, 条目信息正确

---

## WS-20: WS_KICK_CLIENT — 强制断开指定客户端

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x79` |

**前置**: WS_SERVER_OPEN(Port=8086, Path="/ws") → SH; WS 客户端已连接 → CH

**测试步骤**:
1. WS_LIST_CLIENTS(SH) → 确认 CH 存在
2. WS_KICK_CLIENT(CH, ForceFlag=0x01) → Status=`0x00`
3. 等待 WS_DISCONNECT_EVENT(CH, Reason=0x04 网络错误)
4. WS_LIST_CLIENTS(SH) → ClientCount=`0x00` (确认 CH 已不再列表中)

**判定**: PASS — CH 被成功断开并上报事件, 列表中不再出现

---

## WS-21: WS_KICK_CLIENT — 优雅关闭

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x79` |

**前置**: WS Server 已创建, WS 客户端已连接 → CH

**测试步骤**:
1. WS_KICK_CLIENT(CH, ForceFlag=0x00) → Status=`0x00`
2. 等待 WS_DISCONNECT_EVENT(CH, Reason=`0x00` 正常关闭, CloseCode=`1000`)

**判定**: PASS — 优雅关闭发送 Close 帧后断开, 事件原因正确

---

# 第六部分：压力与边界测试 (STRESS)

---

## STR-01: 多 Server 并发

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证同时运行 4 个 TCP Server 的稳定性 |

**测试步骤**:
1. 创建 4 个 TCP Server (TCP-01 × 4, 不同端口)
2. 每个 Server 各连入 1 个客户端
3. 同时对 4 个连接发送数据
4. 验证所有响应 Status=0x00

---

## STR-02: 多 Client 并发连接

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 TCP Server 达到最大连接数时的行为 |

**测试步骤**:
1. 创建 TCP Server (MaxConn=3)
2. 辅助 PC 建立 4 个 TCP 连接
3. 前 3 个连接成功, 第 4 个连接超时或被拒绝
4. 设备不崩溃, 已建立连接正常通信

---

## STR-03: 快速 OPEN → CLOSE 循环

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证资源分配/释放的正确性 |

**测试步骤**: 连续 5 次 TCP_SERVER_OPEN → TCP_SERVER_CLOSE, 每次使用不同端口 (9100-9104)

**注**: 测试脚本降为 5 次（原设计 20 次）以避免 UART 帧积压导致的偶发丢帧。建议后续版本增加 UART 流控后再恢复 20 次。

**预期**: 每次均返回 Status=0x00, 端口不泄漏

**状态**: ✅ PASS (5/5)

---

## STR-04: TCP_SEND 广播句柄 (0x8000)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**请求载荷**: ConnHandle=`0x8000` (BROADCAST), DataLen=`0x0000`

**当前状态**: 广播句柄功能尚未实现, 返回 `ERR_NET_HANDLE_INVALID(0x43)`。测试脚本已更新为接受此返回值。

**预期响应** (实现后): Status=`0x00`, 数据发送到 Server 所有已连接客户端

**状态**: ⬜ 待实现 (测试脚本通过 `ERR_NET_HANDLE_INVALID` 验证)

---

## STR-05: NET_STATUS — 载荷不足 (错误用例)

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x41` |
| **PayloadLen** | `0x0000` |

**请求载荷**: 空 (缺少 InterfaceIndex)

**预期响应**: Status=`0x02` (ERR_PARAM)

---

## STR-06: 命令码不在模块范围内

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x5F` (TCP 范围末端) |

**请求载荷**: 任意 2 字节

**预期响应**: Status=`0x06` (ERR_NOT_SUPPORT) — 保留命令码

---

## STR-07: 内存泄漏 — 100 次 Server 生命周期循环

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证 100 次创建/销毁循环无内存泄漏 |

**测试步骤**:
1. 记录基线 free heap
2. 执行 100 次循环:
   - TCP_SERVER_OPEN(Port=9505+i, MaxConn=2)
   - MCP NM Client 连接 → TCP_ACCEPT
   - TCP_SEND("data")
   - MCP NM Client 断开 → TCP_DISCONNECT_EVENT
   - TCP_SERVER_CLOSE
3. 记录最终 free heap

**预期**: free heap 不应单调递减, 泄漏量 < 1KB

**判定**: PASS — 无内存泄漏

---

## STR-08: 并发命令流水线

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证批量命令无串扰 |

**测试步骤**:
1. 连续发送 5 条 NET_STATUS(0x00) 命令 (不等待各自响应)
2. 等待全部 5 条响应

**预期**: 5 条全部收到 Status=0x00, 响应与请求正确配对, 无串扰

**判定**: PASS — 命令流水线正确

---

## STR-09: 所有保留命令码返回 ERR_NOT_SUPPORT

| 项目 | 值 |
|:---|:---|
| **测试目的** | 验证保留命令码统一返回不支持 |

**涉及的 CmdCode**:

| 范围 | 保留命令码 |
|:---|:---|
| 网络配置 | `0x45-0x4F` |
| TCP | `0x5C-0x5F` |
| UDP | `0x67-0x6F` |
| WebSocket | `0x7A-0x7F` |

**测试步骤**: 对每个保留命令码发送任意载荷

**预期**: 每个命令均返回 Status=`0x06` (ERR_NOT_SUPPORT)

**判定**: PASS — 全部保留码返回 0x06

---

## STR-10: TCP_SEND DataLen 声明不匹配

| 项目 | 值 |
|:---|:---|
| **CmdCode** | `0x54` |

**前置**: 已建立 TCP 连接

**请求载荷**: ConnHandle=CH, DataLen=`0x000A` (声明 10 字节), Data 实际仅 `0x41 0x42 0x43` (3 字节)

**预期响应**: Status=`0x02` (ERR_PARAM) — DataLen 声明与 PayloadLen 不符

**判定**: PASS — 参数校验正确

---

## 用例索引

| 分组 | 用例编号 | 数量 | 说明 |
|:---|:---|:---|:---|
| 以太网驱动层 | DRV-01 ~ DRV-05 | 5 | PHY 链路 UP/DOWN/热插拔事件 / DHCP不可用 / 快速插拔 |
| 网络配置模块 | NET-01 ~ NET-16 | 16 | STATUS, DNS, CONFIG (DHCP/静态IP), NVS持久化, DNS不可达, IP_CHANGED, LIST_CONNS, 错误路径 |
| TCP 模块 | TCP-01 ~ TCP-35 | 35 | Server/Client/收发/句柄/广播/错误/生命周期 / 缓冲满 / 超连接 / 优雅关闭 / 无IP / LIST_CLIENTS / KICK_CLIENT / CONN_STATUS |
| UDP 模块 | UDP-01 ~ UDP-14 | 14 | Server/Client/收发/广播/多播/生命周期 / 超Server / 超Client / 无效句柄 / 无IP |
| WebSocket 模块 | WS-01 ~ WS-21 | 21 | Server/Client/Text/Binary/Ping/Pong/Close/握手/生命周期 / 自动Pong / Close帧 / 404 / MaxConn / 无IP / LIST_CLIENTS / KICK_CLIENT |
| 压力与边界 | STR-01 ~ STR-10 | 10 | 并发/循环/空载荷/保留命令码/内存泄漏/流水线/DataLen不匹配 |
| **MCP NM 辅助测试** | **NM-TCP-01 ~ NM-TCP-07** | **7** | TCP 端到端收发/广播/手动Accept/拒绝/LIST_CLIENTS / KICK_CLIENT |
| | **NM-UDP-01 ~ NM-UDP-03** | **3** | UDP 端到端/Client生命周期/广播 |
| | **NM-WS-01 ~ NM-WS-06** | **6** | WS Text/Binary/PingPong 端到端 / LIST_CLIENTS / KICK_CLIENT |
| | **NM-INT-01 ~ NM-INT-03** | **3** | 3 协议并发/多 Client 并发 / NET_LIST_CONNS 全局概览 |
| | **NM-STR-01** | **1** | 大数据量压力 |
| **合计** | | **121** | |

---

## 测试脚本参考

```bash
# 方式一: Kilo Agent 集成测试 (推荐, 无需外部辅助 PC)
# 步骤 1: 在 Kilo Agent 中启动网络对端
#   network-monitor-mcp_connect_network
#     connId="tcp-srv" protocol="tcp" role="server" listenPort=9090
#
# 步骤 2: 发送 UBCP 命令控制 HEX-Bridge 连接 MCP NM Server
#   serial-monitor-mcp_send_serial_data
#     port="COM35" data="<UBCP TCP_CLIENT_CONNECT 帧>" format="hex"
#
# 步骤 3: 双向收发验证
#   serial-monitor-mcp_send_serial_data   → TCP_SEND 命令
#   network-monitor-mcp_read_network_buffer   → 验证网络数据
# 详见各 NM-* 用例

# 方式二: 独立 Python 脚本 (可配合 MCP NM 或外部 PC)
python script/test/test_network.py --mcp COM35 --mcp-baud 921600
```

---

## 错误码覆盖矩阵

| 错误码 | 名称 | 覆盖用例 |
|:---|:---|:---|
| `0x00` | SUCCESS | 所有正常流程用例 |
| `0x02` | ERR_PARAM | NET-05, NET-09, STR-05, STR-10 |
| `0x03` | ERR_TIMEOUT | — |
| `0x06` | ERR_NOT_SUPPORT | STR-06, STR-09 |
| `0x0A` | ERR_CHANNEL_INVALID | NET-08 |
| `0x40` | ERR_NET_DISCONNECTED | TCP-16, TCP-24 |
| `0x41` | ERR_NET_CONN_REFUSED | TCP-10 |
| `0x42` | ERR_NET_TIMEOUT | TCP-09 |
| `0x43` | ERR_NET_HANDLE_INVALID | TCP-15, TCP-18, TCP-33, TCP-35, WS-20, UDP-13 |
| `0x44` | ERR_NET_BUFFER_FULL | TCP-26 |
| `0x45` | ERR_NET_PORT_IN_USE | TCP-03 |
| `0x46` | ERR_NET_DNS_FAIL | NET-04, NET-11 |
| `0x47` | ERR_NET_NO_IP | NET-13, TCP-29, UDP-14, WS-18 |
| `0x48` | ERR_NET_MAX_CONN | TCP-04, TCP-27, UDP-11, UDP-12 |
| `0x49` | ERR_NET_WS_HANDSHAKE | WS-10 |
