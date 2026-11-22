# HEX-Bridge Wi-Fi 版引脚与接线表（8 MB PSRAM / 16 MB Flash）

网络使用片内 Wi-Fi STA。下表保留现有外设分配，SWD 为新增规划，板上排针位置和连通性待实测。

## 1. 硬件限制与避让说明
* **16MB Flash** 占用引脚：`GPIO 6, 7, 8, 9, 10, 11` (内部连接，不可外接)。
* **8MB PSRAM** 占用引脚：`GPIO 16, 17` (内部连接，不可外接)。由于 8MB PSRAM 为 1.8V 器件，启动时 `GPIO 12 (MTDI)` 电平决定了系统供电域 VDD_SDIO 为 1.8V，**在复位启动期间 GPIO 12 外部不可存在拉低信号**。
* **输入专用引脚 (GPI)**：`GPIO 34, 35, 36, 39` 只能作为输入，无输出驱动能力，也无内部上下拉电阻。

---

## 2. HXB1 默认接线表（v1 基线）

为了让所有接口完全独立并能同时工作，引脚分配如下：

| 外设分类 | 信号名称 | 分配 GPIO&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | GPIO 类型 | 硬件设计与注意事项 |
| :--- | :--- | :--- | :--- | :--- |
| **调试与烧录** | TXD0 | **GPIO 1** | 双向 | 默认 UART0 调试口 |
| | RXD0 | **GPIO 3** | 双向 | 默认 UART0 调试口 |
| **SWD 调试（规划）** | SWCLK | **GPIO 25** | 输出 | 接目标 SWCLK |
| | SWDIO | **GPIO 26** | 双向 | 接目标 SWDIO，读阶段释放输出 |
| | nRESET | — | — | 现由外部 SPI2 占用 GPIO27，不再提供 SWD nRESET |
| | GND | **GND** | 公共参考 | 接目标 GND。按 3.3 V 逻辑、目标板独立供电设计 |
| **mcp串口 1 (UART1)** | TXD1 | **GPIO 4** | 双向 | 通过 GPIO 矩阵映射 |  
| | RXD1 | **GPIO 34** | **仅输入 (GPI)**| 外部必须接 10kΩ 上拉电阻到 3.3V（避免悬空） |
| **扩展串口 2 (UART2)** | RXD2 | **GPIO 35** | **仅输入 (GPI)**| 外部必须接 10kΩ 上拉电阻到 3.3V |
| | TXD2 | **GPIO 32** | 双向 | **UART2 TX**。与 I2C SCL 互换，避免 Strapping 引脚问题。GPIO32 无 Strapping 功能，完全安全。 |
| **CAN FD (MCP2518FD)** | SCK | **GPIO 14** | 双向 | SPI 时钟线 |
| *(SPI 接口)* | MOSI | **GPIO 13** | 双向 | SPI 数据输出线 sdi|
| | MISO | **GPIO 36** | **仅输入 (GPI)**| SPI 数据输入线，外部必须接 10kΩ 上拉电阻 sdo |
| | CS | **GPIO 15** | 双向 | **Strapping 引脚**。芯片内部有弱上拉，但模组内部没有硬上拉电阻。需在外部设计 10kΩ 上拉电阻（防止复位时 CS 被噪声误拉低，同时也保障启动高电平）。 |
| | INT | **GPIO 39** | **仅输入 (GPI)**| 接收中断引脚 |
| **EEPROM (24C02等)** | SCL | **GPIO 12 (MTDI)** | 双向 | I2C 时钟线，需外接 4.7kΩ 上拉电阻。GPIO12 是 MTDI Strapping 引脚控制 PSRAM VDD_SDIO。4.7kΩ 上拉确保复位期间保持高电平 (→1.8V PSRAM 安全)。 |
| *(I2C 接口)* | SDA | **GPIO 33** | 双向 | I2C 数据线，需外接 4.7kΩ 上拉电阻 |
| **外部 SPI 扩展（默认 SPI2）** | SCLK | **GPIO 18** | 双向 | 默认 GPIO Matrix 路由；v2 可选择 SPI2 或 SPI3 并改配引脚 |
| | IO0 / MOSI | **GPIO 19** | 双向 | 单线模式 MOSI；Quad 模式 IO0 |
| | IO1 / MISO | **GPIO 21** | 双向 | 单线模式 MISO；Quad 模式 IO1 |
| | IO2 / WP | **GPIO 22** | 双向 | Quad 数据线 IO2；仅当主机最大线宽配置为单线时不占用 |
| | IO3 / HOLD | **GPIO 23** | 双向 | Quad 数据线 IO3；临时单线事务不解除 Quad 配置的预留 |
| | CS | **GPIO 27** | 双向 | 外部 SPI 片选，可配置高/低有效；原 SWD nRESET 预留取消 |

---

## 3. 剩余没有使用的 GPIO

