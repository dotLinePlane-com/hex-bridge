# HEX-Bridge 统一二进制通信协议 (UBCP) v2.0

> **Unified Binary Communication Protocol** — 多功能硬件接口扩展设备通信协议规范

---

## 项目简介

本协议定义了 HEX-Bridge 多功能接口扩展设备（支持 CAN、SPI、I2C、UART、网口 TCP/UDP/WebSocket、GPIO 等）与上位机（MCP Server）之间的统一二进制通信协议。

### 与 v1.0 的主要变更

| 变更项 | v1.0 | v2.0 |
|:---|:---|:---|
| 帧头大小 | 8 字节（结构歧义） | 10 字节（明确定义） |
| 序列号 | 无 | 2 字节，支持请求-响应匹配 |
| CRC16 | 未规范 | CRC-16/CCITT-FALSE，明确计算范围 |
| 转义规则 | 仅说载荷 | SOF/EOF 之间全部转义 |
| 字节序 | 隐式大端 | 显式声明大端序 |
| UART 支持 | 无 | 新增 0xA0-0xAF 命令组 |
| CAN FD | 不支持 | 支持（DLC 0-64） |
| IPv6 | 声明支持但未实现 | 明确标注为预留 |
| 错误码 | 16 个 | 扩展至分模块错误码 |
| 流控 | 无 | 新增流控命令 |
| GPIO 批量操作 | 无 | 新增掩码读写 |
| 连接事件 | 无 | TCP/WS 断开事件、网络链路事件 |
| OTA 固件升级 | 无 | 新增 0xB0-0xBF 命令组，支持分块传输和回滚 |

---

## 文档结构

| 文件 | 内容 | 命令码范围 |
|:---|:---|:---|
| [01-Introduction.md](01-Introduction.md) | 协议概述、设计目标、通信模型 | — |
| [02-Frame.md](02-Frame.md) | 帧结构、转义、CRC、流控 | — |
| [03-System.md](03-System.md) | 系统管理命令 | 0x00-0x0F |
| [04-CAN.md](04-CAN.md) | CAN / CAN FD 接口命令 | 0x10-0x1F |
| [05-SPI.md](05-SPI.md) | SPI 接口命令 | 0x20-0x2F |
| [06-I2C.md](06-I2C.md) | I2C 接口命令 | 0x30-0x3F |
| [07-UART.md](07-UART.md) | UART 接口命令 | 0xA0-0xAF |
| [08-Network.md](08-Network.md) | 网络基础配置 | 0x40-0x4F |
| [09-TCP.md](09-TCP.md) | TCP 协议命令 | 0x50-0x5F |
| [10-UDP.md](10-UDP.md) | UDP 协议命令 | 0x60-0x6F |
| [11-WebSocket.md](11-WebSocket.md) | WebSocket 协议命令 | 0x70-0x7F |
| [12-GPIO.md](12-GPIO.md) | GPIO 接口命令 | 0x80-0x8F |
| [13-Bulk.md](13-Bulk.md) | 批量传输模式 | 0x90-0x9F |
| [14-ErrorCode.md](14-ErrorCode.md) | 错误码速查表 | — |
| [15-Appendix.md](15-Appendix.md) | 附录：MCP 映射、实现阶段 | — |
| [16-OTA.md](16-OTA.md) | OTA 固件升级命令 | 0xB0-0xBF |

---

## 约定

- **字节序**：本协议所有多字节字段均使用 **大端序（Big-Endian / Network Byte Order）**
- **编号**：所有索引从 0 开始，除非特别说明
- **标记**：`[可选]` 表示该字段可能不存在，取决于标志位
- **版本**：当前协议版本号 `0x02`

---

## 许可证

本协议文档版权归 HEX-Bridge 项目所有。
