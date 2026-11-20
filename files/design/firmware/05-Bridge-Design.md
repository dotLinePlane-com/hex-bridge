# 05. 固件端网桥数据多路复用与同步设计

## 1. 背景与设计目标

HEX-Bridge 作为基于 ESP32 的多功能硬件接口扩展设备，需要通过单一的物理 MCP 通信链路（如 UART1 串口，或未来的 TCP Socket）为上位机（PC / VS Code 插件）提供多个虚拟外设通道（UART2、CAN0、CAN1、SPI、I2C）的并发复用能力。

本设计文档旨在规避多任务并发读写物理通道时的**数据帧交错（Frame Interleaving）**、**高水位溢出丢包（Buffer Overflow）**和**死锁**风险，为固件开发提供关于**多路复用**、**任务互斥同步**和**流控管理**的技术规范。

---

## 2. 固件整体层次架构

固件采用 **硬件驱动 -> 传输适配 -> 协议解析 -> 消息总线 -> 外设模块** 的分层设计。

```
+-----------------------------------------------------------------------+
|                            外设功能模块层                             |
|  [mod_system]        [mod_uart] (CH0/CH1)       [mod_can] (CAN0/CAN1) |
+-------+--------------------+----------------------+-------------------+
        |                    |                      |
        | 发送响应/事件帧     | 发送响应/事件帧       | 发送响应/事件帧
        v                    v                      v
+-----------------------------------------------------------------------+
|                         msg_bus (核心消息总线)                        |
|   - 维护全局发送互斥锁 s_bus_mutex                                    |
|   - 维护逻辑帧构建与转义静态缓冲区 s_wire_buf                          |
+------------------------------------+----------------------------------+
                                     |
                                     v 调用 ubcp_frame_build() & 物理发送
+-----------------------------------------------------------------------+
|                        mcp_transport (传输适配层)                     |
|            [UART1 传输适配]          [TCP Socket 传输适配 (待扩展)]     |
+------------------------------------+----------------------------------+
                                     |
                                     v 物理 IO
╔═══════════════════════════════════════════════════════════════════════╗
║                      物理 MCP 通信链路 (PC / 上位机)                   ║
╚═══════════════════════════════════════════════════════════════════════╝
```

---

## 3. 双向数据流与互斥设计

物理通道只被物理初始化一次。所有的逻辑通道共享此链路。

### 3.1 下行数据流（PC -> 硬件）
1. **接收任务 (`mcp_recv_task`)**：
   - 独占式地从 MCP 物理接口读取字节流。
   - 逐字节送入流式帧解析器 `ubcp_parser_feed` 进行反转义。
   - 解析器内部实时更新 CRC16。当收到未转义的 `0x7E` (EOF) 且校验通过时，派发完整逻辑帧 `ubcp_frame_t`。
2. **消息总线分发 (`msg_bus_dispatch`)**：
   - 在接收任务的上下文（Thread Context）中，根据 `CmdCode` 范围同步调用对应的模块处理器（如 `mod_uart->handle_cmd` 或 `mod_can->handle_cmd`）。
   - **注意**：为防止阻塞 `mcp_recv_task` 导致物理接收溢出，`handle_cmd` 内部如果执行耗时操作，应通过 FreeRTOS 队列将任务分发到外设模块的专属工作任务中异步执行，禁止在分发上下文中进行大延迟的阻塞等待。

### 3.2 上行数据流（硬件 -> PC）
当多个外设模块（如串口接收任务 `uart_rx_task`、CAN 接收中断服务等）同时向 PC 上报事件数据时，若不进行同步控制，输出到物理通道上的字节流会发生交错，导致 CRC 校验失败。

**互斥发送机制**：
* 消息总线维护全局发送互斥信号量 `s_bus_mutex` 和静态构建缓冲区 `s_wire_buf`（大小 4200 字节，防止大帧转义时栈溢出）。
* 发送流程伪代码：

```c
esp_err_t msg_bus_send_frame(const ubcp_frame_t *frame)
{
    // 1. 获取发送互斥锁，等待超时时间 1000ms
    if (xSemaphoreTake(s_bus_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        HEX_LOGW(TAG, "获取发送锁超时，丢弃帧 CMD=0x%02X", frame->cmd_code);
        return ESP_ERR_TIMEOUT;
    }

    size_t wire_len = 0;
    // 2. 逻辑帧打包与转义，存入 s_wire_buf
    esp_err_t err = ubcp_frame_build(frame, s_wire_buf, sizeof(s_wire_buf), &wire_len);
    if (err == ESP_OK) {
        // 3. 调用物理适配层发送原子帧
        err = mcp_transport_send(s_wire_buf, wire_len);
    }

    // 4. 释放发送锁
    xSemaphoreGive(s_bus_mutex);
    return err;
}
```

