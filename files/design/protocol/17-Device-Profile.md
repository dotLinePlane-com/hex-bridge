# UBCP 设备功能与引脚配置 v1 / v2

系统命令 `DEVICE_PROFILE = 0x08`，ChannelID 为 0。使用原有 UBCP v2 帧、CRC、序号和响应规则。所有多字节整数按大端编码，长度必须精确匹配。下列 v1 请求以 `01 Op` 开头，响应首字节是 Status；阶段 1 的 v2 请求以 `02 Op` 开头，完整契约见文末。旧固件可通过 DESCRIBE 返回的 NOT_SUPPORT 识别。上位机通过原有 GET_CONFIG/SET_CONFIG 管理串口速率。

## 报文

本节定义已实现的 v1 线上格式。多外设目标模型及迁移约束见本文末节。

下表仅列出请求公共头和响应 Status **之后**的内容。Rev 和 ID 均为 u32，0 表示无候选或尚无已确认 ID。Rev 为整个配置事务的修订号，初值 1；每次保存、取消、应用、确认或回退后须重新读取。

| Op | 操作 | 请求参数 | 成功响应 |
|---|---|---|---|
| 0 | DESCRIBE | 空 | 版本 u8、板型 ASCII[4]、出厂映射 M、GPIO 策略 u8[40] |
| 1 | READ | 空 | 阶段 u8、Rev、候选 ID、已确认 ID、运行映射 M；有候选时追加候选 M |
| 2 | CHECK | Rev、M | 空 |
| 3 | SAVE | Rev、M | 候选 ID |
| 4 | CANCEL | 候选 ID | 空 |
| 5 | APPLY | 候选 ID | 空，随后设备重启试用 |
| 6 | CONFIRM | 候选 ID | 空 |

每个映射 M 为 11 字节。前两字节为功能掩码，bit 0–8 依次为 UART1 控制、TCP 9500 控制、CAN、UART2、Wi-Fi STA、普通 TCP、UDP、WebSocket、DAPLink。后九字节为 GPIO 编号，信号索引 0–8 依次为 UART2.TX、UART2.RX、CAN.SCK、CAN.MOSI、CAN.MISO、CAN.CS、CAN.INT、DAP.SWCLK、DAP.SWDIO。出厂 M 为 `01 FF 20 23 0E 0D 24 0F 27 19 1A`。例如首次读取 Rev=1 后，关闭 DAP 并把 UART2 移至 GPIO25/26 的完整 CHECK 载荷是 `01 02 00 00 00 01 00 FF 19 1A 0E 0D 24 0F 27 19 1A`。CHECK 不写 Flash。

GPIO 策略按 GPIO0–39 顺序返回，一字节一个。0 为未引出或不存在，1 可用作输入或输出，2 仅输入，3 仅允许 CAN.CS（GPIO15 需维持上电偏置）。4/5 为 UART0 TX/RX，6/7 为 UART1 TX/RX，8 为 Flash，9 为 PSRAM，10 为 SPI2，11 为板载 EEPROM，12 为启动绑带保留。4–12 都是板级固定资源。固定信号的映射和策略只存在于 DESCRIBE，不占用 M 的字段。增加字段、把业务信号指向固定脚均会被设备拒绝。

## 校验及错误

### 从 v1 报文生成三张引脚表（上位机设计）

沿用现有报文长度。主机先读一次 DESCRIBE，再用一次 READ 取得同一快照中的阶段、Rev 和映射。三张表按下列规则生成，名称用于界面或主机程序，不新增可写的线协议字段。

| 数据 | 生成规则 | 写权限 |
|---|---|---|
| 系统固定引脚 | 遍历 DESCRIBE 的 GPIO 策略，4–12 逐项返回 GPIO 和固定用途。策略 0 表示不存在或未引出，单列为不可用。 | 固件板表只读。主机不得从导入文件重建或覆盖板表；固件在校验、保存和启动时以自身板表为准。 |
| 可修改引脚 | 每个信号列出索引、所需方向、所选 GPIO 和合法候选。策略 1 适用符合要求的信号，策略 2 仅适用 UART2.RX、CAN.MISO、CAN.INT，策略 3 仅适用 CAN.CS。CAN.INT 要求输入并支持 GPIO 中断，SWDIO 要求双向。 | 用户通过 M 的九个信号字段改映射。SCK、MOSI、MISO、CS、INT 分别使用索引 2–6；板表中 GPIO15 的限制仅作用于该脚，CAN.CS 仍可选择策略 1 的 GPIO。 |
| 当前占用 | 先放入全部系统固定引脚，再遍历 READ 的运行映射 M。对每个功能位已开启的信号，填入 GPIO → 功能、信号索引。其余可分配 GPIO 标为空闲。 | 查询结果只读，不单独写 NVS。按功能启用状态判断占用，不依赖瞬时电平、外设 OPEN 状态或哪条控制链路正持有会话。 |

