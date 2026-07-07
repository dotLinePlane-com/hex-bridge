# 8. 网络基础配置 (0x40-0x4F)

## 命令码一览

| 命令码 | 名称 | 方向 | 说明 |
|:---|:---|:---|:---|
| `0x40` | NET_CONFIG | 请求-响应 | 网络配置 |
| `0x41` | NET_STATUS | 请求-响应 | 网络状态查询 |
| `0x42` | NET_DNS | 请求-响应 | DNS 域名解析 |
| `0x43` | NET_LINK_EVENT | 事件上报 | 网络链路状态变更 |
| `0x44-0x4F` | — | — | 保留 |

> **关于 IPv6**：当前版本所有 IP 地址字段均为 4 字节（IPv4）。IPv6 支持列为未来扩展计划，届时 IP 地址字段将改为可变长度（由地址族字段决定 4B 或 16B）。

---

## 8.1 NET_CONFIG (0x40) — 网络配置

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | InterfaceIndex | u8 | 网络接口索引 |
| 1 | ConfigType | u8 | 配置类型 |
| 2-5 | IpAddr | u32 | IP 地址 (当 ConfigType=0x01) |
| 6-9 | SubnetMask | u32 | 子网掩码 (当 ConfigType=0x01) |
| 10-13 | Gateway | u32 | 网关地址 (当 ConfigType=0x01) |
| 14-17 | DNS1 | u32 | DNS 服务器 1 (当 ConfigType=0x01) |
| 18-21 | DNS2 | u32 | DNS 服务器 2 (当 ConfigType=0x01) |

### InterfaceIndex 定义

| 值 | 接口 |
|:---|:---|
| 0x00 | ETH0 (以太网口 0) |
| 0x01 | ETH1 (以太网口 1, 如果有) |

### ConfigType 定义

| 值 | 含义 | 载荷 |
|:---|:---|:---|
| 0x00 | 启用 DHCP | 仅 InterfaceIndex (1 字节) |
| 0x01 | 设置静态 IP | 完整 22 字节载荷 |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1-4 | ActualIP | u32 | 实际 IP 地址 |
| 5-8 | ActualMask | u32 | 实际子网掩码 |
| 9-12 | ActualGW | u32 | 实际网关 |
| 13-16 | ActualDNS | u32 | 实际 DNS 服务器 |

---

## 8.2 NET_STATUS (0x41) — 网络状态查询

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | InterfaceIndex | u8 | 接口索引 (0xFF = 查询所有接口) |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | IntfCount | u8 | 接口数量 (N) |
| 2... | Interfaces | — | N 个接口状态 (每个 17 字节) |

### 每个接口的状态结构 (17 字节)

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | IntfIndex | u8 | 接口索引 |
| 1 | LinkState | u8 | 链路状态 (0=Down, 1=Up) |
| 2 | ConnState | u8 | 连接状态 (0=未连接, 1=已连接, 2=获取IP中) |
| 3-6 | IpAddr | u32 | IP 地址 |
| 7-10 | SubnetMask | u32 | 子网掩码 |
| 11-16 | MacAddr | u8[6] | MAC 地址 |

---

## 8.3 NET_DNS (0x42) — DNS 域名解析

### 请求

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | NameLen | u8 | 域名长度 (L) |
| 1... | Hostname | str(L) | 域名字符串 (如 "example.com") |

### 响应

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | 状态码 |
| 1 | AddrCount | u8 | 解析到的地址数量 (N, 最多 4 个) |
| 2... | Addresses | u32[N] | 解析到的 IP 地址列表 |

---

## 8.4 NET_LINK_EVENT (0x43) — 网络链路状态变更 (事件上报)

当网线插拔或 DHCP 地址变化时，设备主动上报。

### 设备 → 主机主动上报

Flags: DIR=1, EVT=1

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | IntfIndex | u8 | 接口索引 |
| 1 | EventType | u8 | 事件类型 |
| 2-5 | IpAddr | u32 | 当前 IP 地址 (如果有) |

### EventType 定义

| 值 | 事件 | 说明 |
|:---|:---|:---|
| 0x00 | LINK_DOWN | 网线断开 / 链路丢失 |
| 0x01 | LINK_UP | 网线连接 / 链路建立 |
| 0x02 | IP_ACQUIRED | 获取到 IP 地址 (DHCP 成功) |
| 0x03 | IP_LOST | IP 地址丢失 (DHCP 续期失败) |
| 0x04 | IP_CHANGED | IP 地址发生变化 |
