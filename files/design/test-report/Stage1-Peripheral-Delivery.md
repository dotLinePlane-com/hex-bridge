# HXB1 可选外设阶段 1 交付记录

2026-11-21。工作区起点为 `000b955` 加现场未提交文件。使用 ESP-IDF 6.0.2、ESP32-D0WD-V3、COM3 控制口 115200、COM5 下载口 460800 及 COM9 CANable。烧录前从控制口导出配置，核实下载口芯片 MAC 与控制口读数一致。默认接线在全过程保持原样。阶段 2–4 未实施。

| 项目 | 验证方法与读数 |
|---|---|
| 1.1 基线与协商 | 在升级前使用新 CLI 读取真实 v1 板，得到 HXB1、9 个可改配 GPIO、修订 22、已确认 ID 20、无候选。关闭 DAP 的草稿通过 CHECK，SAVE 后当前 DAP 仍开启，取消后修订 24。冻结报文、非默认 JSON、版本回退与非法版本另见 `script/test/fixtures/profile` 和 `test_profile_examples.py`。 |
| 1.2 迁移及恢复 | 烧录后从 COM3 协商到 v2。把升级前导出文件按 v1 迁移规则转换，与实板 active 整份比较相等。C 回归直接编译固件处理器，覆盖旧 NVS 状态、损坏、提交失败、重试、丢失扩展字段的旧写入和回退。 |
| 1.3 管理与试用 | 设备原先未联网。关闭 UART1 且仅留 Wi-Fi 管理的 CHECK 返回“缺少已保存配网参数”。C 主机回归覆盖 FORGET、回退入口、启动未就绪、错误入口及陈旧会话。实板保留 UART1，另用临时连接验证网络服务。 |
| 1.4 两个 SPI 主机 | 默认 SPI2 Quad 配置下，真实 SPI OPEN、单线 CONFIG/TRANSFER、Quad CONFIG、Quad 全双工拒绝、CLOSE 完成。SPI2 单线试用时拒绝 Quad。未接已确认的 SPI 数据从机，测试断言覆盖 UBCP 状态和长度。驱动主机测试额外检查 GPIO 调用、CS 仲裁及失败清理。 |
| 1.5 CLI 事务 | 通过原 CLI 入口导出、导入、CHECK、SAVE、CANCEL、APPLY、CONFIRM。保存单线候选后当前占用仍为 15/15，候选为 13/15。进入试用后空闲脚恰为 22、23，从试用读数起 **120.6 秒**后实板回到旧 Quad 映射。再停用外接业务和 SPI2，试用后确认 9/15 占用，空闲为 18、19、21、22、23、27。恢复原图后修订 35、确认 ID 33。 |
| 1.6 Tkinter | 同组协议样例通过真实 Tk 控件回归，包含旧板九脚、三个视图、切换线宽、禁用、修订冲突及换板保护。真实 Tk 读取按钮通过 COM3 读到 HXB1 v2、17 个信号控件、7 个主机及挂载参数、15 占用 0 空闲。UI 回归 33/33 通过。 |

## CAN 与接线

**总线问题排除后复测（COM3 控制口、COM9 CANable，未换线）。** 下表中的 414 PASS、1 FAIL 是历史基线。最新实测如下：

| MCP2518FD 拓扑 | 完整 CANable 回归 | 500 → 250 → 500 kbps |
|---|---|---|
| 默认 SPI3，原接线 | 421 PASS / 0 FAIL / 1 SKIP | 通过，250 kbps 的 `0x601 World` 数据匹配 |
| 共享 SPI2，GPIO 矩阵沿用原 CAN 接线 | 421 PASS / 0 FAIL / 1 SKIP | 通过，同一帧数据匹配；共享 SPI 单线命令冒烟通过 |

两次均仅跳过 CANable 接收端不能上报的 FD+BRS 帧，发送侧 TEC=0、AckErr=0。试验结束后读回默认配置：已确认，修订 144，确认 ID 142，无候选；生效配置与测试前逐字段一致。此结果不覆盖改接 SPI2 默认 GPIO18/19/21 的电气测试，也不属于片上 TWAI 的测试。