扣除系统内部占用引脚（Flash/PSRAM）以及各外设已分配引脚后，可用管脚剩余情况如下：

### 3.1 未分配引脚

默认 Quad 接线中，GPIO18/19/21/22/23/27 分配给外部 SPI2，15 个可分配脚均被占用。v2 将该主机最大线宽设为单线后，GPIO22/23 空闲；关闭外接业务及其无其他使用者的 SPI2 后，原九条业务信号仍占九脚、六脚空闲。GPIO0/2/5 涉及启动配置，始终保留。这里描述配置占用，改线仍须核对实际 PCB 或跳线。

### 3.2 无法引出或模组内部占用的 GPIO
* **`GPIO 16, 17`**：被 8MB PSRAM 占用，外部排针悬空或不可连线。
* **`GPIO 6, 7, 8, 9, 10, 11`**：被 16MB Flash 占用，不可连接。
* **`GPIO 37, 38`**：在大多数 ESP32 模组（如 ESP32-WROOM-3E / WROVER-E 等）中，未将管脚引出到外部排针。

### 3.3 SPI2 接口资源冲突
旧 v1 描述将 GPIO18/19/21/22/23/27 固定给外接 SPI2，仅开放原九个业务 GPIO；当前 v2 将这六脚纳入可分配池，共 15 脚。SPI2、SPI3 各自启停、改配并声明最大线宽；外接 SPI 和 MCP2518FD 分别选择主机，默认仍为外接 SPI2、CAN 使用 SPI3。启用的单线主机预留 SCLK/MOSI/MISO，Quad 另预留 IO2/IO3 且四根数据线均须双向。最大线宽决定预留，一次单线传输不会释放 Quad 引脚；单线主机的 Quad 请求在访问 GPIO 前拒绝。启用但无挂载设备的主机也预留总线脚。关闭主机前必须先关闭或迁走其全部挂载设备。

共享主机使用同一总线映射，各设备独立 CS 和时钟参数，事务串行化。与已启用 MCP2518FD 共享主机时，外接 SPI 禁用手动 CS 模式，仅允许自动片选；通用 SPI 不得访问 CAN 专用 CS，GPIO15 仍只允许 MCP2518FD.CS。旧记录迁移保留外接 SPI2 的 Quad 接线、原 CAN 开关及确认状态。板上实际铜线或跳线必须匹配目标映射；本轮主机证据和待补接线见[阶段 1 交付记录](../design/test-report/Stage1-Peripheral-Delivery.md)。

### 3.4 扩展配置的板级约束

沿用 Flash/PSRAM、UART0/1、EEPROM 与启动保留策略时，可分配池为 GPIO13/14/15/18/19/21/22/23/25/26/27/32/35/36/39，共 15 脚。GPIO35/36/39 仅输入，GPIO15 仅限 MCP2518FD.CS。新增 I2C0/1、TWAI、数字 GPIO、LEDC、MCPWM、PCNT 等按信号方向与电气能力从池内选择；两路 I²C 的开放不解除 EEPROM 及 GPIO12 的供电绑带约束。以太网需逐板确认 PHY、RMII 固定信号和参考时钟；某信号无法合法引出时，该板型不应公布相应可用能力。新规划外设没有经过实测的默认接线，见[功能管理路线图](../design/function/08-device-profile.md)。

---

## 4. 关键设计细节补充
1. **仅输入引脚 (GPI 34/35/36/39) 的电平维护**：
   由于这 4 个引脚用于接收信号且不具备内部拉电阻，设计时在 PCB 上必须将它们外接 10kΩ 上拉电阻至 3.3V。特别是在 UART 的 RXD 引脚和 SPI 的 MISO 引脚上，如果不加外部上拉，在空闲时容易由于悬空干扰导致串口/SPI 控制器产生假接收或帧错误。
---

## 5. 外部拉电阻汇总清单 (硬件原理图对照)

在绘制原理图时，请检查并确认以下外部拉电阻已放置：

### 5.1 10kΩ 上拉电阻 (共 5 个)
* [ ] **`GPIO 34`** (UART1_RX1) $\rightarrow$ 3.3V
* [ ] **`GPIO 35`** (UART2_RX2) $\rightarrow$ 3.3V
* [ ] **`GPIO 36`** (SPI_MISO) $\rightarrow$ 3.3V
* [ ] **`GPIO 39`** (MCP2518FD_INT) $\rightarrow$ 3.3V *(开漏中断输出必须，防止引脚浮空抖动)*
* [ ] **`GPIO 15`** (MCP2518FD_CS) $\rightarrow$ 3.3V *(保证复位期间 CS 为高，且满足启动 Strapping 要求)*

### 5.2 4.7kΩ 上拉电阻 (共 2 个)
* [ ] **`GPIO 12`** (I2C_SCL) $\rightarrow$ 3.3V
* [ ] **`GPIO 33`** (I2C_SDA) $\rightarrow$ 3.3V
