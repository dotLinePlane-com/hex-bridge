# 外部 SPI2 固件模块设计

> 本文描述 `mod_spi` 如何把 UBCP SPI 命令映射到 ESP-IDF SPI Master 驱动。命令载荷和主机可见行为以 [SPI 协议定义](../protocol/05-SPI.md) 为准。

## 1. 目标与边界

`mod_spi` 提供一个外部 SPI 主机通道，使用 ESP32 `SPI2_HOST`。板载 CAN 控制器 MCP2518FD 继续由 CAN 模块通过 SPI3 驱动；两个控制器、设备句柄和片选线互相独立。

模块当前实现一个 SPI 设备实例，固定通道 `UBCP_CH_SPI_EXT1 (4)` 和固定 GPIO，不向主机提供任意引脚映射或多个设备句柄。支持单线 8/16 位与 Quad 8 位事务；不实现协议特定命令解析、地址阶段、dummy cycle、Dual/Octal、DDR 或 SPI 从机。

SPI 从设备模式作为后续能力规划，当前未实现。ESP-IDF 的从设备驱动需要应用预先排队事务；外部主设备拉低 CS 并送出时钟后才完成传输，因此软件不能保证在一次事务中途才生成回复。驱动提供事务队列和完成结果接口，需以队列为固件架构基础。

## 2. 软件结构与资源

| 资源 | 设计 |
|:---|:---|
| 模块入口 | `mod_spi_get()` 返回 `hex_module_t`，命令范围 `0x20-0x2F` |
| 总线 | `spi_bus_initialize(SPI2_HOST, ..., SPI_DMA_CH_AUTO)`，模块初始化时建立一次 |
| 设备句柄 | `spi_bus_add_device()` 按当前 mode、时钟、位序和 Quad 能力创建；软件控制 CS，驱动设备的 `spics_io_num=-1` |
| 互斥 | FreeRTOS mutex 保护设备句柄、配置、CS 操作和同步传输；取锁超时返回 `ERR_BUSY` |
| 缓冲区 | 静态 TX/RX 缓冲区各 2045 字节，静态响应缓冲区为 UBCP 最大载荷，避免事务中动态分配 |
| 拓扑 | 初始化后注册通道 4，设备类型为 SPI |

板级引脚定义集中在 `main/hex_config.h`，并须与 [ESP32 引脚规划](../sch/esp32-pinout-design.md) 一致：SCLK=18、IO0=19、IO1=21、IO2=22、IO3=23、CS=27。SPI 总线声明为 Master + Quad 能力，单线与 Quad 共用这组固定引脚。

## 3. 初始化与生命周期

### 模块初始化

1. 创建模块 mutex。
2. 使用 `SPI2_HOST`、固定 SCLK/IO0–IO3 引脚、最大传输长度 2045 字节和 DMA 自动通道初始化总线。
3. 注册 UBCP SPI 通道 4。
4. 上层停止模块时，若设备已打开则先释放 CS、移除设备，再释放 SPI2 总线。

总线初始化失败时模块初始化返回错误；通道注册只在总线成功初始化后进行。

### OPEN / CLOSE

OPEN 校验固定 CS GPIO 和极性参数，配置 GPIO27 为输出并先驱动到非有效电平，然后以默认配置添加设备：Mode 0、1 MHz、MSB、8 位、自动 CS、单线。设备添加成功后进入打开状态。重复 OPEN 返回 `ERR_ALREADY_OPEN`。

CLOSE 在 mutex 保护下将 CS 置为非有效电平、移除设备并清除打开状态，最后释放 CS GPIO 配置。关闭态 CLOSE 返回 `ERR_NOT_OPEN`。模块 stop 执行同样的资源清理，并额外释放 SPI2 总线。

### CONFIG

CONFIG 校验 9 字节载荷、mode、时钟范围、位序、字宽、CS 模式和线宽。Quad 与 16 位字宽组合不支持。更新时先释放可能保持的手动 CS，移除旧设备句柄，再按新参数添加设备；如添加失败则恢复旧参数并尝试重建旧设备。恢复也失败时设备转为关闭态。

ESP-IDF 设备配置启用 LSB flag（如选择 LSB）及 Quad half-duplex flag（Quad 模式）。CS 由 GPIO 软件控制，因此 CS 极性可配置，且支持跨 UBCP 请求保持。

## 4. 命令处理与事务映射

消息总线将 SPI 命令交给 `spi_handle()`。模块先检查通道号，再分发 OPEN、CLOSE、CONFIG、TRANSFER、WRITE、READ 或 CS_CONTROL；未知命令返回 `ERR_NOT_SUPPORT`。数据命令检查载荷长度、N 值、最大传输长度及 16 位偶数长度要求。

| UBCP 命令 | SPI 驱动操作 | 成功响应 |
|:---|:---|:---|
| `SPI_TRANSFER` | 单线事务，TX/RX 均为 N 字节 | `Status, RxLen:u16, RxData[N]` |
| `SPI_WRITE` | TX N 字节；单线丢弃 RX，Quad 以 QIO 半双工发送 | `Status, ActualLen:u16` |
| `SPI_READ` | 单线发送 FillByte 并接收；Quad 使用纯输入 QIO 阶段 | `Status, RxLen:u16, RxData[N]` |
| `SPI_CS_CONTROL` | 软件 GPIO27 设置有效/非有效电平 | `Status` |