展示候选配置时，用相同规则对候选 M 单独计算“应用后占用”。CHECK、SAVE 不改变当前占用；试用启动后用试用 M，回退启动后用已确认 M。校验冲突时以整份候选 M 为单位，允许一次交换两个合法 GPIO。用户若选择原本已占用的引脚且保留原占用方，则返回原因 6；选择固定脚则返回原因 5。导出文件可附带固定策略供核对，提交载荷只包含 Rev 和 M，不接受客户端提供的固定表或占用表作为分配依据。

### 错误记录

开关依赖、信号方向、板级预留均校验；只对启用功能检查互相占用。纯网络控制要求有可恢复的已保存 Wi-Fi 配置。CHECK、SAVE 和 APPLY 的配置校验错误返回 `02 N` 加 N 个四字节记录 `reason subject gpio other`，不适用字段填 FF。

| reason | 含义 | subject / gpio / other |
|---|---|---|
| 1 | 未知功能位 | FF / FF / FF |
| 2 | 没有控制入口 | FF / FF / FF |
| 3 | 需要启用 Wi-Fi | 依赖方功能位序号 / FF / FF |
| 4 | 纯网络控制缺少已保存的配网参数 | 1 / FF / FF |
| 5 | GPIO 固定、不可用或方向不符 | 信号索引 / GPIO / FF；占用方查板表 |
| 6 | 两个启用的信号争用 GPIO | 信号索引 / GPIO / 另一个信号索引 |

其他失败只返回 Status。02 表示载荷错误，04 表示当前阶段不允许操作，0E 表示 Rev 或 ID 已过期，0F 表示版本不支持，0C 表示确认入口不符，03 表示试用已过期，01 表示持久化失败。针对关闭的业务模块，设备返回 0C。主机可以使用 READ 了解当前状态。

## 状态与程序设计

- 阶段 0 已确认，1 已暂存，2 等待试用重启，3 试用中。SAVE 支持按最新 Rev 替换候选；使用原 Rev 重发相同 SAVE 返回原候选 ID。CONFIRM 可用刚确认的 ID 重发。试用期间再次 APPLY 同一 ID 不延长时限。
- `main/core/device_profile.c` 管理板表、整组校验及状态转换。独立 NVS 分区以单个版本化记录保存确认配置、候选配置和事务编号，NVS 提供完整性检查。写入并提交成功后才更新内存状态。启动时先持久记录“已进入试用”，再启用候选；试用复位、启动失败或 120 秒内未确认均回退。恢复时仍按固件板表校验。新增控制入口必须由该入口确认。
- `main/main.c` 按有效开关注册并初始化模块，系统配置始终可达。UART1 固定使用 GPIO4/34；UART0 固定使用 GPIO1/3。UART2、CAN、SWD 驱动从同一有效配置读取各自信号。外接 SPI2 沿用已有功能和接线，EEPROM 和内部存储引脚按[当前板型接线表](../../sch/esp32-pinout-design.md)保留。
- 沿用原 NVS（0x9000）、PHY（0xF000）和应用（0x10000）偏移。新分区 `profile` 起于 0x110000，长 0x4000。首次安装须随应用更新分区表。网络控制失联时，可经 UART0 进入下载模式，只擦除该板型的 profile 分区，然后重启；Wi-Fi 凭据及 UART1 波特率仍在原 NVS 中。使用旧分区表时设备采用默认映射，保存配置会报告存储错误。

## 上位机操作

以下命令在仓库根目录执行。默认 COM4、115200；可在子命令前传 `--baud`，或用 `--port socket://设备IP:9500`。导出后只编辑 features 和 pins。show 同时展示当前映射、候选、板级占用和版本。

