# HXB1 / CANable 经典 CAN 切速调查（2026-11-21）

**状态：现场断开其他节点后，通过隔离台验收。** 同一 HXB1 固件、SPI3 映射及 COM3/COM9，未重新烧录或写配置。所有硬件实验串行执行。

## 隔离前后对照（最终结论）

用户断开额外节点后，CANable 在 500k 静默监听 3 s，原始接收为 0 字节。与原现场不同，直接 250k 双向通过；连续三轮 500 → 250 → 500，每轮正向严格收到标准经典帧 0x600 Hello、0x601 DLC 5 World、0x602 Back，反向分别收到 0x610 RHello、0x611 RWorld、0x612 RBack。18/18 次方向检查通过，三轮所有状态采样均为 Bus/TEC/REC=0/0/0。完整套件由 414 PASS / 1 FAIL / 1 SKIP 变为 **421 PASS / 0 FAIL / 1 SKIP**。无 BRS 的 FD 64 字节双向通过；独立 SKIP 仍是 CANable 对 FD+BRS 的接收上报。恢复 500k、关闭通道后读回 HXB1 v2 confirmed，修订 138、确认 ID 136、候选 0，CAN 仍为 SPI3/CS15/INT39。

对照支持原总线上其他活动节点影响了本次 250k 测试，并非这对设备无法切速。未测量波形、ACK 槽或终端电阻，不据此断定具体电气机制。切速用例的前置条件：让全部活动节点同步切速，或隔离其他节点并保持正确终端和共地。原接线结果保留在下文作为历史对照。

原始记录：同目录 `CANable-isolated-direct250-20261121-080241.jsonl`、`CANable-isolated-switch-20261121-080241.jsonl`、`CANable-isolated-suite-20261121-080241.log`。

## 原接线证据

- 初始完整 `--baud 500k` 基线：414 PASS / 1 FAIL / 1 SKIP。严格收到标准经典 `0x600 Hello` 和 `0x602 Back`；唯一失败是 `World at 250k: no frame for ID 0x601`。500k 经典与无 BRS 的 FD 64 字节双向正常。独立 SKIP 是 CANable 未上报桥发的 FD+BRS，不是本故障。
- 桥 CAN 通道关闭，CANable 设 `M1` 静默，依次设 500k、250k、500k，各稳定后采样 1.5 s：原始 `t32181122334455667788\r` 分别出现 6、0、7 次；中间串口零字节。可确认额外流量，不可确定节点身份或把串口静默等同于总线静默。
- 跳过套件前置步骤仍复现。COM5 在 OPEN 时读回 `OSC=0x00000400`（PLLEN=0、SCLKDIV=0、OSCRDY=1），`OPMOD=0 CON=0x00100060 NBTCFG=0x010D0403`；切速日志 `baud_idx=5 flags=0x03 fd=0`。按板上记录的 20 MHz 晶振，每位 `1+(13+1)+(4+1)=20` TQ，500k 与 250k 的预分频分别为 2 和 4，对应位时间 2 µs、4 µs。250k 的 `0x030D0403` 是**预期值，不是回读**，不能按源码的 40 MHz 注释改表。
- 11:20:31 UTC 最小切速：Hello 前 `bus/TEC/REC=0/0/0`；CONFIG 成功后、发 World **之前**为 `1/0/128`（error passive），CRC/Form/Bit 错误计数各 1；SEND 回 `00 3e f8 2a 94`，未匹配到 World，之后仍为 `1/0/128`。
- 直接 250k 对照：关闭两端，UBCP OPEN 不接受速率参数，故 OPEN 后立即 CONFIG `05 03 20 00`，期间没有发送测试帧。11:21:50 UTC 首次发帧前 `1/0/128`；SEND 回 `00 43 a3 b1 47`，约 1 s 内 SLCAN 原始 **0 字节**。恢复 CONFIG `06 03 20 00` 回 `00`，11:21:53 UTC 实际收到 `0x602` DLC 4 `42 61 63 6B`，状态回到 `0/0/0`，CLOSE 回 `00`。

