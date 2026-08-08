# 1. 固件架构设计

## 1.1 整体架构

HEX-Bridge 固件采用 **消息总线 + 模块化任�?* 架构，基�?FreeRTOS 调度�?
```
┌─────────────────────────────────────────────────────────────────�?�?                       app_main()                               �?�? 1. NVS Flash 初始�?                                           �?�? 2. msg_bus_init() �?消息总线初始�?                             �?�? 3. topology_init() �?硬件拓扑路由表初始化（静态通道号绑定）       �?�? 4. msg_bus_register_module() �?注册各模�?                     �?�? 5. module->init() �?初始化各模块                               �?�? 6. mcp_transport_init() �?启动 MCP 通信                       �?�? 7. 广播 SYS_BOOT_EVENT (0x06) 事件帧通知主机系统复位/启动原因  �?�? app_main() 返回后，�?FreeRTOS 任务自行运行                     �?�?                                                                �?�? ── 关闭流程 (�?RESET(0x04) 触发) ──                           �?�? 1. msg_bus_stop_all_modules()  �?反向遍历注册�?              �?�? 2. module->stop()  �?各模块关�?socket、释放资源、停止任�?    �?�? 3. esp_restart()  �?系统软复�?                                �?└─────────────────────────────────────────────────────────────────�?```

## 1.2 FreeRTOS 任务分配

| 任务名称 | 栈大�?| 优先�?| 所属模�?| 职责 |
|:---|:---|:---|:---|:---|
| `mcp_recv` | 4096 | 10 | MCP 传输�?| UART1 接收 �?帧解�?�?分发 |
| `uart_rx` | 3072 | 8 | UART 模块 | UART2 接收 �?事件上报 |

> **说明**：MCP 接收任务优先级最高，确保协议帧不会丢失�?> 各外设模块的接收任务优先级略低，让出 CPU 给协议处理�?
## 1.3 内存预算

| 项目 | 大小 | 说明 |
|:---|:---|:---|
| MCP 解析缓冲�?| ~2.1 KB | 逻辑帧缓�?|
| MCP UART 驱动缓冲 | 6 KB | RX 4KB + TX 2KB |
| UART2 驱动缓冲 | 3 KB | RX 2KB + TX 1KB |
| 帧构建缓冲区 | ~4.2 KB | 栈上分配，最坏情�?|
| FreeRTOS 任务�?| ~7 KB | 各任务栈总和 |
| **总计** | ~22 KB | 远小�?ESP32 可用堆内�?(~300KB) |

## 1.4 模块注册机制

每个功能模块提供 `hex_module_t` 结构体：

```c
typedef struct {
    const char *name;               // 模块�?    uint8_t     cmd_range_start;    // 命令码起始（含）
    uint8_t     cmd_range_end;      // 命令码结束（含）
    esp_err_t (*init)(void);        // 初始�?    void (*handle_cmd)(const ubcp_frame_t *frame); // 命令处理
    void (*stop)(void);             // 清理（可选）
} hex_module_t;
```

添加新模块只需�?1. 创建 `modules/mod_xxx.h` �?`modules/mod_xxx.c`
2. 实现 `hex_module_t` 接口（至少实�?`init` �?`handle_cmd`；`stop` 可为 NULL�?3. �?`main.c` 中注册和初始�?4. �?`CMakeLists.txt` 中添加源文件

### 1.4.1 模块生命周期

```
  启动流程                   关闭流程 (RESET 触发)
  ────────                  ─────────────────────
  msg_bus_register()        msg_bus_stop_all_modules()
       �?                          �?       �?                          �?(反向遍历注册�?
  module->init()             module->stop()
       �?                          �?       ├── 分配 socket              ├── 关闭所�?socket
       ├── 启动 select task         ├── s_task_running = false
       └── 注册 LIST_CONNS provider └── 发�?DISCONNECT_EVENT
```

**stop() 实现状�?*:

| 模块 | stop() 函数 | 行为 |
|:---|:---|:---|
| TCP | `tcp_stop()` | 设置 `s_task_running=false` �?`tcp_close_all()` 关闭所�?socket |
| UDP | `udp_stop()` | 同上 |
| WebSocket | `ws_stop()` | 同上 |
| Network | `network_stop()` | 注消 ETH/IP 事件处理�?|
| System | `NULL` | 无需清理 |

**关闭顺序**：`msg_bus_stop_all_modules()` 按注册顺�?*反向**遍历：WS �?UDP �?TCP �?Network，确保依赖关系正确释放�?
## 1.5 代码目录结构