```powershell
python script/cli/hex-bridge-profile.py pins
python script/cli/hex-bridge-profile.py pins --json
python script/cli/hex-bridge-profile.py export device.json
python script/cli/hex-bridge-profile.py check device.json
python script/cli/hex-bridge-profile.py pins --file device.json
python script/cli/hex-bridge-profile.py save device.json
```

`pins` 显示固定用途、九个可配置信号及当前占用。`pins --json` 和 `show` 返回结构化结果，三张表位于 `tables`。编辑导出的 JSON 后，`pins --file` 可以对照当前占用与应用该文件后的占用。保存后直接运行 `pins` 可查看设备暂存的候选。

将 SAVE 返回的整数代入下例（例如 2）。应用前也可用 `cancel 2` 撤销。试用时按新接线验证业务，再确认。

```powershell
python script/cli/hex-bridge-profile.py apply 2
python script/cli/hex-bridge-profile.py show
python script/cli/hex-bridge-profile.py confirm 2
```

## 多外设配置目标与迁移边界

保留 v1 的命令、11 字节映射、既有通道 ID 和 JSON 语义。通过显式版本协商提供扩展描述与完整快照；旧固件继续走 v1。扩展不把新增功能塞入既有位或信号索引。新主机依据固件返回的能力渲染界面。阶段 1 的 v2 编码在下节固化；其余外设仍为后续目标。

| 配置对象 | 扩展描述和快照需要表达的内容 |
|---|---|
| 板型与能力 | 固定资源、可分配 GPIO、方向/中断/开漏/固定路由限制；区分硬件支持、固件已实现、已启用及运行状态。 |
| 外设实例与通道 | 稳定的功能类型、实例及通道标识；SPI2/3、I2C0/1、UART1/2、TWAI 和外接 CAN FD 分别寻址；LEDC 0–15、PCNT 0–7 可逐路选择，MCPWM 描述组及输出对，以太网引用板型 PHY 能力。 |
| 资源关系 | 每个信号的 GPIO、角色和方向；SPI 设备引用主机并声明独立 CS，MCP2518FD 还声明 INT。表达共享总线、定时器、专用路由和实例独占等约束。 |
| 配置事务 | READ 提供同一修订下的运行和候选快照。CHECK、SAVE、启动加载与回退复用整组校验，诊断指出实例、通道、信号、资源及冲突方；继续使用修订号、候选 ID、试用和确认语义。 |

迁移 v1 时，外接 SPI 业务映射到 SPI2 的板级默认值；原 CAN 映射的 SCK/MOSI/MISO 归入 SPI3，CS/INT 归入 MCP2518FD，继承原开关、UART、网络和 DAP 映射。其他新外设默认关闭。对启用了 v1 无法表达的功能或总线路由的配置，旧客户端只可执行语义完整的操作，固件应拒绝可能丢失配置的 v1 写入。导入文件同样按源版本转换并预检；保存、掉电或迁移失败时保留可恢复的已确认版本。详见[功能管理路线图](../function/08-device-profile.md)。

## Stage 1: frozen v2 wire contract

DEVICE_PROFILE payload versions are independent of the outer UBCP v2 frame. Command=0x08, channel=0. All integers are big endian, with exact lengths and no C struct padding. v1 keeps its 11-byte mapping and original diagnostic indices unchanged.

Negotiation: send `02 00` first. Fall back to `01 00` only after explicit status 0F (unsupported version) or 06 (unsupported extension). A timeout, damaged response or unknown layout must fail without silent fallback. CLI `--version 1|2|auto` controls this behavior. Unknown versions return 0F without changing transactions.

A successful v2 DESCRIBE has 77 data bytes after Status: `02 board[4] capabilities:u32 mapping_length:u16 E[26] gpio_policy[40]`. Mapping length=26. Capability bits: 0=v1, 1=v2, 2=dual SPI, 3=Quad; current value=15. Capabilities advertise implemented support; E records configured enablement; runtime state remains in peripheral business commands. Capabilities and board policies are read-only metadata.

Stable instance IDs: SPI2=2, SPI3=3. UART2, DAP, external SPI business device and MCP2518FD each have one instance in this version. CAN channel remains UBCP_CH_CAN_EXT1=3; existing SPI business channels and commands remain unchanged regardless of selected host. Additional slots or host IDs are rejected.