另做同步监听对照：CANable 全程 500k `M1` 静默、桥不开启应用层发送，只有桥依次 CONFIG 500k → 250k → 500k。三个 1.5 s 窗口里 COM9 分别记录 6、6、7 条完整 `t32181122334455667788`，桥的 `bus/TEC/REC` 分别是 `0/0/0`、`1/0/128`、`0/0/0`。这证明**桥处于 250k 配置期间仍有可按 500k 解码的额外流量，且无需发送 World 即可触发错误被动状态**。不能据此推断这是谁发的，或证明移除该节点后一定能收发。

## 最终复核

| 原接线实验 | HEX → CANable | CANable → HEX | Bus/TEC/REC（发前、正向窗口后、反向窗口后） |
|---|---|---|---|
| 两端关闭后直接配置 250k | 0x601 World 超时 | 0x611 RWorld 超时 | 三次均 1/0/128 |
| 切速前 500k | 0x600 Hello 通过 | 0x610 RHello 通过 | 三次均 0/0/0 |
| 运行中切至 250k | 0x601 World 超时 | 0x611 RWorld 超时 | 三次均 1/0/128 |
| 切回 500k | 0x602 Back 通过 | 0x612 RBack 通过 | 三次均 0/0/0 |

原始命令、反馈窗口、逐向帧、状态及关闭回执见同目录 `CANable-original-direct250-20261121.jsonl`、`CANable-original-switch-20261121.jsonl`。两份证据的清理均完成；CANable 没有提供可归属于配置命令的成功应答。修改前后完整 `--baud 500k` 均为 **414 PASS / 1 FAIL / 1 SKIP**，不能把诊断改进算作物理故障修复。旧 host 调用顺序测试通过；套件回归 9/9、最小诊断回归 21/21。增强的是 `script/test/test_canable.py` 的响应关联及门控，新增的是 `script/test/diag_can_switch_min.py` 及复跑命令中的两份 host 回归；没有修改固件。

结束后已在 500k 验证 Back，关闭测试通道和串口。用 profile v2 读回 `HXB1 / confirmed / revision 138 / confirmed_id 136 / candidate_id 0`；CAN 保持 SPI3，SCK/MOSI/MISO=14/13/36，CS=15、INT=39；外设 SPI2/CS27。未提交或推送。

## 复跑（仓库根目录，PowerShell）

```powershell
python script/test/test_canable_switch_host.py
python -m unittest discover -s script/test -p test_canable_suite_strict_host.py -v
python script/test/test_diag_can_switch_min_host.py
$run = Get-Date -Format yyyyMMdd-HHmmss
$ports = @('--mcp','COM3','--mcp-baud','115200','--canable','COM9')
python script/test/diag_can_switch_min.py @ports --confirm-bench original-bench --mode direct250 --rounds 1 --timeout 1 --restore-rate 500000 --evidence "direct-$run.jsonl"
python script/test/diag_can_switch_min.py @ports --confirm-bench original-bench --mode switch --rounds 1 --timeout 1 --restore-rate 500000 --evidence "switch-$run.jsonl"
python script/test/test_canable.py @ports --baud 500k
python script/cli/hex-bridge-profile.py --port COM3 --baud 115200 --version 2 pins --human
```

仅在所有节点速率受控、实际完成隔离后，用 `--confirm-bench isolated-bench --mode switch --rounds 3` 重跑并保存新证据文件。`direct250` 是最小对照，不等于将完整套件改用 `--baud 250k`。诊断脚本记录控制反馈、状态和反向帧，有额外采集时间；原始复现仍以完整套件为准。

## 隔离前的判断边界（历史）

SEND 在写 TXQ、置 UINC/TXREQ 后递增 TxCount，并返回 ESP 时间戳，不是硬件发送完成或 ACK 回执。CONFIG 会轮询恢复的 OPMOD，但不回传切速后的 CiNBTCFG。STATUS 的 TxQueueUsage 来源于队列索引字节，不能证明队列为空。CANable 控制命令写入成功也不是实际速率回读。没有同步波形及隔离对照，不能认定额外节点是固定 500k 或是失败原因。

现场人员须先识别额外节点并授权。建议只断开额外节点支路，保留桥与 CANable 的 CAN_H、CAN_L、共地及两端正确终端；若该节点承载终端，须先确认替代方案。不能用软件过滤替代隔离。在可控台架上按相同窗口连续三轮双向测试，再跑完整套件；若隔离后仍失败，采集 250k 总线波形、CiNBTCFG/CiCON/CiTXQSTA 及 ACK 槽，再决定责任侧修复。
