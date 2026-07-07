# 2. 消息总线设计

## 2.1 概述

消息总线是连接 MCP 传输层与各功能模块的核心枢纽，负责：
- **命令路由**：根据 CmdCode 将请求帧分发到对应模块
- **帧发送**：为模块提供统一的响应帧/事件帧发送接口

## 2.2 路由表

| CmdCode 范围 | 模块 | 状态 |
|:---|:---|:---|
| 0x00-0x0F | mod_system | ✅ 已实现 |
| 0x10-0x1F | mod_can | ⬜ 待实现 |
| 0x20-0x2F | mod_spi | ⬜ 待实现 |
| 0x30-0x3F | mod_i2c | ⬜ 待实现 |
| 0x40-0x4F | mod_network | ⬜ 待实现 |
| 0x50-0x5F | mod_tcp | ⬜ 待实现 |
| 0x60-0x6F | mod_udp | ⬜ 待实现 |
| 0x70-0x7F | mod_websocket | ⬜ 待实现 |
| 0x80-0x8F | mod_gpio | ⬜ 待实现 |
| 0x90-0x9F | mod_bulk | ⬜ 待实现 |
| 0xA0-0xAF | mod_uart | ✅ 已实现 |
| 0xB0-0xBF | mod_ota | ⬜ 待实现 |

## 2.3 数据流

```
                                ┌─────────────┐
   MCP 传输层                    │  消息总线    │
   mcp_recv_task ──帧──────────→│  dispatch() │
                                │             │
                                │  路由表查找   │──→ module->handle_cmd(frame)
                                └──────┬──────┘
                                       │
              ┌────────────────────────┤
              ▼                        ▼
        模块构建响应帧            模块构建事件帧
              │                        │
              ▼                        ▼
        msg_bus_send_frame()    msg_bus_send_frame()
              │                        │
              ▼                        ▼
        ubcp_frame_build()      ubcp_frame_build()
              │                        │
              ▼                        ▼
        mcp_transport_send()   mcp_transport_send()
              │                        │
              ▼                        ▼
            UART1 TX               UART1 TX
```

## 2.4 关键 API

```c
// 初始化
esp_err_t msg_bus_init(void);

// 注册模块
esp_err_t msg_bus_register_module(const hex_module_t *module);

// 分发请求帧（由 MCP 接收任务调用）
void msg_bus_dispatch(const ubcp_frame_t *frame);

// 发送帧（由模块调用，线程安全）
esp_err_t msg_bus_send_frame(const ubcp_frame_t *frame);

// 便捷：发送仅含状态码的响应
esp_err_t msg_bus_send_status_response(const ubcp_frame_t *req, uint8_t status);
```

## 2.5 线程安全

- `msg_bus_dispatch()` 在 `mcp_recv_task` 任务上下文中被调用
- `handle_cmd()` 也在 `mcp_recv_task` 上下文中同步执行
- `msg_bus_send_frame()` 内部通过 MCP 传输层的互斥锁保证发送原子性
- 事件上报从外设接收任务中调用 `msg_bus_send_frame()`，同样线程安全
