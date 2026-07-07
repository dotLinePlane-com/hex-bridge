# 15. 附录

## A. MCP Server 工具映射

| MCP 工具名称 | 命令码 | 功能描述 |
|:---|:---|:---|
| **系统管理** | | |
| `ping` | 0x00 | 检测设备是否在线 |
| `get_info` | 0x01 | 获取设备信息 |
| `get_config` | 0x02 | 读取设备配置 |
| `set_config` | 0x03 | 写入设备配置 |
| `reset` | 0x04 | 复位设备 |
| `flow_control` | 0x05 | 查询/控制流量 |
| **CAN** | | |
| `can_open` / `can_close` | 0x10 / 0x11 | 打开/关闭 CAN 通道 |
| `can_config` | 0x12 | 配置 CAN 波特率（含 FD） |
| `can_send` | 0x13 | 发送 CAN 帧 |
| `can_filter` | 0x15 | 设置 CAN 过滤器 |
| `can_status` | 0x16 | 获取 CAN 状态 |
| **SPI** | | |
| `spi_open` / `spi_close` | 0x20 / 0x21 | 打开/关闭 SPI |
| `spi_config` | 0x22 | 配置 SPI 参数 |
| `spi_transfer` | 0x23 | SPI 全双工传输 |
| `spi_write` / `spi_read` | 0x24 / 0x25 | SPI 只写/只读 |
| `spi_cs_control` | 0x26 | 手动控制 CS |
| **I2C** | | |
| `i2c_open` / `i2c_close` | 0x30 / 0x31 | 打开/关闭 I2C |
| `i2c_config` | 0x32 | 配置 I2C 速度 |
| `i2c_write` / `i2c_read` | 0x33 / 0x34 | I2C 读写 |
| `i2c_write_read` | 0x35 | I2C 组合操作 |
| `i2c_scan` | 0x36 | 扫描 I2C 总线 |
| **UART** | | |
| `uart_open` / `uart_close` | 0xA0 / 0xA1 | 打开/关闭 UART |
| `uart_config` | 0xA2 | 配置 UART 参数 |
| `uart_send` | 0xA3 | 发送 UART 数据 |
| `uart_set_break` | 0xA5 | 发送 Break 信号 |
| `uart_status` | 0xA6 | 获取 UART 状态 |
| `uart_flush` | 0xA7 | 清空缓冲区 |
| **网络** | | |
| `net_config` | 0x40 | 配置网络 IP |
| `net_status` | 0x41 | 查询网络状态 |
| `net_dns` | 0x42 | DNS 域名解析 |
| **TCP** | | |
| `tcp_server_start` / `stop` | 0x50 / 0x51 | TCP Server 操作 |
| `tcp_connect` / `disconnect` | 0x52 / 0x53 | TCP Client 操作 |
| `tcp_send` | 0x54 | TCP 发送数据 |
| `tcp_close` | 0x57 | 通用关闭连接 |
| **UDP** | | |
| `udp_server_start` / `stop` | 0x60 / 0x61 | UDP Server 操作 |
| `udp_client_create` / `delete` | 0x62 / 0x63 | UDP Client 操作 |
| `udp_server_send` | 0x64 | 通过 Server 发送 |
| `udp_client_send` | 0x66 | 通过 Client 发送 |
| **WebSocket** | | |
| `ws_server_start` / `stop` | 0x70 / 0x71 | WebSocket Server 操作 |
| `ws_connect` / `disconnect` | 0x72 / 0x73 | WebSocket Client 操作 |
| `ws_send` | 0x74 | WebSocket 发送数据 |
| **GPIO** | | |
| `gpio_set_dir` | 0x80 | 设置 GPIO 方向 |
| `gpio_write` / `gpio_read` | 0x81 / 0x82 | GPIO 读写 |
| `gpio_set_pull` | 0x83 | 设置上下拉 |
| `gpio_int_enable` | 0x84 | 使能 GPIO 中断 |
| `gpio_write_mask` | 0x86 | 批量设置 GPIO |
| `gpio_read_all` | 0x87 | 批量读取 GPIO |
| **批量传输** | | |
| `bulk_start` / `bulk_stop` | 0x90 / 0x93 | 批量传输控制 |
| **OTA** | | |
| `ota_begin` | 0xB0 | 开始 OTA 升级 |
| `ota_data` | 0xB1 | 发送固件数据块 |
| `ota_end` | 0xB2 | 结束 OTA 并校验 |
| `ota_status` | 0xB3 | 查询 OTA 进度 |
| `ota_rollback` | 0xB4 | 回滚固件 |
| `ota_get_partition` | 0xB5 | 获取分区信息 |

---

## B. 事件上报汇总

以下命令为设备主动上报事件，主机需注册回调处理：

| 事件 | 命令码 | 说明 |
|:---|:---|:---|
| CAN_RECV | 0x14 | 收到 CAN 帧 |
| UART_RECV | 0xA4 | 收到 UART 数据 |
| TCP_RECV | 0x55 | 收到 TCP 数据 |
| TCP_ACCEPT | 0x56 | 新 TCP 客户端连接 |
| TCP_DISCONNECT_EVENT | 0x58 | TCP 远端断开 |
| UDP_RECV | 0x65 | 收到 UDP 数据 |
| WS_RECV | 0x75 | 收到 WebSocket 消息 |
| WS_ACCEPT | 0x76 | 新 WebSocket 连接 |
| WS_DISCONNECT_EVENT | 0x77 | WebSocket 连接断开 |
| GPIO_INT_EVENT | 0x85 | GPIO 中断触发 |
| NET_LINK_EVENT | 0x43 | 网络链路状态变化 |
| FLOW_CONTROL | 0x05 | 流控通知 (XOFF/XON) |
| OTA_PROGRESS | 0xB6 | OTA 升级进度 |

