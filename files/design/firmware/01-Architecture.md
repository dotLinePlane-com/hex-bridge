# 1. 固件架构设计

## 1.1 整体架构

HEX-Bridge 固件采用 **消息总线 + 模块化任务** 架构，基于 FreeRTOS 调度。

```
┌─────────────────────────────────────────────────────────────────┐
│                        app_main()                               │
│  1. NVS Flash 初始化                                            │
│  2. msg_bus_init() — 消息总线初始化                              │
│  3. msg_bus_register_module() — 注册各模块                      │
│  4. module->init() — 初始化各模块                               │
│  5. mcp_transport_init() — 启动 MCP 通信                       │
│  app_main() 返回后，各 FreeRTOS 任务自行运行                     │
└─────────────────────────────────────────────────────────────────┘
```

## 1.2 FreeRTOS 任务分配

| 任务名称 | 栈大小 | 优先级 | 所属模块 | 职责 |
|:---|:---|:---|:---|:---|
| `mcp_recv` | 4096 | 10 | MCP 传输层 | UART1 接收 → 帧解析 → 分发 |
| `uart_rx` | 3072 | 8 | UART 模块 | UART2 接收 → 事件上报 |

> **说明**：MCP 接收任务优先级最高，确保协议帧不会丢失。
> 各外设模块的接收任务优先级略低，让出 CPU 给协议处理。

## 1.3 内存预算

| 项目 | 大小 | 说明 |
|:---|:---|:---|
| MCP 解析缓冲区 | ~2.1 KB | 逻辑帧缓冲 |
| MCP UART 驱动缓冲 | 6 KB | RX 4KB + TX 2KB |
| UART2 驱动缓冲 | 3 KB | RX 2KB + TX 1KB |
| 帧构建缓冲区 | ~4.2 KB | 栈上分配，最坏情况 |
| FreeRTOS 任务栈 | ~7 KB | 各任务栈总和 |
| **总计** | ~22 KB | 远小于 ESP32 可用堆内存 (~300KB) |

## 1.4 模块注册机制

每个功能模块提供 `hex_module_t` 结构体：

```c
typedef struct {
    const char *name;               // 模块名
    uint8_t     cmd_range_start;    // 命令码起始（含）
    uint8_t     cmd_range_end;      // 命令码结束（含）
    esp_err_t (*init)(void);        // 初始化
    void (*handle_cmd)(const ubcp_frame_t *frame); // 命令处理
    void (*stop)(void);             // 清理（可选）
} hex_module_t;
```

添加新模块只需：
1. 创建 `modules/mod_xxx.h` 和 `modules/mod_xxx.c`
2. 实现 `hex_module_t` 接口
3. 在 `main.c` 中注册和初始化
4. 在 `CMakeLists.txt` 中添加源文件

## 1.5 代码目录结构

```
main/
├── hex_config.h          # 硬件引脚/缓冲区/波特率等全局配置
├── main.c                # 入口
├── protocol/             # 协议层（与硬件无关）
│   ├── ubcp_def.h        # 命令码、错误码、标志位常量
│   ├── ubcp_crc16.h      # CRC16 计算
│   ├── ubcp_frame.h      # 帧结构体与 API
│   └── ubcp_frame.c      # 帧解析/构建实现
├── core/                 # 核心框架
│   ├── module_base.h     # 模块接口定义
│   ├── seq_num.h         # 事件序列号管理
│   ├── msg_bus.h         # 消息总线接口
│   └── msg_bus.c         # 消息总线实现
├── transport/            # 传输层
│   ├── mcp_transport.h   # MCP 传输接口
│   └── mcp_transport.c   # UART1 收发实现
├── modules/              # 功能模块
│   ├── mod_system.h/.c   # 系统管理
│   └── mod_uart.h/.c     # UART 扩展
└── utils/
    └── hex_log.h         # 日志宏
```
