# 阶段 2 应用设计 · 双路 I²C 与数字 IO 列表

评审稿。复用 funcitonPinMap 的 Tkinter 工作台、ProfileService、共享 Python 编解码和现有 CLI。此页的字段及命令为拟议接口。

## 配置页

| 选择对象 | 编辑区 | 当前状态与反馈 |
|---|---|---|
| I²C → I2C0 / I2C1 | 两行分别显示启用、SCL、SDA、默认 100/400 kHz 和超时。点击一行只编辑该控制器。 | 同时可见两路映射和占用。业务区另显示 OPEN 状态、当前速率、最近地址与结果。 |
| GPIO → 路 0–13 | 行内显示开关、逻辑路号、物理 GPIO 和模式；选中行可编辑上拉/下拉、启动电平、触发与消抖。 | 输出显示“初始电平”和“最近读回电平”，开漏高电平标为“释放”。输入路隐藏写操作。GPIO35/36/39 禁用内置偏置选项。 |

沿用 SPI 的当前／候选／草稿切换和顶部引脚条。下拉框按方向和板级能力筛选；跨功能冲突同时标注新旧占用方，保留草稿以便在同一事务中迁脚。关闭行后可重新打开并取回草稿设置。未分配与 GPIO0 明确区分。当前设备只宣告 v1–v5 时，规划项只读；不得把不支持误报为“全部关闭”。

## 配置与业务分开操作

1. 连接后协商 v6→v1，仅遇明确不支持时降级。读取设备身份、能力、快照和拓扑。导入 JSON 时复核板型、版本、实例数与引脚。勾选或编辑只产生本地草稿。
2. CHECK 返回字段索引及冲突方；SAVE 展示候选修订与改动。APPLY 后重新连接、核对候选 ID、管理入口和活动映射，再允许 CONFIRM。过期或换板标明原因并保留草稿供比较。
3. 业务区只使用已生效映射和已发现通道。I²C 用户先选择控制器与地址位数，再 OPEN、读寄存器、WRITE_READ、写入、扫描或 CLOSE。以十六进制显示**原始从地址**、寄存器字节、应答数据和错误；扫描由显式操作发起。断线后丢弃打开状态，不重发写操作。
4. GPIO 用户选择逻辑路做读、写、订阅；批量操作先按当前映射分组。跨组写在执行前展示为两笔，分别返回成功／失败，可读回确认。事件列出逻辑路、物理脚、触发沿、采样电平、设备时间戳与溢出提示。同一会话只有一个收帧入口，按序号分派响应、按通道分派事件。I/O 在工作线程，Tk 主线程批量刷新；重连后重建映射，旧事件不再更新当前视图。

## Python、JSON 与 CLI

在 script/hexbridge_profile.py 扩展 encode_mapping、decode_mapping、build_tables 和版本协商；后端及 CLI 均调用这些函数。v6 JSON 保留 v5 字段，新增 i2c（键 "0"/"1"）及 gpio_lines（键 "0" 至 "13"）；整份配置始终含所有固定实例。以下为字段示例，导出未分配脚写 255，UI 显示“未分配”。

~~~json
{
  "i2c": {"0": {"enabled": true, "scl": 18, "sda": 19, "clock_hz": 100000, "timeout_ms": 100}},
  "gpio_lines": {"0": {"enabled": true, "pin": 23, "mode": "open_drain", "initial_level": 1, "pull": "none", "trigger": "none", "debounce_ms": 0}}
}
~~~

保留 hex-bridge-profile.py 的 export/check/save/apply/confirm 流程。业务 CLI 拟提供以下交互；会话型操作使用同一条串口或 TCP 连接完成，避免一次性 CLI 子进程间丢失 OPEN 状态。

~~~text
i2c open --bus 0 --addr-bits 7
i2c read-reg --bus 0 --addr 0x50 --reg 0x00 --length 4
i2c close --bus 0
gpio write --line 0 --level 1
gpio read --line 1
gpio watch --line 1 --edge both --debounce-ms 10
~~~

工具解析当前映射得到物理脚和组，用户脚本始终可按逻辑路号工作。CLI 的机器输出携带实例、通道、序号、状态和数据；业务失败返回非零退出状态（批处理模式）。保存时遇到旧修订，刷新设备状态并让用户合并差异，避免覆盖另一会话的改动。

**界面验收。** 用模拟设备和真实 Tk 控件覆盖两路独立编辑、十四行滚动、导入导出、跨标签冲突、停用后再启用、旧固件能力门控、跨组部分失败及断线重连。上板后用 CLI 和 GUI 读取同一组签名和 GPIO 电平，对照协议抓包。[固件字段与寻址](../../../files/design/firmware/10-Stage2-I2C-GPIO.md) · [测试环境](../../../files/design/test/10-Stage2-I2C-GPIO.md)