---

## C. 实现优先级与阶段划分

| 阶段 | 模块 | 命令码 | 优先级 | 预计工时 |
|:---|:---|:---|:---|:---|
| **Phase 0** | 帧解析/打包/CRC/转义/序列号 | — | P0 | 3 天 |
| **Phase 1** | PING, GET_INFO, GET_CONFIG, SET_CONFIG, RESET | 0x00-0x04 | P0 | 1 天 |
| **Phase 2** | FLOW_CONTROL | 0x05 | P0 | 1 天 |
| **Phase 3** | CAN 接口全部命令 (含 FD) | 0x10-0x16 | P1 | 3 天 |
| **Phase 4** | UART 接口全部命令 | 0xA0-0xA7 | P1 | 2 天 |
| **Phase 5** | SPI 接口全部命令 (含 CS 控制) | 0x20-0x26 | P2 | 2 天 |
| **Phase 6** | I2C 接口全部命令 | 0x30-0x36 | P2 | 2 天 |
| **Phase 7** | 网络基础配置 (含 DNS, 链路事件) | 0x40-0x43 | P3 | 2 天 |
| **Phase 8** | TCP Server/Client (含断开事件) | 0x50-0x58 | P3 | 3 天 |
| **Phase 9** | UDP Server/Client | 0x60-0x66 | P3 | 2 天 |
| **Phase 10** | WebSocket Server/Client (含断开事件) | 0x70-0x77 | P3 | 3 天 |
| **Phase 11** | GPIO 接口 (含批量操作) | 0x80-0x87 | P4 | 2 天 |
| **Phase 12** | 批量传输模式 (含 ACK/重传) | 0x90-0x93 | P4 | 3 天 |
| **Phase 13** | OTA 固件升级 | 0xB0-0xB6 | P1 | 3 天 |

**总计**：约 32 个工作日

---

## D. v1.0 → v2.0 变更日志

| 编号 | 变更内容 | 影响范围 |
|:---|:---|:---|
| 1 | 帧头从 8 字节扩展为 10 字节（新增 2 字节 SeqNum） | 帧解析器 |
| 2 | 明确 CRC-16/CCITT-FALSE 算法和计算范围 | 帧解析器 |
| 3 | 转义范围扩展到 SOF/EOF 之间所有字节 | 帧解析器 |
| 4 | 填充 0x02 (GET_CONFIG) 和 0x03 (SET_CONFIG) | 系统模块 |
| 5 | 新增 0x05 (FLOW_CONTROL) 流控命令 | 系统模块 |
| 6 | CAN 新增 FD 支持（DLC 0-64, FD 波特率） | CAN 模块 |
| 7 | SPI 新增 0x26 (SPI_CS_CONTROL) 手动 CS | SPI 模块 |
| 8 | I2C 地址改为 u16 (支持 10 位地址)，不再左移 | I2C 模块 |
| 9 | I2C 超时字段从 u8 改为 u16 | I2C 模块 |
| 10 | 新增 UART 模块 (0xA0-0xAF) | 新模块 |
| 11 | 新增 0x42 (NET_DNS) DNS 解析 | 网络模块 |
| 12 | 新增 0x43 (NET_LINK_EVENT) 链路事件 | 网络模块 |
| 13 | 去除 IPv6 声明（标记为未来扩展） | 网络模块 |
| 14 | 新增 0x58 (TCP_DISCONNECT_EVENT) | TCP 模块 |
| 15 | UDP_SEND 拆分为 0x64 和 0x66 两个命令 | UDP 模块 |
| 16 | 新增 0x77 (WS_DISCONNECT_EVENT) | WebSocket 模块 |
| 17 | WebSocket 可选字段改用长度前缀 | WebSocket 模块 |
| 18 | GPIO 新增 0x86 (WRITE_MASK) 和 0x87 (READ_ALL) | GPIO 模块 |
| 19 | 批量传输新增 0x92 (BULK_ACK) 确认和重传机制 | 批量传输 |
| 20 | BULK_DATA 新增 per-frame DataCRC | 批量传输 |
| 21 | 错误码扩展为分模块体系 | 全局 |
| 22 | 时间戳统一使用微秒单位 | 全局 |
| 23 | 显式声明大端序约定 | 全局 |
| 24 | Capabilities 位图扩展（CAN FD, UART） | 系统模块 |
| 25 | 新增 OTA 模块 (0xB0-0xBF)，支持分块传输、SHA-256、双分区、回滚 | 新模块 |
| 26 | Capabilities 位图新增 OTA 支持标志 | 系统模块 |
| 27 | 推荐 Payload 调小（1024/2048字节），规范流式反转义及伪 SOF 过滤机制，免去物理大缓存 | 帧解析器 |
| 28 | CAN_STATUS 响应新增 TxQueueSize 和 RxQueueSize 辅助上位机流控计算 | CAN 模块 |
| 29 | I2C 读写寄存器地址由硬编码 2 字节改为根据 RegAddrLen (0-4 字节) 变长传输，支持多字节寻址 | I2C 模块 |
| 30 | UDP_CLIENT_SEND 在 AddrMode=0x00 时省略目标 IP/Port，降低高频下串口开销 | UDP 模块 |
| 31 | GPIO_INT_EVENT 新增限频防风暴规范（每秒限频 50 次），避免高抖动下系统死锁 | GPIO 模块 |
| 32 | OTA_DATA 引入 ChunkCRC 分块校验，将错误控制在数据块级别，防止整包重传 | OTA 模块 |
