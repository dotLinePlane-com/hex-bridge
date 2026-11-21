# UBCP 设备功能与引脚配置扩展 v1

系统命令 `DEVICE_PROFILE = 0x08`，ChannelID 为 0。使用原有 UBCP v2 帧、CRC、序号和响应规则。所有多字节整数按大端编码，长度必须精确匹配。每个请求以 `01 Op` 开头，响应首字节是 Status。旧固件可通过 DESCRIBE 返回的 NOT_SUPPORT 识别。上位机通过原有 GET_CONFIG/SET_CONFIG 管理串口速率。

## 报文

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
python script/cli/hex-bridge-profile.py export device.json
python script/cli/hex-bridge-profile.py check device.json
python script/cli/hex-bridge-profile.py save device.json
```

将 SAVE 返回的整数代入下例（例如 2）。应用前也可用 `cancel 2` 撤销。试用时按新接线验证业务，再确认。

```powershell
python script/cli/hex-bridge-profile.py apply 2
python script/cli/hex-bridge-profile.py show
python script/cli/hex-bridge-profile.py confirm 2
```
