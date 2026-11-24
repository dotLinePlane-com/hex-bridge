# 阶段 2 固件设计 · 配置、路由与驱动

评审稿，以下编号和格式供实施。目标为 HXB1、ESP-IDF v6.0.2。业务载荷以现有 [I²C](../protocol/06-I2C.md)、[GPIO](../protocol/12-GPIO.md) 与[错误码](../protocol/14-ErrorCode.md)为基础，板型细化如下。

## Profile v6 与迁移

沿用 DEVICE_PROFILE 的版本协商和 CHECK/SAVE/APPLY/CONFIRM/CANCEL。v6 描述能力在 v5 基础上新增 0x200（双 I²C 主机）、0x400（多路 GPIO），与 GET_INFO 的 UBCP_CAP 位分开。映射采用大端、无填充，所有保留位写零。

| 映射偏移 | 长度 | 内容 |
|---|---:|---|
| 0–33 | 34 | 原样编码 v5，含 SPI 角色和 UART1 业务选项。 |
| 34–45 | 2 × 6 | 依次 I2C0、I2C1。每条为 enabled、SCL、SDA、speed_code 四个 u8，随后 timeout_ms:u16。速率 0/1 对应 100/400 kHz，超时 1–1000 ms。 |
| 46–115 | 14 × 5 | 按逻辑路号递增。每条为 pin、flags、pull、trigger、debounce_ms 五个 u8。flags 位 0 表示启用，位 1–2 为输入/推挽/开漏（0/1/2），位 3 为初始输出锁存值。pull 和 trigger 沿用 GPIO 协议枚举。 |

新增记录默认 pin/SCL/SDA 为 FF、未启用，I²C 为 100 kHz、1000 ms，GPIO 为输入、无偏置、中断关闭。启用时必须有合法映射；停用仍校验枚举和长度，可保留合法脚。沿用原 DESCRIBE 头和 40 字节板表，响应 168 字节；READ 含状态及事务头，单快照 130、双快照 246 字节；CHECK/SAVE 请求 122 字节。与当前 256 字节配置响应区做编译期校验。诊断采用原四字节条目，23–26 为 I2C0/1 各自的 SCL、SDA，27–40 为 GPIO 路，41/42 为 I²C 实例参数。每个信号至多报告一个优先错误，复用既有原因码；响应长度须显式受缓冲区约束。

在 device_profile.c 中新增独立的 v6 编解码与带版本、校验和的 NVS 记录。先读旧长度、识别 v1–v5 并分别迁移 confirmed/candidate；保留 revision、ID、阶段和回退语义，提交成功后发布内存状态。旧版 DESCRIBE/READ 保持字节布局；只要当前、候选或回退快照包含旧版无法表达的值（含停用但已选脚），拒绝可能丢失配置的旧版事务。试用时外设驱动初始化失败走 profile_driver_failed；总线上暂时没有从设备不影响启动确认。[原配置协议](../protocol/17-Device-Profile.md)

## 路由、寻址与引脚所有权

- 建议固定通道 8、9 分别标识 I2C0、I2C1（类型 4），10、11 分别标识 GPIO 低组、高组（类型 5）。GPIO 逻辑路可改脚；拓扑仅发布至少含一条启用路的组。组基址分别为 0、32，PinNum 和掩码位都是物理脚减组基址。例如 GPIO35 为通道 11 的 PinNum 3、mask 0x08。事件同样编码。应用用当前映射还原逻辑路号。现有单字节 PinNum、32 位掩码均可复用；跨组操作需要两帧。
- mod_system 按有效实例设置 GET_INFO 的 I²C/GPIO 能力位；GET_TOPOLOGY 发布成功初始化的实例。模块按命令范围注册一次。已注册模块内查通道、设备类型，再查有效引脚、方向和会话状态。沿用总线对已关闭业务族的 PERMISSION 和无实现命令的 NOT_SUPPORT。系统现有 16 项拓扑容量可容纳 1–11 通道；注册时检查重复及溢出。
- 将 I²C 和 GPIO 映射放入与 SPI、CAN、DAP、UART 共用的整组占用校验。只有启用的对象持有引脚，输出、开漏、上下拉和中断分别检查能力。运行时 SET_DIR/SET_PULL/INT_EN 同样校验，不能借业务命令重映射、占用其他脚或绕过板级限制。

