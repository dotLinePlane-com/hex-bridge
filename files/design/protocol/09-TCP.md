# 9. TCP 协议命令 (0x50-0x5F)

## 命令码一览

| 命令码 | 名称 | 方向 | 说明 |
|:---|:---|:---|:---|
| `0x50` | TCP_SERVER_OPEN | 请求-响应 | 创建 TCP Server |
| `0x51` | TCP_SERVER_CLOSE | 请求-响应 | 关闭 TCP Server |
| `0x52` | TCP_CLIENT_CONNECT | 请求-响应 | TCP Client 连接 |
| `0x53` | TCP_CLIENT_DISCONNECT | 请求-响应 | 断开 TCP 连接 |
| `0x54` | TCP_SEND | 请求-响应 | 发送 TCP 数据 |
| `0x55` | TCP_RECV | 事件上报 | 接收 TCP 数据 |
| `0x56` | TCP_ACCEPT | 事件上报/请求 | 新客户端连接通知 |
| `0x57` | TCP_CLOSE | 请求-响应 | 通用关闭连接 |
| `0x58` | TCP_DISCONNECT_EVENT | 事件上报 | 远端断开连接事件 |
| `0x59` | TCP_LIST_CLIENTS | 请求-响应 | 查询 Server 下所有已连接客户端 |
| `0x5A` | TCP_KICK_CLIENT | 请求-响应 | 强制断开指定客户端连接 |
| `0x5B` | TCP_CONN_STATUS | 请求-响应 | 查询单个连接状态和收发统计 |
| `0x5C-0x5F` | — | — | 保留 |

---

## 句柄管理

| 范围 | 用途 |
|:---|:---|
| 0x0001-0x7FFF | Server 句柄（由设备分配） |
| 0x8001-0xFFFE | Client/连接 句柄（由设备分配） |
| 0x0000 | 无效句柄 |
| 0x8000 | 广播句柄（表示所有连接） |
| 0xFFFF | 保留 |

---

## 9.1 TCP_SERVER_OPEN (0x50) — 创建 TCP Server

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | Port | u16 | 监听端口 (0 = 自动分配) |
| 2 | MaxConn | u8 | 最大连接数 (默认 5) |
| 3 | AcceptMode | u8 | 连接接受模式 |
| 4 | KeepAlive | u8 | 保活时间 (秒, 0 = 禁用) |

### AcceptMode 定义

| 值 | 模式 | 说明 |
|:---|:---|:---|
| 0x00 | 手动接受 | 主机收到 TCP_ACCEPT 后需确认 |
| 0x01 | 自动接受 | 设备自动接受新连接 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ServerHandle | u16 | 服务器句柄 |
| 3-4 | ActualPort | u16 | 实际绑定端口 |

---

## 9.2 TCP_SERVER_CLOSE (0x51) — 关闭 TCP Server

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | 服务器句柄 |
| 2 | ForceClose | u8 | 0 = 等待连接关闭, 1 = 立即关闭 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 9.3 TCP_CLIENT_CONNECT (0x52) — TCP Client 连接

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-3 | DestIP | u32 | 目标 IP 地址 |
| 4-5 | DestPort | u16 | 目标端口 |
| 6 | TimeoutSec | u8 | 连接超时时间 (秒, 默认 5) |
| 7 | KeepAlive | u8 | 保活时间 (秒, 0 = 禁用) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ConnHandle | u16 | 连接句柄 |
| 3-6 | LocalIP | u32 | 本地 IP 地址 |
| 7-8 | LocalPort | u16 | 本地端口 |

---

## 9.4 TCP_CLIENT_DISCONNECT (0x53) — 断开 TCP 连接

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 连接句柄 |
| 2 | Method | u8 | 断开方式 (0 = 正常 FIN, 1 = 强制 RST) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 9.5 TCP_SEND (0x54) — 发送 TCP 数据

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 连接句柄 |
| 2-3 | DataLen | u16 | 数据长度 (N) |
| 4... | Data | u8[N] | 发送数据 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ActualLen | u16 | 实际发送字节数 |

---

## 9.6 TCP_RECV (0x55) — 接收 TCP 数据 (事件上报)

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 连接句柄 |
| 2-3 | DataLen | u16 | 数据长度 (N) |
| 4... | Data | u8[N] | 接收数据 |

---