首次整套验收发现，SPI2 和外接业务同时关闭时，SPI3 上的 MCP2518FD 会在启动探测中读回 `0xFE` 并触发回退。保留 SPI2 主机、仅停外接业务时同一探测成功。延长启动等待不能消除故障。把 HXB1 的 SPI2 固定到 DMA1、SPI3 固定到 DMA2 后，同板同线连续三轮关闭 SPI2 均能试用并确认，错误主机仍触发回退。主机测试也断言这两个 DMA 参数。

| SPI 实例及电气连接 | 结果 |
|---|---|
| 历史 v1，默认 SPI3 | 升级前现场复跑 407 PASS、1 FAIL、1 SKIP。250 kbps 切速后的 0x601 未收到；适配器对 FD+BRS 帧的主机上报有单独跳过项。 |
| v2，默认 SPI3、原接线 | 414 PASS、1 FAIL、1 SKIP。在 500 kbps，经典帧与 64 字节无 BRS 的 FD 帧双向逐字节通过。FD+BRS 发送方报告 TEC=0、AckErr=0；CANable 向桥发送的 BRS 帧通过标志和数据断言。250 kbps 切速用例和适配器 BRS 上报与 v1 基线相同。停止 HEX 测试发帧后，COM9 静默监听 500 kbps 仍收到 ID 0x321；当前接线不是隔离双节点测试台，切速失败原因未证实。 |
| v2，将 MCP2518FD 改到 SPI2 默认 GPIO18/19/21，保持原接线 | 试用驱动探测失败，设备自行重启回到原 SPI3 配置，修订 38。此项验证驱动失败回退。 |
| v2，共用 SPI2，将 GPIO 矩阵映射到原 CAN 线 14/13/36 | MCP2518FD 使用 CS15/INT39，通用 SPI 使用 CS27，SPI3 关闭；实际进入试用并确认。共享主机的通用 SPI 单线命令冒烟通过。CANable 回归 414 PASS、1 FAIL、1 SKIP，失败和跳过项与上述旧固件相同。测试后恢复默认主机并读回，修订 44。 |
| v2，改动跳线，将 MCP2518FD 接到 SPI2 默认 GPIO18/19/21 | 保留现场接线，此项经典帧和 FD 帧双向电气测试待换线后执行。 |

## 最终固件与管理入口

- `build/hex-bridge.bin` 为 920272 字节，SHA-256 为 `0ea61a7458334ce1a361723c8417d8d88537e6da0e107f0ffcb4411757e70639`。COM5 烧录并校验成功。
- 只读检查最初的 NVS，确认没有有效的 `hex_wifi/sta` 键。使用临时配网记录后同时关闭 UART1 和普通 TCP，实板仅通过 TCP 9500 进入试用、读取及确认。试用期和确认后发 WIFI_FORGET 均收到权限错误 0x0C，下一次 READ 成功。
- 通过 TCP 9500 申请恢复 UART1。实测发现早期固件在 TCP APPLY 回包发送后立即重启会丢失回复。最终固件在回复后半关闭 TCP 并有界等待，实板 CLI 收到 APPLY 回复。试用中从 TCP 确认新增 UART1 返回 0x0C，此时 FORGET 也被拒绝，从 UART1 确认成功。恢复原配置后只移除本次临时添加的配网记录。
- 真实 Tk 在单线试用修订 113 读到 17 个信号、13 脚占用、2 脚空闲；同时在单线配置上实测拒绝 Quad 请求。GPIO4/34 的板级保留由扩展描述与 C 校验回归核对。
- 最终固件使用仓库入口 `test_profile_board.py --shared --wrong-host` 完整通过，在修订 129 读回原 Quad、无候选及原拓扑（UART2 通道 1、CAN 通道 3、SPI 通道 4）。
- 随后在最终镜像上分别复跑默认 SPI3 与共享 SPI2 的 CANable 业务，两者均为 414 PASS、1 FAIL、1 SKIP。最后恢复默认主机并硬复位，CLI 与 Tk 读回 **修订 138、确认 ID 136、无候选、15 占用**。CLI 逐字段比较 active 与升级前导出按 v1 规则迁移的结果，相等。NVS 元数据核对原配网键为空，NET_STATUS 恢复为断开。

