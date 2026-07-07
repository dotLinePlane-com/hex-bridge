# 3. MCP 传输层设计

## 3.1 概述

MCP 传输层管理 UART1 (GPIO 4 TX / GPIO 34 RX) 与上位机 (MCP Server) 之间的 UBCP 帧收发。

### 硬件配置

| 参数 | 值 |
|:---|:---|
| UART 端口 | UART1 |
| TX 引脚 | GPIO 4 |
| RX 引脚 | GPIO 34 (GPI, 外接 10kΩ 上拉) |
| 波特率 | 5,000,000 bps (5 Mbps) |
| 数据格式 | 8N1 |
| 流控 | 无 |
| 连接方式 | USB 转串口芯片 (如 CH343) |

> **注意**：5 Mbps 要求 USB 转串口芯片支持此速率。CH343 支持最高 6 Mbps，是推荐选择。
> 如需降级，修改 `hex_config.h` 中的 `HEX_MCP_UART_BAUD` 即可。

## 3.2 接收流程（流式帧解析）

```
UART1 RX 中断/DMA
       │
       ▼
uart_read_bytes() ← 批量读取（256 字节缓冲）
       │
       ▼
逐字节送入 ubcp_parser_feed()
       │
       ├── WAIT_SOF_0: 等待 0xAA
       ├── WAIT_SOF_1: 等待 0x55
       └── RECEIVING:
           ├── 在线反转义（0x7D 状态机）
           ├── 在线 CRC16 更新
           ├── 写入逻辑缓冲区
           └── 收到 EOF (0x7E):
               ├── CRC 校验
               ├── 提取帧结构体
               └── msg_bus_dispatch()
```

### 关键设计决策

1. **流式解析，无双倍缓冲**：反转义在线进行，逻辑缓冲区大小 = 最大帧大小
2. **伪 SOF 防范**：RECEIVING 状态下，0xAA 0x55 视为普通数据（协议规范 2.5.4）
3. **错误恢复**：CRC 失败、溢出、转义错误均重置解析器等待下一帧

## 3.3 发送流程

```
模块调用 msg_bus_send_frame()
       │
       ▼
ubcp_frame_build() — 构建线路帧
  ├── SOF (0xAA 0x55)
  ├── Header 转义输出
  ├── Payload 转义输出
  ├── CRC16 转义输出
  └── EOF (0x7E)
       │
       ▼
mcp_transport_send()
  ├── 获取互斥锁
  ├── uart_write_bytes()
  └── 释放互斥锁
```

### 线程安全

发送使用互斥锁 (`s_tx_mutex`) 保护，确保多个模块同时发送事件帧时不会交错。

## 3.4 源文件

| 文件 | 说明 |
|:---|:---|
| `transport/mcp_transport.h` | 接口声明 |
| `transport/mcp_transport.c` | UART1 硬件初始化、接收任务、发送函数 |