## I²C 模块

mod_i2c 依 ESP-IDF 的 bus/device 模型绑定显式硬件端口。开机为启用实例建 bus，OPEN 建立业务会话并载入该路默认参数；重复 OPEN 返回 ALREADY_OPEN。CLOSE 释放业务设备句柄及参数、保留配置的总线所有权。每路一个有界请求队列及串行执行上下文。接收端复制请求载荷、序号与 session_id 后即返回分发循环，队列满返回 BUSY。两路分别执行，慢速扫描不占另一实例的执行锁。切换传输会话后，旧队列任务失效、旧响应不进入新连接；正在执行的写入可能已生效，主机不得自动重放。

每路最多缓存一个地址/位宽/速度匹配的设备句柄。替换前完成在途事务，失败时清理临时资源，下一请求可重建。CONFIG 仅作用于已打开通道，校验成功后才替换参数。100/400 kHz 之外返回 NOT_SUPPORT；寄存器前缀 0–4 字节按载荷原序传输。READ 带前缀和 WRITE_READ 使用 transmit_receive 保证 repeated START，空前缀直接 receive。读写请求先核对精确长度、合法原始地址和响应容量（读回最多 2045 字节）；异常不返回伪造的部分成功长度。SCAN 接受 0x08–0x77 内的闭区间，仅 7 位模式可用，每个地址短时 probe，整笔受配置超时和会话取消约束，超时返回错误。地址 NACK 在扫描中跳过，在读写中报告 0x30；超时返回 TIMEOUT，总线故障和可辨识的仲裁丢失按 I²C 错误表区分。只恢复出错的控制器；故障解除后再次 OPEN/读写可恢复。不得自动重复外部写事务。[ESP-IDF I²C 驱动](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32/api-reference/peripherals/i2c.html)

## GPIO 模块

mod_gpio 在应用候选时先屏蔽中断、预置输出锁存，再配置推挽/开漏及输入采样。有效配置生效前不驱动新脚。逐路维护模式、偏置、输出锁存、触发配置与消抖状态。SET_DIR 扩充值 2 为开漏，以 v6 能力门控；WRITE 只允许输出，READ 包括输出脚实际采样。持久默认来自 Profile，业务命令改 RAM，重启还原。切换到输入时关闭输出驱动，切换到输出前撤销输入中断。

WRITE_MASK 在组锁内预检掩码涉及的所有位，任一无效、占用或非输出即整笔拒绝；合法后才更新选中位。READ_ALL 的全 1 掩码表示该组全部已启用 GPIO，返回电平和方向，其余位置零。普通显式掩码引用无效位返回错误。跨脚写允许硬件置位与清位分步完成，不承诺电气同时翻转。错误按 GPIO 专用错误区区分脚号、方向和占用。

与 CAN 共用 GPIO ISR 服务，每脚单独注册/移除处理器。ISR 只采样 GPIO、电平、时间、会话代次并投递有界队列。任务执行逐脚消抖和限速（每脚每秒最多 50 条），用帧头时间戳上报；队满计数并走现有流控，持续电平触发时屏蔽该脚直到解除后重装。支持单边沿、双边沿、单一高/低电平；混合边沿与电平拒绝。trigger=0 禁用；为消除旧文档对 debounce=0 的歧义，v6 启用时要求 1–255 ms，禁用时写 0/0。切换会话时丢弃旧事件并恢复配置默认订阅，避免事件和临时订阅串入新会话。[ESP-IDF GPIO 驱动](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32/api-reference/peripherals/gpio.html)

实施时同步 main/CMakeLists.txt、ubcp_def.h、msg_bus.c、mod_system.c、topology 和协议文档；分别覆盖模块初始化部分失败、试用回退、断线及队列回收。[应用设计](../../../tool/funcitonPinMap/design/Stage2-I2C-GPIO.md)