## 网络、会话、UART 和调试回归

| 入口 | 本次实测 |
|---|---|
| `test_network.py --auto` | 联网时 95 PASS、0 FAIL、3 SKIP。离线单独运行 TCP-29、UDP-14、WS-18，各 2 PASS，覆盖联网时跳过的全部六个请求。 |
| `test_cli_network_e2e.py` | 使用真实 PC 套接字及板端连接，26 PASS、0 FAIL。 |
| `test_ubcp_sessions.py` | UART1、TCP 接管及回退、半帧清理、第二客户端拒绝、Wi-Fi 断开/重新连接、旧会话隔离通过。UART2 注入事件需要独立对端；未接 PCAN，此次 CAN 对端为 COM9 CANable。 |
| `test_dap_tcp.py --ubcp`、SWD | TCP4441 DAP 与 TCP9500 PING 并行通过。通过 HEX-Bridge 的 DAP/SWD 在原 GPIO25/26 上以 100 kHz 实际读到目标 DP IDCODE `0x1BA01477`。 |
| `test_uart.py --no-ext` | UART2 控制、配置及状态 105 PASS、0 FAIL、14 SKIP。14 个检查需要独立 UART2 收发对端，本次没有确认该连线。 |

## 可复跑命令

| 交付项 | 主要修改文件（相对仓库根目录） |
|---|---|
| 1.1 | `files/design/protocol/17-Device-Profile.md`，`script/test/fixtures/profile/{v1-nondefault,v2-default,wire-examples}.json`，`script/test/test_profile_examples.py` |
| 1.2 | `main/core/device_profile.{c,h}`，`script/test/test_profile_host.py`，`script/test/test_profile_v2_host.py` |
| 1.3 | `main/main.c`，`main/modules/mod_network.c`，`main/transport/mcp_transport.{c,h}`，`script/test/host/test_ubcp_sessions.c`，`script/test/test_ubcp_sessions{,_host}.py` |
| 1.4 | `main/core/spi_bus_manager.{c,h}`，`main/modules/{mod_spi,mod_can,mod_system,mcp2518fd}.c`，`main/modules/mcp2518fd.h`，`main/core/msg_bus.c`，`main/CMakeLists.txt`，`script/test/test_spi_{host,smoke}.py`，`script/test/test_canable{,_switch_host}.py` |
| 1.5 | `script/hexbridge_profile.py`，`script/cli/hex-bridge-profile.py`，`script/test/test_profile_cli_host.py`，`script/test/test_profile_board.py` |
| 1.6 | `tool/funcitonPinMap/{app,backend,test_app,verify_readonly}.py`，`tool/funcitonPinMap/DESIGN.md` |

同步中英文 README、板级接线、设备配置功能、SPI 功能/协议、CAN 模块、Wi-Fi 协议及网络验收说明。网络回归脚本另更新 `script/test/test_network.py`、`script/test/test_cli_network_e2e.py` 和 `script/test/test_network_timing_host.py`。