| E offset | Bytes | Meaning |
|---|---:|---|
| 0 | 2 | Original nine v1 feature bits |
| 2 | 4 | UART2.TX, UART2.RX, DAP.SWCLK, DAP.SWDIO GPIO |
| 6 | 7 | SPI2: enabled, width, SCLK, MOSI/IO0, MISO/IO1, IO2, IO3 |
| 13 | 7 | SPI3: same fields |
| 20 | 3 | External SPI business: enabled, host (2/3), CS GPIO |
| 23 | 3 | MCP2518FD: host (2/3), CS GPIO, INT GPIO; enabled by features.CAN |

Enabled is exactly 0/1; width is exactly 1/4. Disabled objects retain mappings but own no configurable pins. Single-line buses own SCLK/MOSI/MISO; Quad also owns IO2/IO3 and requires all four data pins to be bidirectional. A configured Quad bus keeps all pins when an individual transfer uses one data line. Enabled devices require an enabled referenced host. The host owns shared bus pins once; attachments own independent CS/INT. GPIO15 is exclusively MCP2518FD.CS. External SPI selecting GPIO15 returns reason5; selecting the configured MCP2518FD CS returns reason6.

v2 GPIO policies use the existing numeric codes, with GPIO18/19/21/22/23/27 changed from fixed SPI2 to flexible. v1 DESCRIBE retains the old policies. v1 READ remains a legacy projection; v1 CHECK/SAVE must reject configurations whose extension cannot be represented without loss. ID-based CANCEL/APPLY/CONFIRM also reject a nonrepresentable candidate on v1; clients must reconnect using v2 to manage that candidate.

v2 READ success data: `phase:u8 revision:u32 candidate_id:u32 confirmed_id:u32 active:E [candidate:E]`, totaling 39/65 bytes after Status. CHECK/SAVE parameters are `revision:u32 E` (32 bytes including request version/op). SAVE success returns candidate_id:u32. Other operation parameters and responses are identical to v1.

Validation failure stays `02 N [reason subject gpio other]*N`. Reasons1-6 keep their meanings; 7=invalid host/instance/width/enable parameter, 8=disabled dependency host. Reason9 is reserved for a dedicated CS diagnostic and is not currently emitted. v2 signal indices: 0/1=UART2.TX/RX; 2/3=DAP.SWCLK/SWDIO; 4-8=SPI2 SCLK/MOSI/MISO/IO2/IO3; 9-13=SPI3 same order; 14=external SPI.CS; 15=MCP2518FD.CS; 16=MCP2518FD.INT. Feature dependencies still use feature-bit indices. Unused fields are FF. Invalid lengths return status02 without records.

There is no fragmentation. Every complete request/response must fit the existing 2048-byte UBCP payload limit. Hosts check before sending; firmware rejects oversized or mismatched lengths without changing active/candidate/revision. Future larger descriptions require a separately versioned pagination protocol; truncation and partial SAVE are forbidden.

v1 migration retains all feature switches, UART/DAP wiring and CAN.CS/INT. CAN bus signals move to SPI3, width=1, enabled follows features.CAN; unused IO2/IO3 retain22/23. External SPI2 remains enabled with the original18/19/21/22/23, CS27 and Quad support. To import v1 JSON on HXB1, the host reconstructs only those six known legacy SPI2 policy entries from the current real v2 descriptor, strictly validates source metadata, converts, then CHECKs the entire candidate. Import never applies automatically.

### Executable examples and acceptance

[wire-examples.json](../../../script/test/fixtures/profile/wire-examples.json) freezes complete v1/v2 DESCRIBE/READ/CHECK/SAVE payloads and responses including Status, excluding outer UBCP framing/CRC. Each SAVE example starts independently at revision1 and expects ID2. [v1-nondefault.json](../../../script/test/fixtures/profile/v1-nondefault.json) disables DAP and moves UART2 to25/26: seven business pins,32/35 free, five CAN pins unchanged. [v2-default.json](../../../script/test/fixtures/profile/v2-default.json) has15 business pins; SPI2 width1 gives13 and releases22/23; disabling external business and its unreferenced SPI2 leaves9.

```powershell
python script/test/test_profile_examples.py
# VS developer environment: real firmware C handler with platform-only stubs
python script/test/test_profile_cli_host.py
python script/cli/hex-bridge-profile.py --version auto export device.json
python script/cli/hex-bridge-profile.py check device.json --human
```

