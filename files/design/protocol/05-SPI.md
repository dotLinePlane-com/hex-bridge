# 5. SPI 外部扩展接口（SPI2，命令 `0x20-0x2F`）

本章定义 UBCP 主机通过 HEX-Bridge 的外部 SPI2 主机接口控制一个 SPI 从设备的完整行为。当前实现提供单线 SPI 和 Quad SPI（4 根双向数据线）；不提供 Dual SPI、Octal SPI、SPI 从机或运行时任意引脚映射。

## 5.1 硬件资源和限制

| 信号 | ESP32 GPIO | 单线模式 | Quad 模式 |
|---|---:|---|---|
| SCLK | 18 | 时钟 | 时钟 |
| IO0 | 19 | MOSI | 数据线 0 |
| IO1 | 21 | MISO | 数据线 1 |
| IO2 | 22 | 未使用 | 数据线 2 / WP |
| IO3 | 23 | 未使用 | 数据线 3 / HOLD |
| CS | 27 | 片选 | 片选 |

这些信号由 GPIO Matrix 路由到 SPI2（`SPI2_HOST`）；GPIO 选择固定，不由主机在命令中更改。GPIO27 原预留为可选 SWD nRESET；现分配给外部 SPI CS，SWD 复位线因此不可同时使用。SPI2 的板级引脚以 `files/sch/esp32-pinout-design.md` 为准。

SPI2 是唯一的外部扩展 SPI 总线，固件当前只允许打开一个从设备。板载 MCP2518FD 继续使用 SPI3，不属于本 UBCP SPI 通道。SPI 外部通道固定为 `UBCP_CH_SPI_EXT1=4`。

GPIO Matrix 布线的保守时钟上限为 40 MHz；固件接受 10 kHz–40 MHz。最终可用频率取决于从设备时序、电气负载和 PCB 布线。CS 空闲态由 `CsPolarity` 决定；Quad IO 线需按目标从设备要求配置外部上拉/下拉。

## 5.2 通用载荷约定

- 多字节整数均为**大端序**，与 UBCP v2.0 全局约定一致。
- 每个 SPI 命令都必须使用通道 ID `0x04`。
- 除 `SPI_OPEN` 外，所有操作要求设备已打开；除 `SPI_CLOSE` 外，配置/传输命令也要求已打开。
- 响应首字节 `Status` 使用 UBCP 通用错误码；成功为 `0x00`。具体传输错误使用 SPI 错误码 `0x20–0x23`。命令响应均为 UBCP 普通响应（DIR=1、EVT=0）。
- 最大单次数据长度为 2045 字节，使最大读响应（状态 1 + 长度 2 + 数据 2045）不超过 UBCP 载荷上限 2048 字节。零长度非法。
- 当前只支持一个活动 SPI 设备和同步阻塞事务。固件串行化配置、CS 和传输操作。

SPI API 只定义 SPI 总线上的时钟和数据阶段，不解析器件命令、地址或寄存器。除非命令另有说明，`N` 指总线传送的字节数，而非 SPI 时钟周期数。发送缓冲区中的字节按其原始顺序发送；16 位模式下相邻两个字节组成一个 16 位字，主机必须按从设备要求提供高/低字节顺序，本协议不会交换字节。

UBCP 层的请求序号、超时、重试和重复请求处理规则继续遵循 UBCP v2.0。SPI 操作是同步执行的；主机应等待本次响应后再提交下一 SPI 命令。手动 CS 可跨请求保持，但不代表请求可以并发。

## 5.3 命令一览

| 命令 | 方向 | 用途 |
|---|---|---|
| `0x20 SPI_OPEN` | 请求/响应 | 打开固定 SPI2 总线设备 |
| `0x21 SPI_CLOSE` | 请求/响应 | 释放 CS 并关闭设备 |
| `0x22 SPI_CONFIG` | 请求/响应 | 配置模式、时钟、位序、字宽、CS 和线宽 |
| `0x23 SPI_TRANSFER` | 请求/响应 | 单线全双工交换 |
| `0x24 SPI_WRITE` | 请求/响应 | 发送数据，不返回接收数据 |
| `0x25 SPI_READ` | 请求/响应 | 发送填充值并返回接收数据 |
| `0x26 SPI_CS_CONTROL` | 请求/响应 | 手动保持/释放 CS |
| `0x27-0x2F` | — | 保留 |

