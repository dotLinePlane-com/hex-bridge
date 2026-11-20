# 02. 网络功能

> **状态**: Wi-Fi STA，使用系统能力位 12 发现
> **命令码范围**: `0x40-0x4F` / `0x50-0x5F` / `0x60-0x6F` / `0x70-0x7F`

---

## 1. 功能描述

通过 ESP32 内置 Wi-Fi STA 加入局域网，提供 TCP、UDP、WebSocket 的 Server/Client 模式。

---

## 2. 子功能

| 子功能 | 命令码范围 | 说明 |
|:---|:---|:---|
| 网络配置 | `0x40-0x4F` | DHCP/静态IP 配置、链路状态查询与事件上报、DNS 解析、全局连接概览 |
| TCP | `0x50-0x5F` | TCP Server/Client 创建与关闭、数据收发、客户端管理（查询/踢出）、连接状态查询 |
| UDP | `0x60-0x6F` | UDP Server/Client 创建与删除、数据收发（含广播/多播） |
| WebSocket | `0x70-0x7F` | WebSocket Server/Client 创建与关闭、RFC 6455 帧收发、客户端管理 |

> 各子功能的命令码详情、载荷格式、错误码定义见对应协议文档。

---

## 3. 硬件依赖

- ESP32 内置 2.4 GHz Wi-Fi；UART1 提供离线配网。

---

## 4. 设计文档索引

| 层级 | 文档 | 路径 |
|:---|:---|:---|
| 协议定义 | 网络配置协议 | `../protocol/08-Network.md` |
| | TCP 协议 | `../protocol/09-TCP.md` |
| | UDP 协议 | `../protocol/10-UDP.md` |
| | WebSocket 协议 | `../protocol/11-WebSocket.md` |
| | 网络错误码 | `../protocol/14-ErrorCode.md` |
| 固件设计 | Wi-Fi STA + 网络模块实现设计 | `../firmware/06-WiFi-STA.md` |
| 测试 | 网络模块测试用例 | `../test/09-Network-Tests.md` |

---

## 5. 对齐说明

HEX-Bridge 网络命令集与 **MCP Network Monitor** 工具链 (`network-monitor-mcp_*`) 的能力对比：

| MCP NM 功能 | HEX-Bridge 等效命令 | 状态 |
|:---|:---|:---|
| `connect_network` (TCP/UDP/WS) | `*_SERVER_OPEN`, `*_CLIENT_CONNECT/CREATE` | ✅ |
| `disconnect_network` | `*_SERVER_CLOSE`, `*_CLIENT_DISCONNECT/DELETE` | ✅ |
| `send_network_data` | `*_SEND` | ✅ |
| `read_network_buffer` | `*_RECV` (事件上报) | ✅ |
| `get_network_clients` | `*_LIST_CLIENTS` | ✅ |
| `disconnect_network_client` | `*_KICK_CLIENT` | ✅ |
| `get_network_status` | `TCP_CONN_STATUS`, `NET_STATUS` | ✅ |
| `list_network_connections` | `NET_LIST_CONNS` | ✅ |
| `close_all_connections` | `NET_CLOSE_ALL` | ✅ |
| `update_network_client_label` | — | 未支持 |
| `autoReconnect` | — | 未支持 |

HEX-Bridge 超集能力 (MCP NM 不具备): TCP 手动接受模式、远程断开事件上报、DNS 设备侧解析、链路状态事件、NET_CLOSE_ALL 一键关闭所有连接。
