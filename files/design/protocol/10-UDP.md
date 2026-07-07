# 10. UDP 协议命令 (0x60-0x6F)

## 命令码一览

| 命令码 | 名称 | 方向 | 说明 |
|:---|:---|:---|:---|
| `0x60` | UDP_SERVER_OPEN | 请求-响应 | 创建 UDP Server |
| `0x61` | UDP_SERVER_CLOSE | 请求-响应 | 关闭 UDP Server |
| `0x62` | UDP_CLIENT_CREATE | 请求-响应 | 创建 UDP Client |
| `0x63` | UDP_CLIENT_DELETE | 请求-响应 | 删除 UDP Client |
| `0x64` | UDP_SERVER_SEND | 请求-响应 | 通过 Server 发送数据 |
| `0x65` | UDP_RECV | 事件上报 | 接收 UDP 数据 |
| `0x66` | UDP_CLIENT_SEND | 请求-响应 | 通过 Client 发送数据 |
| `0x67-0x6F` | — | — | 保留 |

> **v1.0 修正**：原 `UDP_SEND (0x64)` 一个命令码承载两种格式，已拆分为 `UDP_SERVER_SEND (0x64)` 和 `UDP_CLIENT_SEND (0x66)` 两个独立命令。

---

## 10.1 UDP_SERVER_OPEN (0x60) — 创建 UDP Server

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | Port | u16 | 本地端口 (0 = 自动分配) |
| 2 | BroadcastMode | u8 | 广播模式 (0 = 禁用, 1 = 启用) |
| 3-6 | MulticastAddr | u32 | 多播组地址 (0 = 不使用多播) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ServerHandle | u16 | 服务器句柄 |
| 3-4 | ActualPort | u16 | 实际绑定端口 |

---

## 10.2 UDP_SERVER_CLOSE (0x61) — 关闭 UDP Server

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | 服务器句柄 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 10.3 UDP_CLIENT_CREATE (0x62) — 创建 UDP Client

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-3 | DefaultDestIP | u32 | 默认目标 IP 地址 |
| 4-5 | DefaultDestPort | u16 | 默认目标端口 |
| 6-7 | LocalPort | u16 | 本地端口 (0 = 自动分配) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ClientHandle | u16 | 客户端句柄 |
| 3-4 | ActualPort | u16 | 本地绑定端口 |

---

## 10.4 UDP_CLIENT_DELETE (0x63) — 删除 UDP Client

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 客户端句柄 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |

---

## 10.5 UDP_SERVER_SEND (0x64) — 通过 Server 发送数据

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ServerHandle | u16 | 服务器句柄 |
| 2-5 | DestIP | u32 | 目标 IP 地址 |
| 6-7 | DestPort | u16 | 目标端口 |
| 8-9 | DataLen | u16 | 数据长度 (N) |
| 10... | Data | u8[N] | 发送数据 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ActualLen | u16 | 实际发送字节数 |

---

## 10.6 UDP_CLIENT_SEND (0x66) — 通过 Client 发送数据

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | ClientHandle | u16 | 客户端句柄 |
| 2 | AddrMode | u8 | 地址模式 |
| 3... | — | — | 载荷根据 AddrMode 的不同为变长结构 (见下) |

### AddrMode 与请求载荷结构

* **AddrMode = 0x00 (使用默认地址)**
  此时 DestIP 和 DestPort 字段被完全省略，以节省高频发包场景下的串口/网络带宽：

  | 偏移 | 字段 | 类型 | 说明 |
  |:---|:---|:---|:---|
  | 3-4 | DataLen | u16 | 数据长度 (N) |
  | 5... | Data | u8[N] | 发送数据 |

* **AddrMode = 0x01 (使用指定地址)**

  | 偏移 | 字段 | 类型 | 说明 |
  |:---|:---|:---|:---|
  | 3-6 | DestIP | u32 | 目标 IP 地址 |
  | 7-8 | DestPort | u16 | 目标端口 |
  | 9-10 | DataLen | u16 | 数据长度 (N) |
  | 11... | Data | u8[N] | 发送数据 |

### AddrMode 定义

| 值 | 含义 | 说明 |
|:---|:---|:---|
| 0x00 | 使用默认地址 | 发送到 UDP_CLIENT_CREATE 时设置的默认目标 |
| 0x01 | 使用指定地址 | 发送到载荷中指定的 DestIP:DestPort |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-2 | ActualLen | u16 | 实际发送字节数 |

---

## 10.7 UDP_RECV (0x65) — 接收 UDP 数据 (事件上报)

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0-1 | Handle | u16 | 接收到数据的句柄 (Server 或 Client) |
| 2-5 | SrcIP | u32 | 数据来源 IP 地址 |
| 6-7 | SrcPort | u16 | 数据来源端口 |
| 8-9 | DataLen | u16 | 数据长度 (N) |
| 10... | Data | u8[N] | 接收数据 |
