# HEX-Bridge 网络调试探针（CMSIS-DAP over TCP）

## 状态

**实现状态：代码已接入；已通过 OpenOCD 对 NUCLEO-F103RB 读取 DP IDCODE、halt/寄存器访问/resume，以及 demo 固件下载和校验。** 实测只覆盖记录中的 OpenOCD 版本、目标和连接条件，不能据此宣称对其他 OpenOCD 版本或所有目标兼容。本功能是 HEX-Bridge ESP32 固件上的网络 CMSIS-DAP/SWD 探针，与 NUCLEO-64 MB1136 板载 ST-LINK、USB HID DAPLink 均不同。

| 项目 | 当前实现/状态 |
|---|---|
| TCP 服务 | Wi-Fi ready 后监听 `0.0.0.0:4441`；一个活跃客户端；网络代次变化和断开时释放 SWD GPIO |
| TCP 帧 | 8 字节 `DAP\0` 头；长度小端；request=1/response=2；保留字节为 0；载荷 1–1024 字节；支持拆包、粘包和短写 |
| CMSIS-DAP | 已实现 Info、Host Status、Connect/Disconnect、Transfer Configure、Transfer、TransferBlock、Transfer Abort（同步引擎无在途传输）、Write ABORT、Delay、Reset Target（报告无硬件 reset sequence）、SWJ Pins/Clock/Sequence、SWD Configure |
| 能力声明 | `DAP_Info(0xF0)` 仅声明 SWD；包数 1、包长 1024。未声明 JTAG、SWO、原子命令或时间戳 |
| GPIO | `main/hex_config.h` 配置 SWCLK GPIO25、SWDIO GPIO26；默认约 100 kHz，请求频率限制在 10–250 kHz，GPIO 调用开销可能使实际频率更低 |
| 复位 | GPIO27 预留但 `HEX_SWD_RESET_ENABLED=0`。无硬件复位线时只可依赖 SWD/软件复位路径 |
| 硬件验证 | 2026-11-20：TCP/DAP_Info/UBCP 并发通过；OpenOCD 读取 STM32F103 DP IDCODE、halt、PC/SP 寄存器访问、resume，以及 demo 下载和校验通过；断开后物理引脚电气释放、真实 CAN 帧与 DAP 并发仍未确认 |

## 服务及资源规则

DAP 服务由 `main/main.c` 启动，在网络获得 IP 后开始监听。服务任务独占命令引擎和 SWD GPIO；忙时关闭新连接。失去网络或客户端断开时丢弃半帧、调用 `dap_release()`，并将 SWDIO/SWCLK（及启用时的 nRESET）设为输入浮空。当前无目标复位线。

DAP 引擎不持有 UBCP 总线锁。服务在命令处理后让出调度，避免长 SWD 操作或连续请求长期占用 CPU。传输请求/响应最大 1024 字节；无效签名、类型、保留位、空载荷、超长载荷或半帧断开时结束会话。慢写入有超时。

## TCP 帧格式

每帧以 8 字节头开始：字节 0–3 为 `44 41 50 00`，字节 4–5 为载荷长度（小端，包含 CMSIS-DAP 命令字节），字节 6 为类型（请求 1、响应 2），字节 7 为保留位（0）。接收端按头部长度组帧，不假定一次 `recv` 对应一帧；发送端循环处理短写。非法帧终止当前连接并清理会话状态。

## SWD 行为与限制

SWDIO 仅在时钟低电平变化；目标响应阶段切换为输入，发送阶段再驱动。引擎检查 ACK 和读数据奇偶校验，响应 WAIT 重试并有次数/时间限制，FAULT 作为错误返回。AP 访问会处理 posted read/deferred write fault。GPIO 实际边沿、频率、目标负载下的稳定性仍须实测确认。

未实现 USB HID/Bulk、JTAG、SWO、固件烧录流程及硬件 nRESET（默认关闭）。代码中的命令覆盖不等于 OpenOCD 后端兼容认证；只有完成指定版本与目标的端到端验证后才更新兼容状态。

## 接线与只读验证

依据 [ESP32 引脚规划](../../sch/esp32-pinout-design.md) 接线：ESP32 GPIO25→目标 SWCLK、GPIO26↔目标 SWDIO、共地；目标板按自身方式供电，使用 3.3 V 逻辑。NUCLEO-F103RB 实测使用 CN7 pin 15 (PA14/SWCLK)、pin 13 (PA13/SWDIO)、pin 8 (GND)。CN4 是板载 ST-LINK 的外部调试连接器，不是连接到板上 F103 的直连接口；接 CN4 时需考虑 CN2 跳线对 ST-LINK 路由的影响。GPIO27 仅在启用复位支持并配置开漏接线后使用。NUCLEO-64 MB1136 板载 ST-LINK 与此网络探针无关，不应将其 UID 或连接结果记为 HEX-Bridge DAP 结果。

