# 4. UART 扩展模块设计

## 4.1 概述

UART 扩展模块管理 UART2 (扩展口)，实现 UBCP 协议中的 UART 命令组 (0xA0-0xAF)。

### 硬件配置

| 参数 | 值 |
|:---|:---|
| UART 端口 | UART2 |
| TX 引脚 | GPIO 2 (Strapping 引脚) |
| RX 引脚 | GPIO 35 (GPI, 外接 10kΩ 上拉) |
| 默认波特率 | 115,200 bps |
| RX 缓冲区 | 2048 字节 |
| TX 缓冲区 | 1024 字节 |

## 4.2 命令实现状态

| 命令码 | 名称 | 状态 |
|:---|:---|:---|
| `0xA0` | UART_OPEN | ✅ 完整实现 |
| `0xA1` | UART_CLOSE | ✅ 完整实现 |
| `0xA2` | UART_CONFIG | ✅ 完整实现 |
| `0xA3` | UART_SEND | ✅ 完整实现 |
| `0xA4` | UART_RECV | ✅ 事件上报（4 种接收模式） |
| `0xA5` | UART_SET_BREAK | ✅ 完整实现 |
| `0xA6` | UART_STATUS | ✅ 完整实现 |
| `0xA7` | UART_FLUSH | ✅ 完整实现 |

## 4.3 接收模式

### 被动上报模式 (RxMode = 0x00)

收到数据立即上报。每次从 UART2 读取到的数据（最多 512 字节批次）打包为一个 UART_RECV 事件帧。

### 行模式 (RxMode = 0x01)

缓存数据直到遇到 `\n`（支持 `\r\n`），整行上报。行缓冲区 1024 字节，超长自动截断上报。

### 定长模式 (RxMode = 0x02)

累积数据直到达到 `RxThreshold` 字节后上报。适用于固定长度协议。

### 超时模式 (RxMode = 0x03)

收到首字节后，如果 `RxTimeout` 毫秒内无新数据则上报。适用于不定长消息（如 Modbus RTU）。

## 4.4 生命周期

```
上位机                                   设备 (UART 模块)

UART_OPEN(RxMode) ──────────────────→   安装 UART2 驱动
                                         创建 RX 接收任务
                   ←────────────────── 响应(Status, BufSize)

UART_CONFIG(波特率, 8N1) ────────────→   配置 UART2 参数
                   ←────────────────── 响应(ActualBaud)

UART_SEND("Hello") ─────────────────→   uart_write_bytes()
                   ←────────────────── 响应(ActualLen)

                   ←────────────────── UART_RECV 事件上报
                   ←────────────────── UART_RECV 事件上报
                                        (RX 任务持续上报)

UART_STATUS() ───────────────────────→   查询状态
                   ←────────────────── 响应(波特率, 计数器...)

UART_CLOSE() ────────────────────────→   停止 RX 任务
                                         卸载 UART2 驱动
                   ←────────────────── 响应(Status)
```

## 4.5 源文件

| 文件 | 说明 |
|:---|:---|
| `modules/mod_uart.h` | 接口声明 |
| `modules/mod_uart.c` | 完整实现（~450 行） |