Shared Python API: `script/hexbridge_profile.py`. Original CLI entry remains a thin compatibility wrapper. `Device.descriptor(version=None)` negotiates; `snapshot()` reads a coherent transaction; `encode_mapping/decode_mapping` handle11/26 bytes; `load_config` validates metadata and migrates v1; `build_tables` computes fixed/editable/current/candidate views. CLI and GUI should import this module directly.

The executable examples test explicit rejection fallback, unsupported versions and nondefault occupancy. The compiled firmware CLI suite verifies frozen v1/v2 bytes, old host/new firmware, both versions' CHECK/SAVE/CANCEL/APPLY/CONFIRM, timeout rollback, persisted corruption, ownership, human rendering and import protection. These are hardware-free host results; wiring and peripheral throughput require separately recorded board acceptance.

### Profile v3 双普通 SPI 实例与可选 CS

v3 DESCRIBE 响应共 81 字节（含状态）。布局沿用 v2，映射长度为 29，后接 40 个 GPIO 策略。能力位 0x10 表示支持第二个普通实例，0x20 表示支持普通设备无 CS；本固件返回 0x3F。映射的前 26 字节沿用原字段顺序，20–22 为设备 1 的启用、主机和 CS，26–28 为设备 2 的相同字段，分别对应通道 4、5。仅 v3 普通设备的 CS 字段以 0xFF 表示无 CS。MCP2518FD 的 CS、INT 仍须有效。CHECK/SAVE 诊断沿用原索引，新增 17 表示设备 2 的 CS；原因 9 表示无 CS 设备需要独占总线，字段依次为原因、设备信号索引、主机号、冲突方信号索引。

v3 客户端的协商顺序为 3、2、1，仅在设备明确拒绝该版本或扩展时降级。旧配置迁移保留设备 1 的开关、主机和 CS。设备 2 默认关闭、主机号 2、CS 为 0xFF。旧客户端可读取其版本视图；生效、已确认或候选配置含旧版无法保留的设置时，固件拒绝旧版写操作。JSON 与线上均以十进制 255 或等值字节表示无 CS；旧版本继续使用原有格式。

### Profile v4 UART1 普通串口

版本协商顺序为 4、3、2、1。v4 DESCRIBE 响应含状态共 82 字节，能力位 0x40 表示可配置 UART1 普通串口；HXB1 全部能力为 0x7F。映射共 30 字节，偏移 0–28 沿用 v3，偏移 29 是 `uart1_business`（0 或 1）。功能掩码中的 UART2 开关仍仅控制通道 1。

UART1 控制位与普通串口位互斥，同时为 1 返回原因 10、字段 18；非法普通串口位返回原因 7、字段 18。两位为 0 时仍保留 GPIO4/34。普通串口使用业务通道 2，管理入口切换须满足 Wi-Fi STA、TCP 9500 和板上已保存凭据的校验。普通串口试用通过当前 TCP 管理会话确认，重新启用串口管理则经 UART1 确认。120 秒未确认恢复上一已确认映射。

旧映射升级时新增位为 0。旧客户端可读其版本支持的字段；若生效、候选或已确认的回退映射启用 UART1 普通串口，设备拒绝旧版配置写操作，以保全该角色。

### Profile v5 SPI 角色

后续 v6 沿用完整的 34 字节 v5 前缀，新增两条 I²C 和十四条 GPIO 映射。字段偏移、能力位、只读降级与事务保护详见 [Profile v6 与迁移](../firmware/10-Stage2-I2C-GPIO.md#profile-v6-与迁移)。

映射 34 字节，前 30 字节保持 v4 布局。偏移 30、31 为 SPI2 的 role、slave_cs，32、33 为 SPI3 的相同字段。role 为 0 主机、1 从机；旧映射补主机和未分配 CS（255）。能力 0x80、0x100 分别表示 SPI2、SPI3 可作单线从机。JSON 在 spi["2"]、spi["3"] 下分别使用 role（"master" 或 "slave"）和 slave_cs（GPIO 编号或 255）。从机启用时必须指定合法输入 CS 并配置单线，检查 SCLK、MOSI 输入与 MISO 输出。旧版写请求不能丢弃有效、候选或回退配置中的新字段。诊断字段 19、20 为 SPI2/3 从机 CS，21、22 为 SPI2/3 角色。原因 11 为主机设备挂在从机上，字段为设备信号、控制器号、角色字段。