验证前记录 ESP32 固件版本/构建、Wi-Fi IP、目标板型号及版本、OpenOCD/CMSIS-DAP 客户端版本、接线、SWD 时钟与完整日志。先查询 DAP_Info，再连接 SWD 并读取 DP IDCODE，然后 halt、读取目标/CPU 寄存器、resume，断开后确认引脚释放。暂停目标会暂时中断目标固件活动；不要执行擦除、下载、内存写入或其他改写目标状态的命令，除非用户明确授权。并发验证应记录 CAN/UART 实际活动及 DAP 请求结果。无实测证据的项目保持“未验证”。

## 本地测试

- 命令引擎 host harness：`python main/dap/test_dap_engine_host.py <native-C-compiler> [compiler args]`
- TCP framing host harness：编译 `main/dap/dap_stream.c` 与 `script/test/dap_stream_test.c`，按测试源文件注释中的命令运行。
- 实板 TCP framing/Info：`python script/test/test_dap_tcp.py --host <HEX-Bridge-IP>`；`--ubcp` 额外并发检查 TCP9500 UBCP PING。此脚本不执行 SWD 目标访问。

## 实板记录（2026-11-19）

- 探针：HEX-Bridge ESP32 网络 CMSIS-DAP（非 Nucleo 板载 ST-LINK）；TCP `192.168.1.112:4441`；DAP_Info 产品名 `HEX-Bridge`，FW 字段 `2.0.0`，能力为 SWD，包数 1、包长 1024。
- 目标：NUCLEO-F103RB，MB1136 C-04，目标 MCU STM32F103RBT6（按用户提供型号）。
- 工具：OpenOCD `v0.12.0-esp32-20260424`；CMSIS-DAP TCP backend；SWD 请求时钟 100 kHz（另用原始 CMSIS 命令在 10 kHz 复测）。
- 通过项：`python script/test/test_dap_tcp.py --host 192.168.1.112 --ubcp` 输出 framing/busy-client/malformed/reconnect PASS 和 TCP9500 UBCP PING 与 DAP_Info 并发 PASS。OpenOCD 显示 `SWD supported`、`FW Version = 2.0.0`、`Interface Initialised (SWD)`。
- 失败项：OpenOCD target examine 输出 `Error connecting DP: cannot read IDR`。手动发送 SWD line reset、SWD select `0xE79E`、idle 后读取 DP IDCODE，CMSIS-DAP Transfer 返回 `05 00 08`；原始 SWD 请求后的 turnaround+ACK 输入采样为 `0x0F`（四位均高，未观察到目标 ACK）。10 kHz 与 100 kHz 均失败。
- 下载尝试：经 HEX-Bridge DAP 执行 OpenOCD `program demo-firmware/demo.bin 0x08000000 verify reset exit`，在 `dap init`/DP IDR 阶段失败，未到擦除/写入阶段；目标固件未改写。板载 ST-LINK VCP COM8 只读观察 3 秒，没有收到 UART 输出；这不能单独证明目标未运行。
- 未完成：DP IDCODE（预期 `0x2BA01477`）、CPU halt/寄存器读取/resume、成功下载与校验、断开后的物理引脚电气状态、真实 CAN/UART 活动与 DAP 并发。
- 结论与下一步：网络 framing 和探针信息正常，目标 DP 没有应答，现有证据不足以把问题归因到 SWD GPIO 时序或目标接线。继续前需在目标侧确认供电/VDD、共地及连接点：NUCLEO-F103RB 的 PA13/SWDIO 与 PA14/SWCLK 应接到探针 GPIO26/GPIO25；若仍失败，测量 SWDIO/SWCLK 空闲电平并检查目标 nRESET 是否被保持为低。ST 官方 [UM1724 Nucleo-64 MB1136 用户手册](https://www.st.com/resource/en/user_manual/dm00105823-stm32-nucleo64-boards-mb1136-stmicroelectronics.pdf)列出 CN7 pin 13=PA13、pin 15=PA14、pin 8=GND、pin 14=RESET。

### 2026-11-20 复测

- UART1 状态确认 HEX-Bridge 仍连接 `CU_Jm2v`，IPv4=`192.168.1.112`。DAP TCP framing/Info 和 UBCP 并发脚本再次通过。
- 重新发送 SWD line reset、SWD select、idle 和 DP IDCODE read，100 kHz 下仍返回 `05 00 08`；改用 10 kHz/100 kHz 并遍历 turnaround 1–4 周期，结果相同。
- 原始 `DAP_SWD_Sequence` 请求后 turnaround+ACK 窗口读为 `0x00`（采样全低），不是合法 ACK。OpenOCD `v0.12.0-esp32-20260424` 再次报告 `cannot read IDR`。
- 再次尝试 `program demo-firmware/demo.bin 0x08000000 verify reset exit`，仍在 `dap init` 阶段失败；没有出现 erase/write/verify 操作，STM32 Flash 未改写。
- 当前仍需目标侧电气检查或确认应用是否关闭/复用 PA13/PA14。尚未执行 halt、寄存器访问、resume 或成功下载。
- 用户重新插接 SWD 线后再次复测：DAP TCP/Info 和 UBCP 并发仍通过；Transfer 仍返回 `05 00 08`，OpenOCD STM32F1 target examine 仍为 `cannot read IDR`。重新插接尚未恢复 DP 应答。

### 2026-11-20 CN7 接线后成功实测

- 接线改为 ESP32 GPIO25→NUCLEO CN7 pin 15 (PA14/SWCLK)、GPIO26↔CN7 pin 13 (PA13/SWDIO)、共地 CN7 pin 8。此前 CN4 的 2/3/4 是板载 ST-LINK 外部连接器信号，未能让 HEX-Bridge 直接访问板上 MCU；改用 CN7 后目标开始应答。
- 实际硬件：HEX-Bridge ESP32 网络 CMSIS-DAP，IP/端口 `192.168.1.112:4441`；NUCLEO-F103RB MB1136 C-04、STM32F103RBT6；OpenOCD `v0.12.0-esp32-20260424`，`cmsis-dap-tcp` backend。固件版本字段 `2.0.0`；DAP_Info 能力 SWD、packet count 1、packet size 1024。实测 SWD 时钟 100 kHz 和 250 kHz。
- CMSIS-DAP 直接 DP 读回 `0x1BA01477`。OpenOCD target examine 成功，识别 Cortex-M3 r1p1、6 个硬件断点和 4 个 watchpoint。OpenOCD TCP backend 在运行时仍打印若干 `error reading header`/`WSAEWOULDBLOCK` 噪声，虽然目标检查及后续操作成功；应继续调查其非阻塞读取日志。
- Halt 后成功读取 PC（约 `0x08000124`）和 SP (`0x20002000`)，随后执行 resume；通过后续重新 halt 取得 PC 读数，说明寄存器访问和恢复执行路径已实测。halt 会短暂中断目标应用运行。
- 目标固件：`demo-firmware/demo.bin`，560 bytes。OpenOCD `program ... verify` 在 100 kHz 下报告 `Verified OK`，program+verify 命令耗时 3049 ms，约 184 B/s (0.179 KiB/s)；250 kHz 下报告 `Verified OK`，耗时 2728 ms，约 205 B/s (0.200 KiB/s)。此数值含目标 flash 擦除、编程和读回校验，不是原始 TCP 吞吐或纯写入速度。完整 OpenOCD 进程约 15 秒，包含启动、连接和目标探测，不用作传输速率。此下载由用户明确授权；没有擦除整片，仅 OpenOCD 显示需要的目标 flash 范围操作。
- demo 下载后板载 ST-LINK VCP COM8 只读读取到重复的 `CAN Heartbeat 0x321 sent, System OK.` UART 日志，证明应用在目标上运行；该日志表示固件尝试发送 CAN，不能证明总线上实际出现 CAN 帧。PCAN 监听验证尚未记录结果。
- `python script/test/test_dap_tcp.py --host 192.168.1.112 --ubcp` 通过 framing、busy-client、malformed-frame、disconnect/reconnect，以及 TCP9500 UBCP PING 与 DAP_Info 并发检查。OpenOCD 端到端实测说明该版本/backend 对此目标的基本连接、检查、halt/寄存器访问、resume 和下载校验可用，不构成通用兼容性承诺。
- 尚未通过示波器/万用表确认 `dap_release()` 后 SWD 引脚电气状态，也未证明真实 CAN 线上帧及 CAN/UART 活动与 DAP 并发互不干扰。