### SPI_OPEN (`0x20`)

请求：`CsPin:u8, CsPolarity:u8`，载荷长度固定为 2。`CsPin` 当前必须为 27；其他值返回 `ERR_SPI_CS_INVALID (0x21)`。`CsPolarity`：0=低有效，1=高有效。打开时默认 Mode 0、1 MHz、MSB 优先、8 位、自动 CS、单线。

响应：`Status:u8`。

状态变化：关闭态收到 OPEN 后进入打开态；打开态再次 OPEN 返回 `ERR_ALREADY_OPEN`。打开成功时 CS 必须处于非有效电平。OPEN 失败时设备保持关闭。

### SPI_CLOSE (`0x21`)

请求载荷为空。无论 CS 当前是否保持激活，固件先将 CS 释放到配置的非有效电平，再移除设备。响应：`Status:u8`。

关闭态收到 CLOSE 返回 `ERR_NOT_OPEN`。CLOSE 之后必须重新 OPEN 才能配置或传输。

### SPI_CONFIG (`0x22`)

请求载荷固定为 9 字节：

| 偏移 | 字段 | 类型 | 定义 |
|---:|---|---|---|
| 0 | SpiMode | u8 | 0–3：CPOL/CPHA 标准模式 |
| 1–4 | ClockHz | u32 | 大端，10,000–40,000,000 Hz |
| 5 | BitOrder | u8 | 0=MSB first，1=LSB first |
| 6 | WordSize | u8 | 0=8 位，1=16 位；16 位传输长度必须为偶数，载荷仍是原始字节序列 |
| 7 | CsMode | u8 | 0=自动 CS，1=手动 CS |
| 8 | BusWidth | u8 | 1=单线，4=Quad |

模式表：0=(CPOL0,CPHA0)，1=(0,1)，2=(1,0)，3=(1,1)。不合法值或频率越界返回 `ERR_SPI_CLOCK (0x22)` 或 `ERR_PARAM (0x02)`。Quad 只支持 8 位字宽；不支持 Quad 全双工。响应：`Status:u8`。

CONFIG 是原子更新：先释放可能保持的 CS，再应用整个新配置。成功后 CS 处于非有效电平；失败时保留原配置，若底层无法恢复旧设备配置则设备转为关闭态，之后命令返回 `ERR_NOT_OPEN`。自动 CS 在每个 WRITE/READ/TRANSFER 请求开始时有效，完成后释放；手动 CS 不由这些数据命令自动改变。

### SPI_TRANSFER (`0x23`)

只适用于单线模式。请求：`DataLen:u16, TxData:u8[N]`。固件同时发送 N 字节并采样 N 字节。响应：`Status:u8, RxLen:u16, RxData:u8[RxLen]`；成功时 RxLen=N。Quad 模式调用返回 `ERR_NOT_SUPPORT (0x06)`。

请求长度必须严格等于 `2 + DataLen`。SPI_TRANSFER 在单个 CS 周期内完成全双工交换。

### SPI_WRITE (`0x24`)

请求：`DataLen:u16, TxData:u8[N]`。响应：`Status:u8, ActualLen:u16`。成功时 ActualLen=N。适用于单线和 Quad 写事务。

SPI_WRITE 在单个 CS 周期内发送全部 N 字节。单线模式下从 MISO 移入的数据被丢弃；Quad 模式下 IO0–IO3 用作四条发送数据线，属于半双工输出阶段。请求长度必须严格等于 `2 + DataLen`。

### SPI_READ (`0x25`)

请求：`ReadLen:u16, FillByte:u8`。单线模式发送 N 个 FillByte 时钟字节并同时读取 N 字节；FillByte 由主机显式传入（通常 `0xFF`）。Quad 模式为纯接收数据阶段，FillByte 被忽略，控制器只产生 N 字节接收时钟。响应：`Status:u8, RxLen:u16, RxData:u8[RxLen]`；成功时 RxLen=N。需要设备命令/地址阶段的器件可在同一 CS 周期中用手动 CS 加 `SPI_WRITE` 发出命令/地址，然后发起读取；命令/地址阶段自身按照当前 BusWidth 发送，协议暂不支持在单次事务中切换阶段线宽。