---

## 4. 共享链路下的流量控制（Flow Control）

当串口和 CAN 接口同时在高负荷下接收数据并向 PC 疯狂发送事件帧（`CMD_UART_RECV` 和 `CMD_CAN_RECV`）时，物理链路带宽（尤其是 921600 bps 串口）将面临极限。

### 4.1 水位监控与 XON/XOFF 机制
固件必须建立逻辑流控管理，配合消息总线定期向 PC 报告水位：

1. **缓存区水位报告**：
   - 固件周期性或在接收环形缓冲区（Ring Buffer）达到临界值时，通过 `NET_STATUS` 或专门的流控事件帧（`FLOW_CTRL_EVENT`）上报当前各外设接收队列的水位。
2. **主动暂停（XOFF）与恢复（XON）**：
   - **XOFF 触发**：当某个外设通道的软件接收缓冲区水位超过 **80%** (由 `HEX_FLOW_XOFF_PCT` 定义) 时，外设任务向 PC 发送 XOFF 事件帧，请求 PC 暂停下发该通道的数据发送包。
   - **XON 恢复**：当缓冲区水位回落到 **50%** (由 `HEX_FLOW_XON_PCT` 定义) 以下时，外设任务向 PC 发送 XON 事件帧，恢复数据下发。
   - **下位机硬丢弃**：若水位达到 100%，固件应直接丢弃外设新进数据，并在下一个上报帧中标记丢包标志（如 `rxFlags` 中的 `FrameLost` 标志位），同时累加错误计数器，向 PC 报警。

---

## 5. 面向 CAN FD 和网口扩展的适配设计

### 5.1 CAN FD 模块适配设计（`mod_can.c`）
* **通道号映射**：设备最多支持 2 路 CAN 接口，由固件编译期分配静态 Channel ID
  （如 `UBCP_CH_CAN_EXT1 = 3`、`UBCP_CH_CAN_EXT2 = 4`）。
  Host 通过 `GET_TOPOLOGY (0x07)` 获取实际映射关系，不得自行假设通道号。
* **接收中断优化**：CAN 控制器（如 MCP2518FD）收到总线帧后触发 GPIO 中断。固件中的 CAN 接收服务应当从硬件 FIFO 批量读取多帧，合并打包后通过 `msg_bus_send_frame` 批量上报，以降低互斥锁 `s_bus_mutex` 的竞争频率。
* **经典 CAN / CAN FD 报文结构定义**：
  上报 `CMD_CAN_RECV` (0x14) 时，Payload 前 4 字节为统一 `CanID`（含扩展帧、RTR、FD 等 Flags 位），第 5 字节为 `DLC`，之后为最大 64 字节的经典/FD 数据。

### 5.2 网口与 TCP 模块适配设计（`mod_tcp.c`）
* **动态句柄路由**：因为网络连接非常多，无法用静态的 `ChannelID` 来映射。
* **Handle 映射表**：
  - `mod_tcp` 模块内部维护一个动态映射数组：
    ```c
    typedef struct {
        uint16_t conn_handle;      // 0x8001 - 0xFFFE 范围的逻辑句柄
        int      socket_fd;        // lwIP 套接字文件描述符
        bool     is_active;
    } hex_tcp_conn_t;
    ```
  - 当收到 `TCP_SEND (0x54)` 请求时，`mod_tcp` 解析 Payload 中的 `ConnHandle`，查表找到对应的 `socket_fd` 调用 `send()` 发送。
  - 当底层的 `select/poll` 任务检测到某个 `socket_fd` 收到网络数据时，`mod_tcp` 自动为数据打包上 `ConnHandle` 报头，作为 `TCP_RECV (0x55)` 事件帧通过消息总线上报给 PC。

### 5.3 SPI 与 I2C 模块适配设计（`mod_spi.c` / `mod_i2c.c`）
* **同步阻塞与片选管理**：
  - SPI（`0x20-0x2F`）和 I2C（`0x30-0x3F`）物理协议在硬件层是同步、主从结构的应答协议（Master-Slave）。因此，PC 端的读写请求（如 `SPI_TRANSFER`、`I2C_WRITE`）在固件端均采取**同步阻塞响应**模式。
   - **SPI 片选控制**：通过 `ChannelID` 区分不同的 SPI 从设备，每个 CS 片选对应一个
     独立的静态 Channel ID（如 `UBCP_CH_SPI_EXT1 = 5` 对应板载 MCP2518FD，
     `UBCP_CH_SPI_EXT2 = 6` 对应外部扩展引脚 CS）。