## 9.7 TCP_ACCEPT (0x56) — 新客户端连接

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | 服务器句柄 |
| 2-3 | ClientHandle | u16 | 客户端句柄 (设备分配) |
| 4-7 | ClientIP | u32 | 客户端 IP 地址 |
| 8-9 | ClientPort | u16 | 客户端端口 |

### 手动接受确认 (主机 → 设备)

仅当 TCP_SERVER_OPEN 中 AcceptMode = 0x00（手动接受）时需要发送。

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 客户端句柄 |
| 2 | Decision | u8 | 0 = 接受, 1 = 拒绝 |

---

## 9.8 TCP_CLOSE (0x57) — 通用关闭连接

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | Handle | u16 | 句柄 |
| 2 | HandleType | u8 | 0 = 连接句柄, 1 = 服务器句柄 |
| 3 | ForceFlag | u8 | 0 = 优雅关闭, 1 = 强制关闭 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 9.9 TCP_DISCONNECT_EVENT (0x58) — 远端断开连接 (事件上报)

当远端主动断开 TCP 连接时，设备上报此事件。

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 断开的连接句柄 |
| 2 | Reason | u8 | 断开原因 |
| 3-6 | RemoteIP | u32 | 远端 IP 地址 |
| 7-8 | RemotePort | u16 | 远端端口 |

### Reason 定义

| 值 | 原因 | 说明 |
|:---|:---|:---|
| 0x00 | 正常关闭 | 远端发送 FIN |
| 0x01 | 连接重置 | 远端发送 RST |
| 0x02 | 超时 | 连接超时断开 |
| 0x03 | 网络错误 | 网络不可达等 |

---

## 9.10 TCP_LIST_CLIENTS (0x59) — 查询已连接客户端

查询指定 TCP Server 下所有当前已连接的客户端列表。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | 服务器句柄 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | ClientCount | u8 | 已连接客户端数量 (N) |
| 2... | Clients | — | N 个客户端条目 (每个 10 字节) |

### 每个客户端条目的结构 (10 字节)

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 客户端句柄 |
| 2-5 | ClientIP | u32 | 客户端 IP 地址 |
| 6-7 | ClientPort | u16 | 客户端端口 |
| 8-9 | ConnectTime | u16 | 连接建立时长 (秒, 设备启动起算) |

> **设计意图**: 等效于 MCP Network Monitor 的 `get_network_clients`, 提供 Server 端已连接客户端的完整快照。ConnectTime 为 u16 (最大 65535 秒 ≈ 18 小时), 满足大多数会话跟踪需求。

---

## 9.11 TCP_KICK_CLIENT (0x5A) — 强制断开指定客户端

强制断开指定客户端连接, 无需事先知道该客户端属于哪个 Server。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 要断开的目标客户端句柄 |
| 2 | ForceFlag | u8 | 0 = 优雅关闭 (FIN), 1 = 强制关闭 (RST) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

### 错误场景

| 场景 | 错误码 |
|:---|:---|
| ClientHandle 无效或已断开 | `ERR_NET_HANDLE_INVALID (0x43)` |

> **设计意图**: 等效于 MCP Network Monitor 的 `disconnect_network_client`。断开后设备自动发送 `TCP_DISCONNECT_EVENT (0x58)` 事件帧通知主机。

---

## 9.12 TCP_CONN_STATUS (0x5B) — 查询单个连接状态

查询指定 TCP 连接的实时状态和收发字节统计。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 连接句柄 (Server 子连接或 Client 连接) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | ConnState | u8 | 连接状态 |
| 2-5 | TxBytes | u32 | 累计发送字节数 |
| 6-9 | RxBytes | u32 | 累计接收字节数 |
| 10-13 | RemoteIP | u32 | 对端 IP 地址 |
| 14-15 | RemotePort | u16 | 对端端口 |
| 16-17 | LocalPort | u16 | 本地端口 |
| 18-21 | ConnectTime | u32 | 连接建立时长 (秒) |

### ConnState 定义

| 值 | 状态 | 说明 |
|:---|:---|:---|
| `0x00` | ESTABLISHED | 连接正常 |
| `0x01` | CLOSING | 正在关闭中 (已发 FIN, 等待对端确认) |
| `0x02` | CLOSED | 已关闭 (等待清理) |

> **设计意图**: 等效于 MCP Network Monitor 的 `get_network_status`。TxBytes / RxBytes 为设备侧套接字层的累计统计, 用于带宽监控和故障诊断。