```
main/
├── hex_config.h          # 硬件引脚/缓冲�?波特率等全局配置
├── main.c                # 入口
├── protocol/             # 协议层（与硬件无关）
�?  ├── ubcp_def.h        # 命令码、错误码、标志位常量
�?  ├── ubcp_crc16.h      # CRC16 计算
�?  ├── ubcp_frame.h      # 帧结构体�?API
�?  └── ubcp_frame.c      # 帧解�?构建实现
├── core/                 # 核心框架
�?  ├── module_base.h     # 模块接口定义
�?  ├── seq_num.h         # 事件序列号管�?�?  ├── topology.h/.c     # 硬件拓扑路由�?�?  ├── msg_bus.h         # 消息总线接口
�?  └── msg_bus.c         # 消息总线实现
├── transport/            # 传输�?�?  ├── mcp_transport.h   # MCP 传输接口
�?  └── mcp_transport.c   # UART1 收发实现
├── modules/              # 功能模块
�?  ├── mod_system.h/.c   # 系统管理
�?  └── mod_uart.h/.c     # UART 扩展
└── utils/
    └── hex_log.h         # 日志�?```

## 1.6 硬件拓扑路由�?(Topology Routing)

固件在编译期为每个物理外设分配唯一的静�?`Channel ID`，Host 必须通过
`GET_TOPOLOGY (0x07)` 获取拓扑后方可寻址。Host 不得自行编�?Channel ID�?
### 核心数据结构

```c
/* 全局唯一的静态通道 ID */
typedef enum {
    UBCP_CH_UART_EXT1 = 1,  // 物理扩展串口 1 (UART2, 对应 COM3 引脚)
    UBCP_CH_UART_EXT2 = 2,  // 物理扩展串口 2 (预留)
    UBCP_CH_CAN_EXT1  = 3,  // 物理扩展 CAN 1
    UBCP_CH_SPI_EXT1  = 4,  // 物理扩展 SPI 1
} ubcp_channel_id_t;

/* 物理外设类型 */
typedef enum {
    UBCP_DEV_TYPE_UART = 1,
    UBCP_DEV_TYPE_CAN  = 2,
    UBCP_DEV_TYPE_SPI  = 3,
    UBCP_DEV_TYPE_I2C  = 4,
    UBCP_DEV_TYPE_GPIO = 5,
} ubcp_device_type_t;

/* 路由表项 */
typedef struct {
    uint8_t channel_id;     // 编译期分配的静�?Channel ID
    uint8_t device_type;    // 外设类型 (ubcp_device_type_t)
    void   *device_driver;  // 对应硬件驱动上下文指�?} ubcp_route_entry_t;
```

### 路由表注�?
路由表在 `topology_init()` 中初始化，采用动态注册方式（非编译期 const）以
支持后续外设模块的运行时注册�?
```c
/**
 * @brief 初始化并构建硬件拓扑路由�? *
 * 各外设模块在 module->init() 内部调用 topology_register() 注册自身�? * mod_system �?GET_TOPOLOGY 处理函数通过 topology_for_each() 遍历路由表�? */
void topology_init(void);

/**
 * @brief 向路由表注册一个硬件通道
 * @param channel_id   静态通道�? * @param device_type  外设类型
 * @param driver       驱动上下文指�? */
void topology_register(uint8_t channel_id, uint8_t device_type, void *driver);

/**
 * @brief 遍历路由表，对每个通道调用回调
 * @param callback  回调函数 (channel_id, device_type, driver, user_data)
 * @param user_data 透传用户数据
 * @return 已遍历的通道�? */
int topology_for_each(void (*callback)(uint8_t, uint8_t, void*, void*),
                      void *user_data);

/**
 * @brief �?Channel ID 查找路由表项
 * @param channel_id 要查找的通道�? * @return 路由表项指针，未找到返回 NULL
 */
const ubcp_route_entry_t *topology_find(uint8_t channel_id);
```

### 模块 Open 处理中的路由校验

每个模块�?Open/Config 处理函数在操作硬件前，必须先通过路由表校�?Channel ID�?
1. **Channel ID 存在性检�?*：`topology_find(channel_id)` 非空
2. **硬件类型匹配检�?*：`route->device_type == 本模块期望类型`
3. 校验失败时返回对应的错误�?(`ERR_CHANNEL_INVALID` �?`ERR_TYPE_MISMATCH`)

校验通过后，从路由表项中取出 `device_driver` 指针操作具体的硬件实例�?