自动 CS 模式由模块在事务前后切换 GPIO；手动模式下数据事务不操作 CS，由主机显式控制。CONFIG 和 CLOSE 都会释放 CS。设备事务通过 `spi_device_transmit()` 同步完成，模块 mutex 确保同一时刻只有一条 SPI 操作访问设备状态和缓冲区。

## 5. 响应与错误处理

- 成功数据响应在静态响应缓冲区中组装，长度字段使用大端序；READ/TRANSFER 数据按 SPI 接收字节原样返回。
- 参数错误、错误通道、未打开、重复打开和忙等待超时使用对应 UBCP 通用状态码。
- 不支持的操作使用 `ERR_NOT_SUPPORT`；SPI 传输失败使用 `ERR_SPI_TRANSFER`；OPEN/CONFIG/CLOSE 驱动层失败映射为 `ERR_HAL_FAIL`。
- 错误响应仅含一个 Status 字节；成功响应长度由对应命令定义。
- 传输失败时自动 CS 释放；手动 CS 保持主机设置的状态，主机应 Deassert 或 CLOSE。

## 6. 配置常量与关联文件

| 文件 | 职责 |
|:---|:---|
| `main/hex_config.h` | SPI2 host、固定 GPIO、最大传输长度 |
| `main/protocol/ubcp_def.h` | 通道、模式/宽度枚举、错误码、命令码 |
| `main/modules/mod_spi.h` / `mod_spi.c` | 模块注册接口、初始化、命令分发和 SPI 事务 |
| `main/main.c` | 注册 SPI 模块生命周期 |
| `files/design/function/05-spi.md` | 面向用户的功能范围及使用概览 |
| `files/design/protocol/05-SPI.md` | 主机与固件之间的线上协议规范 |

## 7. SPI 从设备模式规划（未实现）

### 7.1 模式和生命周期

SPI2 的主设备和从设备角色不能同时使用同一控制器。未来的设备打开流程需显式选择角色，并在切换时完整停止旧角色、释放总线，再初始化对应 master/slave 驱动。不能在现有 SPI2 master bus 仍活动时直接启动 slave 驱动。SPI3 目前由 CAN/MCP2518FD 使用，不应在产品运行时借作 SPI 主设备；只可在隔离的自测固件中停用 CAN 后用作测试主机。

从设备角色由外部主设备提供 SCLK、CS、MOSI；ESP32 提供 MISO。ESP32 不决定外部事务开始时间，也不能主动产生时钟。因此命令接口必须是异步队列语义，而不能照搬现有 `SPI_TRANSFER` 的同步主设备语义。

### 7.2 需要先冻结的契约

1. **准备发送**：UBCP 主机将一笔或多笔 TX 数据放入固件队列；队列为空时从设备回传填充值还是禁止主机开始事务。
2. **Ready 握手**：外部主设备如何确认一个完整 TX/RX 槽位已准备好。建议增加 READY 输出 GPIO；在引脚规划中明确极性、空闲态和复位态。未分配 READY 前，不冻结外部事务协议。
3. **事务边界**：定义一次 CS 有效区间是否对应一个队列项、允许的最大长度、短帧如何处理，以及过长事务是否截断并报告溢出。
4. **完成上报**：定义 RX 数据可读取方式（事件推送或队列读取）、序号、缓冲区所有权、背压和丢包计数。
5. **参数和能力**：定义 Mode、位序、单线/Quad、频率上限、DMA/对齐限制。角色、线宽、引脚约束应在 OPEN 前检查。
6. **异常恢复**：定义无 READY、主设备提前访问、CS 中断、队列满、超时、close/reopen 和 UBCP 断连时如何清队列及复位状态。

协议命令空间 `0x27-0x2F` 当前为预留。完成上述契约和引脚分配后，再决定从设备命令是否扩展在该范围内；不要在实现前让主机依赖未冻结的命令码或载荷。

### 7.3 分阶段验证

- **阶段 A：驱动可行性**：独立测试固件禁用 CAN 模块，将 SPI3 配置为 Master、SPI2 配置为 Slave，并用跳线连接 SCLK/MOSI/MISO 和独立测试 CS。板载 MCP2518FD 的 GPIO15 CS 保持非有效，SPI3 使用另一测试 GPIO 片选 SPI2 Slave，避免 MCP2518FD 同时驱动 MISO。验证预排队 TX、RX 长度和连续事务。
- **阶段 B：协议与队列**：以 MCP/UBCP 主机控制预置、读取、取消和队列满恢复；校验异步完成事件和断连清理。
- **阶段 C：真实主机**：接入外部 SPI 主设备或 MCU 测试夹具，在目标频率、线长和电气条件下验证 READY 时序与 MISO 建立时间。

ESP-IDF SPI slave 文档说明事务需先通过 `spi_slave_queue_trans()` 排队，之后由外部主机启动；CPU 处理响应存在延迟，READY GPIO 可用于主机同步。ESP32 从设备频率和 DMA 对齐需按实际 IDF 版本及事务缓冲区验证，不能直接沿用 SPI 主设备的 40 MHz 配置。[ESP-IDF SPI Slave 文档](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/spi_slave.html)