ReadLen 必须为 1–2045，载荷长度必须恰为 3。SPI_READ 的读取阶段在一次 CS 周期内完成；自动 CS 模式下前置命令和本次读取属于不同 CS 周期，因此需要命令/地址前缀的器件必须使用手动 CS。单线读取阶段在 MOSI 发送 FillByte；Quad 读取阶段为 4 线半双工输入，IO0–IO3 均作为输入。

### SPI_CS_CONTROL (`0x26`)

仅在 `CsMode=1` 时有效。请求 `CsState:u8`：0=Assert（拉至有效电平），1=Deassert（拉至非有效电平）。自动模式调用返回 `ERR_SPI_CS_MODE (0x23)`。手动模式下，事务不会自动改变 CS；主机负责在序列结束时释放 CS。`SPI_CLOSE` 总会释放 CS。

重复 Assert 或重复 Deassert 是幂等操作。CS_CONTROL 与传输命令均受同一模块锁保护；每条命令执行期间不会被另一条 SPI 命令插入。若传输失败，自动 CS 模式仍释放 CS；手动 CS 模式保持调用前电平，主机应主动 Deassert，或通过 CLOSE 释放。

典型命令后读取：`CS Assert → SPI_WRITE(command/address) → SPI_READ(N) → CS Deassert`。单个 UBCP 请求/响应内的 SPI 操作是原子事务；不同请求之间 CS 可保持激活。

## 5.4 错误响应和参数规则

参数长度不匹配、长度为零、长度超限、16 位模式奇数长度返回 `ERR_PARAM`；设备未打开返回 `ERR_NOT_OPEN`；重复打开返回 `ERR_ALREADY_OPEN`；忙等待超时返回 `ERR_BUSY`；无效通道返回 `ERR_CHANNEL_INVALID`；无效 CS 返回 `ERR_SPI_CS_INVALID (0x21)`；频率越界返回 `ERR_SPI_CLOCK (0x22)`；底层 SPI 传输失败返回 `ERR_SPI_TRANSFER (0x20)`。失败响应只含一个 Status 字节；成功响应按相应命令格式返回。CONFIG 应用前会释放任何保持中的手动 CS。

OPEN、CONFIG 或 CLOSE 遇到底层 GPIO/SPI 驱动错误时返回通用 `ERR_HAL_FAIL (0x17)`；SPI 数据事务失败返回 `ERR_SPI_TRANSFER (0x20)`。长度、枚举和线宽不合法统一返回 `ERR_PARAM (0x02)`；Quad 下调用全双工 TRANSFER 返回 `ERR_NOT_SUPPORT (0x06)`。

未知的 `0x20–0x2F` 命令返回 `ERR_NOT_SUPPORT`。SPI 错误码定义如下：`0x20` 底层事务失败，`0x21` CS 引脚非法，`0x22` 时钟频率越界，`0x23` CS 控制与当前 CS 模式不兼容。SPI 错误码用于 `Status`，不另加错误载荷。

主机推荐初始化与事务流程：

1. `SPI_OPEN(CsPin=27, CsPolarity=...)`。
2. `SPI_CONFIG(...)` 设置模式、频率、位序、字宽、CS 模式及线宽。
3. 自动 CS 设备逐次调用 WRITE/READ/TRANSFER；需要命令加数据的设备则配置手动 CS，Assert 后执行各阶段，最后 Deassert。
4. 完成后调用 `SPI_CLOSE`。

请求字段示例（大端序）：Mode 0、1 MHz、MSB、8 位、自动 CS、单线配置为 `00 00 0F 42 40 00 00 00 01`。Quad 的线宽字段改为 `04`。示例只说明 CONFIG 载荷，不包含 UBCP 帧头、通道和 CRC。

## 5.5 当前实现边界

Quad 模式是通用 IO0–IO3 数据阶段，不包含协议特定的命令/地址位数、dummy cycles、DTR/DDR、连续读写状态或自动设备寻址。主机可用手动 CS 与 WRITE/READ 组合多个阶段，但各阶段使用相同线宽。SPI2 GPIO Matrix 支持重新映射在芯片层面成立，但此产品固定了引脚以保证接线一致，不开放动态重映射。
