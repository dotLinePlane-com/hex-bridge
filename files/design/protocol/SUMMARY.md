# UBCP v2.0 — 快速参考摘要

## 帧结构速览

```
+-------+-------+-------+-------+--------+---------+----------+-----------+---------+-------+------+
| Byte  |  0-1  |   2   |   3   |  4-5   |    6    |    7     |   8-9     | 10-13   | N...  | Last |
+-------+-------+-------+-------+--------+---------+----------+-----------+---------+-------+------+
| 字段  |  SOF  |  Ver  | Flags | SeqNum | CmdCode | ChanID   | PayloadLen| [Tstamp]| Payload| ...  |
| 值    |AA  55 | 0x02  |       |        |         |          |           | [可选]  |       |      |
+-------+-------+-------+-------+--------+---------+----------+-----------+---------+-------+------+
                                                                                      CRC16  | 0x7E |
```

- **固定头部**：10 字节（Byte 0-9）
- **可选时间戳**：4 字节（Flags Bit 5 = 1 时存在，紧跟头部之后）
- **CRC16**：CRC-16/CCITT-FALSE，计算范围：Version → Payload 末尾（转义前原始数据）
- **转义**：SOF 与 EOF 之间的所有字节均需转义

## 命令码速查

| 范围 | 模块 | 关键命令 |
|:---|:---|:---|
| `0x00-0x0F` | 系统管理 | PING, GET_INFO, GET_CONFIG, SET_CONFIG, RESET, FLOW_CONTROL, GET_TOPOLOGY |
| `0x10-0x1F` | CAN | OPEN, CLOSE, CONFIG, SEND, RECV, FILTER, STATUS |
| `0x20-0x2F` | SPI | OPEN, CLOSE, CONFIG, TRANSFER, WRITE, READ, CS_CONTROL |
| `0x30-0x3F` | I2C | OPEN, CLOSE, CONFIG, WRITE, READ, WRITE_READ, SCAN |
| `0x40-0x4F` | 网络配置 | NET_CONFIG, NET_STATUS, NET_DNS, NET_LINK_EVENT |
| `0x50-0x5F` | TCP | SERVER_OPEN/CLOSE, CLIENT_CONNECT/DISCONNECT, SEND, RECV, ACCEPT, CLOSE, DISCONNECT_EVENT |
| `0x60-0x6F` | UDP | SERVER_OPEN/CLOSE, CLIENT_CREATE/DELETE, SERVER_SEND, CLIENT_SEND, RECV |
| `0x70-0x7F` | WebSocket | SERVER_OPEN/CLOSE, CLIENT_CONNECT/DISCONNECT, SEND, RECV, ACCEPT, DISCONNECT_EVENT |
| `0x80-0x8F` | GPIO | SET_DIR, WRITE, READ, SET_PULL, INT_EN, INT_EVENT, WRITE_MASK, READ_ALL |
| `0x90-0x9F` | 批量传输 | BULK_START, BULK_DATA, BULK_ACK, BULK_STOP |
| `0xA0-0xAF` | UART | OPEN, CLOSE, CONFIG, SEND, RECV, SET_BREAK, STATUS, FLUSH |
| `0xB0-0xBF` | OTA | BEGIN, DATA, END, STATUS, ROLLBACK, GET_PARTITION, PROGRESS |

## 错误码速查

| 范围 | 分类 |
|:---|:---|
| `0x00-0x0F` | 通用错误 |
| `0x10-0x1F` | CAN 错误 |
| `0x20-0x2F` | SPI 错误 |
| `0x30-0x3F` | I2C 错误 |
| `0x40-0x4F` | 网络错误 |
| `0x80-0x8F` | GPIO 错误 |
| `0xA0-0xAF` | UART 错误 |
| `0xB0-0xBF` | OTA 错误 |

## Flags 位定义

| Bit | 名称 | 值 |
|:---|:---|:---|
| 7 | 方向 (DIR) | 0=主机→设备, 1=设备→主机 |
| 6 | 需要ACK (ACK) | 0=不需要, 1=需要 |
| 5 | 包含时间戳 (TS) | 0=无, 1=有 |
| 4 | 异步事件 (EVT) | 0=正常, 1=事件上报 |
| 3 | 分片标志 (FRAG) | 0=完整帧, 1=分片 |
| 2-0 | 保留 | 必须为 0 |
