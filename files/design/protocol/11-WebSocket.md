# 11. WebSocket 协议命令 (0x70-0x7F)

## 命令码一览

| 命令码 | 名称 | 方向 | 说明 |
|:---|:---|:---|:---|
| `0x70` | WS_SERVER_OPEN | 请求-响应 | 创建 WebSocket Server |
| `0x71` | WS_SERVER_CLOSE | 请求-响应 | 关闭 WebSocket Server |
| `0x72` | WS_CLIENT_CONNECT | 请求-响应 | WebSocket Client 连接 |
| `0x73` | WS_CLIENT_DISCONNECT | 请求-响应 | WebSocket 断开 |
| `0x74` | WS_SEND | 请求-响应 | 发送数据 |
| `0x75` | WS_RECV | 事件上报 | 接收数据 |
| `0x76` | WS_ACCEPT | 事件上报 | 新 WebSocket 连接 |
| `0x77` | WS_DISCONNECT_EVENT | 事件上报 | 连接断开事件 |
| `0x78` | WS_LIST_CLIENTS | 请求-响应 | 查询 WS Server 下所有已连接客户端 |
| `0x79` | WS_KICK_CLIENT | 请求-响应 | 强制断开指定 WS 客户端连接 |
| `0x7A-0x7F` | — | — | 保留 |

---

## 11.1 WS_SERVER_OPEN (0x70) — 创建 WebSocket Server

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | Port | u16 | 监听端口 (0 = 自动分配) |
| 2 | MaxConn | u8 | 最大连接数 (默认 5) |
| 3 | PathLen | u8 | 路径长度 (L) |
| 4...(4+L-1) | Path | str(L) | 路径字符串 (如 "/ws") |
| (4+L) | SubProtoLen | u8 | 子协议列表长度 (S, 0 = 无子协议) |
| (5+L)...(5+L+S-1) | SubProtocol | str(S) | 子协议列表 (逗号分隔) |

> **v1.0 修正**：可选字段使用明确的长度前缀，消除了"Byte 之后"的歧义。当 SubProtoLen=0 时，子协议字段不存在。

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ServerHandle | u16 | 服务器句柄 |
| 3-4 | ActualPort | u16 | 实际端口 |

---

## 11.2 WS_SERVER_CLOSE (0x71) — 关闭 WebSocket Server

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | 服务器句柄 |
| 2 | ForceFlag | u8 | 0 = 等待所有连接关闭, 1 = 立即关闭 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 11.3 WS_CLIENT_CONNECT (0x72) — WebSocket Client 连接

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-3 | ServerIP | u32 | 服务器 IP 地址 |
| 4-5 | ServerPort | u16 | 服务器端口 |
| 6 | PathLen | u8 | 路径长度 (L) |
| 7...(7+L-1) | Path | str(L) | 路径字符串 |
| (7+L) | HeaderLen | u8 | 额外 HTTP 请求头长度 (H, 0 = 无额外头) |
| (8+L)...(8+L+H-1) | Headers | str(H) | 请求头 (Key:Value\r\n 格式) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ClientHandle | u16 | 客户端句柄 |
| 3 | ConnResult | u8 | 连接结果 (0 = 失败, 1 = 成功) |

---

## 11.4 WS_CLIENT_DISCONNECT (0x73) — WebSocket 断开

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 客户端句柄 |
| 2-3 | CloseCode | u16 | WebSocket 关闭码 |

### WebSocket 关闭码

| 值 | 含义 |
|:---|:---|
| 1000 | 正常关闭 |
| 1001 | 终端离开 |
| 1002 | 协议错误 |
| 1003 | 不支持的数据类型 |
| 1006 | 异常关闭（无关闭帧） |
| 1008 | 策略违规 |
| 1011 | 服务器内部错误 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 11.5 WS_SEND (0x74) — 发送 WebSocket 数据

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 连接句柄 |
| 2 | MsgType | u8 | 消息类型 |
| 3-4 | DataLen | u16 | 数据长度 (N) |
| 5... | Data | u8[N] | 发送数据 |