* **硬件总线互斥**：
  - 固件端在调用 ESP32 物理 SPI 驱动或 I2C 驱动前，必须通过 ESP-IDF 驱动层自身的互斥锁（如 `i2c_master_write_read_device` 的底层锁）来防止多线程冲突。这与 `msg_bus` 物理发送锁解耦。

### 5.4 GPIO 模块适配设计（`mod_gpio.c`）
* **中断异步事件上报**：
  - 当 GPIO 引脚被配置为输入中断模式（如双边沿触发）时，固件端的 GPIO 中断服务程序（ISR）将中断事件推入专门的 GPIO 工作队列，由后台任务向 PC 发送 `GPIO_INTR_EVENT (0x84)` 异步事件帧，上报触发的引脚号和电平状态。

---

## 6. 多通道并发事务时序图

下图展示了上位机同时进行“扩展串口 1 发送”与“CAN 0 接收数据上报”时的时序冲突与互斥解决流程：

```mermaid
sequenceDiagram
    autonumber
    participant Host as 上位机 (PC)
    participant Bus as msg_bus (设备消息总线)
    participant UART as mod_uart (串口1任务)
    participant CAN as mod_can (CAN0任务)
    participant PHY as mcp_transport (物理通道)

    Note over Host, PHY: 上位机向扩展串口 1 发送数据，同时 CAN0 总线收到数据需要上报

    Host->>PHY: [下行] 发送 CMD_UART_SEND (Channel: 1)
    PHY->>Bus: 解析并分发到 UART 模块
    activate UART
    UART->>UART: 执行物理串口发送...

    par 异步上报触发
        CAN->>Bus: 调用 msg_bus_send_frame(CMD_CAN_RECV, Ch:0)
        Bus->>Bus: 获取 s_bus_mutex (成功)
        Bus->>PHY: [上行] 独占发送 CAN 接收帧
    and 响应触发
        UART->>Bus: 发送响应帧 CMD_UART_SEND (Ch: 1)
        Note over Bus: s_bus_mutex 被 CAN 占用，UART 任务阻塞等待
        Bus-->>UART: 挂起等待信号量
    end

    Bus-->>PHY: CAN 接收帧发送完毕
    Bus->>Bus: 释放 s_bus_mutex
    deactivate UART

    Note over Bus: UART 响应任务被唤醒
    activate UART
    Bus->>Bus: 获取 s_bus_mutex (成功)
    Bus->>PHY: [上行] 独占发送 UART_SEND 响应帧
    Bus->>Bus: 释放 s_bus_mutex
    deactivate UART
```

---

## 7. 远程 MCP 传输扩展（Wi-Fi / 以太网 TCP）与上位机生态桥接规划

### 7.1 设计原则：固件统一 UBCP 总线 + 上位机按需协议转换

为了同时实现**全外设无线/有线远程使用**与**第三方标准串口软件生态兼容（RFC 2217）**，同时避免在 ESP32 固件内部引入多协议竞争硬件所有权的问题，遵循以下分层原则：

1. **固件侧保持纯粹**：
   - 所有外设模块（`mod_uart`、`mod_can`、`mod_spi`、`mod_i2c` 等）**仅对 `msg_bus` 负责**，不感知底层物理传输介质，也不在固件内直接实现 RFC 2217 等第三方应用层协议。
   - 远程能力通过在 `mcp_transport` 层增加 **TCP Socket 传输适配**（监听 `TCP 9500` 端口，承载于ESP32 片内 2.4 GHz Wi-Fi STA）实现。
   - TCP Socket 接收到的字节流直接复用 `ubcp_parser_feed()` 在线反转义与 CRC16 校验；`msg_bus_send_frame()` 构建的原子线路帧通过 `mcp_transport_send()` 写入活跃的 TCP 客户端 Socket（或 `UART1`）。