| 主机验收入口 | 成功与拒绝路径 |
|---|---|
| `test_profile_examples.py` | 冻结报文、协商、JSON 迁移、表结构共 7 项通过；损坏长度、非法布尔字段、READ 阶段与候选 ID 矛盾均拒绝。 |
| `test_profile_host.py`、`test_profile_v2_host.py` | 编译实际固件 C 处理器。覆盖独立校验和、旧试用中断、重复提交、维护入口、关闭仍被引用的主机、重复 CS、GPIO15 专用和输入脚作 Quad 输出。 |
| `test_profile_cli_host.py` | CLI 对实际 C 处理器 13/13 通过，包含 v1/扩展版完整事务、文件元数据伪造、过期修订和恢复。 |
| `test_spi_host.py` | 编译实际主机管理器和两个设备驱动，断言共享时只初始化一次、独立 CS、单线配置拒绝 Quad 时无 GPIO 操作、失败后释放总线及资源、移走最后挂载后保留已启用的空总线。 |
| `test_app.py` | Tk 与服务层 33/33 通过。对同一组 CLI 样例检查单线/Quad、候选与草稿、修订冲突、同端口换板拦截。 |
| `test_ubcp_sessions_host.py --cc cl`、`test_wifi_host.py` | 会话 12 个场景及 Wi-Fi 主机 11 项通过，包含 TCP 接管时过期响应隔离。 |

在仓库根目录运行。C 主机回归须使用 VS x64 Developer PowerShell 或先运行 `D:\BuildTools\VS2022\VC\Auxiliary\Build\vcvars64.bat` 的 cmd 环境。

```powershell
python script/test/test_profile_examples.py
python script/test/test_profile_host.py
python script/test/test_profile_v2_host.py
python script/test/test_profile_cli_host.py
python script/test/test_spi_host.py
python script/test/test_canable_switch_host.py
python script/test/test_wifi_host.py
python script/test/test_ubcp_sessions_host.py --cc cl
python tool/funcitonPinMap/test_app.py
python tool/funcitonPinMap/verify_readonly.py --port COM3 --baud 115200
cmd /c "D:\project\esp-idf-v6.0.2\export.bat && idf.py build"
python script/cli/hex-bridge-profile.py --port COM3 --baud 115200 pins --human
python script/test/test_spi_smoke.py --mcp COM3 --baud 115200 --cs 27 --max-width 4
python script/test/test_profile_board.py --port COM3 --baud 115200 --wrong-host --shared
python script/test/test_canable.py --mcp COM3 --mcp-baud 115200 --canable COM9 --baud 500k
python script/test/test_uart.py --mcp COM3 --mcp-baud 115200 --no-ext
python script/test/test_network.py --mcp COM3 --mcp-baud 115200 --auto
```

在无 IP 时逐项重跑离线断言。纯 Wi-Fi 管理验收用 CLI 导出当前配置，将 `features.serial` 与 `features.tcp` 关闭，保留 `features.wifi` 与 `features.control_tcp`；CHECK 通过后 SAVE、APPLY，经 `--port socket://<板端IPv4>:9500` READ 并确认。没有已保存的可用配网记录时 CHECK 应拒绝保存。这一操作只适用于已备份配置且具备对应管理入口的实板。

```powershell
foreach ($case in 'TCP-29','UDP-14','WS-18') {
    python script/test/test_network.py --mcp COM3 --mcp-baud 115200 --test $case
}
```

先用 NET_STATUS 查询板端 IP，下列命令中的 `$ip` 取本次读数。

```powershell
python script/test/test_cli_network_e2e.py --mcp COM3 --mcp-baud 115200 --esp-ip $ip
python script/test/test_ubcp_sessions.py --uart COM3 --baud 115200 --host $ip
python script/test/test_dap_tcp.py --host $ip --ubcp
```

复核 SWD 时，沿用 `script/test/test_dap_tcp.py` 的 `frame`、`response`，向 TCP 4441 依次发送以下 CMSIS-DAP 载荷。过程仅选择 SWD、读取 DP IDCODE 并断开。

| 请求（十六进制） | 操作 / 预期响应 |
|---|---|
| `02 01`、`11 A0 86 01 00` | SWD 连接，时钟 100 kHz；响应 `02 01`、`11 00` |
| `12 38 FF FF FF FF FF FF FF`、`12 10 9E E7`、再发一次前述 56 位全 1，接 `12 08 00` | 复位线序、JTAG 到 SWD 选择及空闲位；每次响应 `12 00` |
| `05 00 01 02`、`03` | 实测响应 `05 01 01 77 14 A0 1B`、`03 00` |