### MsgType 定义

| 值 | 类型 | 说明 |
|:---|:---|:---|
| 0x01 | Text | 文本消息 (UTF-8) |
| 0x02 | Binary | 二进制消息 |
| 0x09 | Ping | Ping 帧 |
| 0x0A | Pong | Pong 帧 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ActualLen | u16 | 实际发送字节数 |

---

## 11.6 WS_RECV (0x75) — 接收 WebSocket 数据 (事件上报)

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 连接句柄 |
| 2 | MsgType | u8 | 消息类型 (同 11.5 节) |
| 3-4 | DataLen | u16 | 数据长度 (N) |
| 5... | Data | u8[N] | 接收数据 |

---

## 11.7 WS_ACCEPT (0x76) — 新 WebSocket 连接 (事件上报)

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | 服务器句柄 |
| 2-3 | ClientHandle | u16 | 客户端句柄 |
| 4-7 | ClientIP | u32 | 客户端 IP 地址 |
| 8-9 | ClientPort | u16 | 客户端端口 |
| 10 | SubProtoIndex | u8 | 协商的子协议索引 (0 = 未指定) |
| 11 | PathLen | u8 | 请求路径长度 (L) |
| 12... | Path | str(L) | 请求路径 |

---

## 11.8 WS_DISCONNECT_EVENT (0x77) — 连接断开事件 (事件上报)

当 WebSocket 连接断开时（远端关闭、网络错误等），设备主动上报。

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ConnHandle | u16 | 断开的连接句柄 |
| 2-3 | CloseCode | u16 | WebSocket 关闭码 |
| 4 | Reason | u8 | 断开原因 |

### Reason 定义

| 值 | 原因 | 说明 |
|:---|:---|:---|
| 0x00 | 正常关闭 | 收到对端的关闭帧 |
| 0x01 | 异常关闭 | 未收到关闭帧就断开 |
| 0x02 | 超时 | 连接超时 |
| 0x03 | 协议错误 | WebSocket 协议违规 |
| 0x04 | 网络错误 | 底层 TCP 连接断开 |

---

## 11.9 WS_LIST_CLIENTS (0x78) — 查询已连接客户端

查询指定 WebSocket Server 下所有当前已连接的客户端列表。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | WebSocket 服务器句柄 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | ClientCount | u8 | 已连接客户端数量 (N) |
| 2... | Clients | — | N 个客户端条目 (每个 12 字节) |

### 每个客户端条目的结构 (12 字节)

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 客户端句柄 |
| 2-5 | ClientIP | u32 | 客户端 IP 地址 |
| 6-7 | ClientPort | u16 | 客户端端口 |
| 8 | SubProtoIndex | u8 | 协商的子协议索引 (0 = 未指定) |
| 9 | PathLen | u8 | 请求路径长度 (L) |
| 10-11 | ConnectTime | u16 | 连接建立时长 (秒, 设备启动起算) |

> **设计意图**: 等效于 MCP Network Monitor 的 `get_network_clients`。WS 条目相比 TCP 多了 SubProtoIndex 字段, 便于区分不同子协议的客户端。

---

## 11.10 WS_KICK_CLIENT (0x79) — 强制断开指定客户端

强制断开指定 WebSocket 客户端连接。

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 要断开的目标客户端句柄 |
| 2 | ForceFlag | u8 | 0 = 发送 Close 帧后断开, 1 = 直接关闭底层 TCP |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

### 错误场景

| 场景 | 错误码 |
|:---|:---|
| ClientHandle 无效或已断开 | `ERR_NET_HANDLE_INVALID (0x43)` |

> **设计意图**: 等效于 MCP Network Monitor 的 `disconnect_network_client`。断开后设备自动发送 `WS_DISCONNECT_EVENT (0x77)` 事件帧通知主机。