2. **上位机侧提供 `本地 RFC 2217 端口 ↔ 远端 ESP32 UBCP (TCP/Serial)` 转换桥**：
   - 在 PC 侧运行 `hex-bridge-rfc2217-bridge.py`（或由 MCP Server 守护启动），对外在本地回环地址（如 `127.0.0.1:2217`）提供标准 **RFC 2217 (Telnet Com Port Control)** 服务。
   - 对内通过 `MCPTransport`（支持本地 `COM4` 串口或远端 `socket://<esp32_ip>:9500`）将 RFC 2217 的波特率/数据位/停止位/校验位/Break/Purge 控制与双向字节流实时翻译为 UBCP `0xA0-0xA7` 帧。
   - 详细的 RFC 2217 子命令与 UBCP `0xA0-0xA7` 映射规范参见 [04-UART-Module.md 第 4.7 节](04-UART-Module.md#47-上位机-本地-rfc-2217-端口--远端-esp32-ubcp-tcpserial-转换桥设计规划)。

### 7.2 远程全外设复用与本地 RFC 2217 桥接架构图

```mermaid
flowchart TB
    subgraph HostPC["上位机 (PC)"]
        direction TB
        ThirdParty["第三方串口工具\n(pyserial / esptool / PuTTY / VCOM)"]
        RFCBridge["本地 RFC 2217 转换桥\n(127.0.0.1:2217 ↔ UBCP 0xA0-0xA7)"]
        MCPServer["MCP Server / CLI 工具\n(CAN FD / UART / 网络 / SPI / I2C)"]
        MuxClient["上位机 UBCP 多路复用客户端\n(MCPTransport: Serial 或 TCP Socket)"]

        ThirdParty <-->|"RFC 2217 (Telnet + Opt 44)"| RFCBridge
        RFCBridge <-->|"UBCP 0xA0-0xA7"| MuxClient
        MCPServer <-->|"UBCP 全命令集 (0x00-0xBF)"| MuxClient
    end

    subgraph ESP32["远端 / 本地 HEX-Bridge (ESP32)"]
        direction TB
        Trans["mcp_transport 传输适配层\n[UART1: COM4] / [Wi-Fi & ETH TCP: 9500]"]
        Bus["msg_bus 核心消息总线\n(s_bus_mutex 原子帧保護 + 流控水位)"]
        UART2["mod_uart\n(UART2 扩展口)"]
        CAN["mod_can\n(MCP2518FD CAN FD)"]
        NET["mod_network / tcp / udp / ws\n(网络测试代理)"]

        Trans <--> Bus
        Bus <--> UART2 & CAN & NET
    end

    MuxClient <===>|"物理链路二选一：\n1. 本地 USB 串口 (COM4)\n2. 远程 Wi-Fi / 以太网 (TCP 9500)"| Trans
```

### 7.3 该架构的核心工程优势

1. **零 GPIO 额外消耗**：当前硬件外部 GPIO 已 100% 分配完毕（剩余 0 个），ESP32 片内 Wi-Fi 不占用任何外部引脚；且模组配备 8MB PSRAM，开启 `CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP` 后可轻松承载 Wi-Fi + lwIP 协议栈内存开销。
2. **一处打通，全外设远程化**：`mcp_transport` 接入 Wi-Fi / 以太网 TCP 后，不仅扩展串口 `UART2` 可以远程使用，**CAN FD (`MCP2518FD`)、SPI、I2C、GPIO、OTA 也同步获得远程无线访问能力**。
3. **抗无线网络抖动（Jitter）**：串口硬件断帧（行模式、定长模式、Modbus RTU 超时模式 `RxMode=0x03`）与 CAN 报文微秒级时间戳均在 ESP32 本地实时完成，封装为带 CRC16 的 UBCP 帧后再经 Wi-Fi 传输，不会因无线延迟抖动破坏协议时序。

### 7.4 单活链路与切换边界（开发规约）

UART1 为默认入口。启用远程控制时，仅允许一个 TCP 9500 客户端取得控制权。成功切换后，UART1 暂停命令分发，后续 TCP 客户端直接关闭；单活约束覆盖命令、同步回复、异步事件和流控。每次切换先停止旧入口接单，再结束或丢弃旧会话的待发帧，重置解析器、流控与收发队列后开放新入口。异步完成的旧请求必须按会话代次隔离。TCP 断开或 Wi-Fi 掉线后恢复 UART1，无需重启。UART1 的配网恢复路径须可用。TCP 9500 用于可信局域网或 VPN；跨公网中继如启用，须经鉴权并占用同一远程控制席位。

CMSIS-DAP 使用独立服务，其会话规则见 [网络调试探针规约](08-DAPLink.md)。DAP 与一个活跃的 UBCP 会话可以同时工作。
