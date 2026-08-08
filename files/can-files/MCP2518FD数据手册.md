# MCP2518FD

# 带SPI接口的外部CAN FD控制器

特性振荡器选项
- 40、20或4 MHz晶振或陶瓷谐振器；外部时钟输入 通用
- 带预分频器的时钟输出
- 带串行外设接口（Serial Peripheral Interface，SPI） SPI接口 的外部CAN FD 控制器
- 最高1 Mbps的仲裁比特率•最高20 MHz SPI时钟速度
- 最高8 Mbps的数据比特率•支持SPI模式0,0和1,1
- CAN FD 控制器模式•寄存器和位域的排列方式便于通过SPI高效访问
- CAN 2.0B和CAN FD 混合模式安全关键型系统
- CAN 2.0B模式• 带CRC 的SPI命令，用于检测SPI接口上的噪声
- 符合ISO 11898-1:2015• 受纠错码（Error Correction Code，ECC）保护的 RAM 报文FIFO 其他特性
- 31 个FIFO，可配置为发送或接收FIFO
- 1个发送队列（Transmit Queue，TXQ）•GPIO引脚：INT0和INT1可配置为通用I/O
- 带32位时间戳的发送事件FIFO（Transmit Event•漏极开路输出：TXCAN、INT、INT0和INT1引脚 FIFO，TEF）可配置为推/挽或漏极开路输出 报文发送 封装类型
- 报文发送优先级：MCP2518FD
- 基于优先级位域SOIC14
- 使用发送队列（TXQ）先发送ID最小的报文 TXCAN114VDD
- 可编程自动重发尝试：无限制、3次尝试或禁止 RXCAN213nCS 报文接收 CLKO/SOF312SDO
- 32 个灵活的过滤器和屏蔽器对象 INT 4 11SDI
- 每个对象均可配置为过滤： OSC25 10SCK
- 标准ID + 前18个数据位或 OSC1 6 9INT0/GPIO0/XSTBY
- 扩展ID VSS7 8 INT1/GPIO1
- 32 位时间戳 特殊特性 MCP2518FD
- VDD：2.7V至5.5V具有可润湿侧翼的VDFN14*
- 工作电流：最大20 mA（5.5V，40 MHz CAN时钟） TXCAN114VDD
- 休眠电流：15 A（典型值） RXCAN213nCS
- 低功耗模式电流：最大为10 A（–40°C至150°C） CLKO/SOF312SDO
- 报文对象位于RAM中：2 KB EP* INT 4 11SDI
- 最多3个可配置中断引脚 OSC25 10SCK
- 总线健康状况诊断和错误计数器 OSC1 6 9INT0/GPIO0/XSTBY
- 收发器待机控制 VSS7 8 INT1/GPIO1
- 帧起始引脚，用于指示总线上报文的开头
- 温度范围：
- 扩展级（E）：-40°C至+125°CVDFN14包括外露的散热焊盘（EP）；请参见表 1-1
- 高温（H）：-40°C 至+150°C

 2020 Microchip Technology Inc. DS20006027A_CN 第1 页

# MCP2518FD

### 1.0 器件概述1.1 框图

MCP2518FD 器件是一款经济高效的小尺寸CAN FD 控图1.1给出了MCP2518FD器件的框图。MCP2518FD包 制器，可通过SPI 接口轻松添加到单片机中。CAN FD含以下主要模块： 通道可以轻松添加到缺少CAN FD 外设或者没有足够
- CAN FD控制器模块实现了CAN FD协议并包含FIFO CAN FD通道的单片机中。 和过滤器。 MCP2518FD 支持经典格式（CAN2.0B）和CAN 灵活数•SPI接口用于通过访问特殊功能寄存器（Special 据速率（CAN FD）格式的CAN帧，如ISO 11898-1:2015Function Register，SFR）和RAM来控制器件。 所规定。
- RAM控制器仲裁SPI和CAN FD控制器模块之间的 MCP2518FD 器件经过了如下改进：RAM访问。
- 新增了低功耗模式（Low Power Mode，LPM），•报文RAM用于存储报文对象的数据。 从而使整个温度范围内的泄漏电流降至10 μA。• 振荡器产生CAN时钟。
- 将发送报文对象和发送事件 FIFO 对象中的 SEQ 字• 内部LDO和POR 电路。 段从7位扩展到23 位。•I/O控制。
- 新增了DEVID寄存器，用以区分该系列未来的新 产品。注1：本数据手册总结了MCP2518FD器件的特性。
- 改用带可润湿侧翼的锯割型DFN封装。但是不应把本手册当作无所不包的参考资 料来使用。如需了解本数据手册的补充信 息，请参见《MCP25xxFD系列参考手册》 的相关章节。

图1-1： MCP2518FD 框图

VDD nCS 䜘޵LDO SPI᧕ਓSCK VSS SDI POR SDO

CLKO/SOF I/O ᣕ᮷RAMRAMಘࡦ᧗ INT

INT0/GPIO0/XSTBY

INT1/GPIO1 OSC1

CAN FD ᥟ㦑ಘRXCAN OSC2 ᧗ࡦಘ⁑ඇRX 䗷└ಘ TXCAN

DS20006027A_CN 第 2页  2020 Microchip Technology Inc.

# MCP2518FD

1.2 引脚分配说明

表1-1说明了引脚的功能。

表1-1： MCP2518FD 标准引脚排列方式 引脚名称 SOIC VDFN 引脚类型 说明

TXCAN 1 1 O 向CAN FD 收发器发送输出 RXCAN 2 2 I 接收来自CAN FD 收发器的输入 CLKO/SOF 3 3 O 时钟输出/ 帧起始输出 INT 4 4 O 中断输出（低电平有效） OSC2 5 5 O 外部振荡器输出 OSC1 6 6 I 外部振荡器输入 V SS 7 7 P 地 INT1/GPIO1 8 8 I/O RX中断输出（低电平有效）/GPIO INT0/GPIO0/9 9 I/O TX中断输出（低电平有效）/GPIO/收发器待机输出 XSTBY SCK 10 10 I SPI时钟输入 SDI 11 11 I SPI数据输入 SDO 12 12 O SPI数据输出 nCS 13 13 I SPI片选输入 VDD 14 14 P 正电源 EP - 15 P 外露焊盘；连接至 V SS 图注： P = 电源，I = 输入，O = 输出

 2020 Microchip Technology Inc. DS20006027A_CN 第3 页

# MCP2518FD

1.3 典型应用CAN FD收发器的VDD连接至5V。 SPI接口用于配置和控制CAN FD控制器。 图1-2 给出了MCP2518FD 器件的典型应用示例。在本 示例中，单片机的工作电压为3.3V。MCP2518FD器件使用INT、INT0和INT1向单片机发送 中断信号。中断需要由单片机通过SPI清除。 MCP2518FD 器件可直接连接到工作电压为2.7V至5.5V 的单片机。此外，MCP2518FD 器件直接连接至高速CLKO引脚为单片机提供时钟。 CAN FD 收发器。将MCP2518FD 和单片机的V DD 与收 发器的VIO 连接时，无需外部电平转换器。

图1-2： MCP2518FD 与 3.3V 单片机接口

VBAT5V LDO

3.3V LDO

0.1 uF0.1 uF0.1 uF0.1 uF

CANH VDDVDDVIOVDD CANH RA0nCSTXCANTXD

SCKSCKRXCANRXD120 ATA6563 SDOSDISTBYCANL CANL VSS SDISDO

MCP2518FD INT0INT PIC® MCU 22 pF INT1INT0OSC2

INT2INT1 22 pF OSC1CLKOOSC1 VSS VSS

DS20006027A_CN 第 4页  2020 Microchip Technology Inc.

# MCP2518FD

- 每个FIFO都可以配置为发送或接收FIFO。FIFO控

### 2.0 CAN FD控制器模块

制持续跟踪FIFO 头部和尾部，并计算用户地址。 图2-1给出了CAN FD控制器模块的主模块：在TX FIFO中，用户地址指向RAM中用于存储下
- CAN FD 控制器模块有多种模式：一个发送报文数据的地址。在RX FIFO中，用户 地址指向RAM 中 用 于 存 储 即 将 读 取 的 下 一 个 接
- 配置 收报文数据的地址。用户通过递增FIFO的头部/ 尾
- 正常CAN FD 部来通知FIFO已向RAM写入报文或已从RAM读取
- 正常CAN 2.0 报文。
- 休眠（正常休眠模式和低功耗模式）
- 发送队列（TXQ）是一个特殊的发送FIFO，它根据
- 仅监听队列中存储的报文的ID发送报文。
- 受限工作• 发送事件FIFO（TEF）存储所发送报文的报文ID。
- 内部和外部环回模式• 自由运行的时基计数器用于为接收的报文添加时间
- CAN FD 比 特 流 处 理 器（Bit Stream Processor，戳。TEF 中的报文也可以添加时间戳。 BSP）实现了ISO 11898-1:2015中说明的CAN FD• CAN FD控制器模块在接收到新的报文时或在成功 协议介质访问控制。它可以对比特流进行序列化和发送报文时产生中断。 反序列化处理、对CAN FD帧进行编码和解码、管理
- SFR 用于控制和读取CAN FD控制器模块的状态。 介质访问、应答帧以及检测错误和发送错误信号。
- TX 处理程序优先处理发送 FIFO 请求发送的报文。 注 1： 本数据手册总结了CAN FD控制器模块的特 该处理程序通过RAM 接口从RAM 中获取发送数据 性。但是不应把本手册当作无所不包的参 并将其提供给BSP进行发送。 考资料来使用。如需了解本数据手册的补
- BSP向RX处理程序提供接收到的报文。RX处理程充信息，请参见《MCP25xxFD系列参考手 序使用接收过滤器过滤应存储在接收FIFO 中的报册》的相关章节。 文。该处理程序通过RAM 接口将接收到的数据存 储到RAM中。

图2-1： CAN FD 控制器模块框图

ࡦ⁑ᔿ᧗SFRᰦ䰤ᡣTBCRAM᧕ਓ

TX༴⨶〻ᒿRX༴⨶〻ᒿ FIFOࡦ᧗TXQࡦ᧗ TX㓗ݸՈ᧕᭦䗷└ಘ

CAN FDॿ䇞 TEFࡦ᧗ࡦѝᯝ᧗ 䭉䈟༴⨶䇺ᯝ ∄⢩⍱༴⨶ಘ

 2020 Microchip Technology Inc. DS20006027A_CN 第5 页

# MCP2518FD

注：

DS20006027A_CN 第 6页  2020 Microchip Technology Inc.

# MCP2518FD

### 3.0 存储器构成图3-1：存储器映射

图3-1给出了存储器的主要分段及其地址范围：MSBLSB ൠ൰ൠ൰
- MCP2518FD 特殊功能寄存器32ս
- CAN FD 控制器模块SFR0x003MSBLSB0x000
- 报文存储器（RAM） SFR的宽度为32位。LSB位于低地址，例如，C1CON的CAN FD᧗ࡦಘ⁑ඇ᧗ࡦಘ⁑ඇSFR LSB位于地址0x000处，而其MSB位于地址0x003处。˄752ᆇ㢲˅ᆇ㢲˅ 表3-1 列出了MCP2518FD 特定的寄存器。第一列包含 SFR 的地址。0x2EF 0x2EC 0x2F30x2F0 表3-2 列出了CAN FD 控制器模块的寄存器。第一列包ᵚᇎ⧠ᵚᇎ⧠ 含SFR 的地址。˄272ᆇ㢲˅ᆇ㢲˅ 0x3FF 0x3FC 0x4030X400

RAM ˄2Kᆇ㢲˅ᆇ㢲˅

0xBFF0xBFC 0xC030xC00 ᵚᇎ⧠ᵚᇎ⧠ ˄512ᆇ㢲˅ᆇ㢲˅ 0xDFF0xDFC 0xE030xE00 MCP2518FD SFR ˄24ᆇ㢲˅ᆇ㢲˅ 0xE170xE14 0xE1B0xE18 ⮉؍⮉؍ ˄488ᆇ㢲˅ᆇ㢲˅ 0xFFF0xFFC

 2020 Microchip Technology Inc. DS20006027A_CN 第7 页

# MCP2518FD

表3-1： MCP2518FD 寄存器汇总

BitBitBitBitBitBitBitBit 地址 名称 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

E03 OSC 31:24 — — — — — — — — E02 23:16 — — — — — — — — E01 15:8 — — — SCLKRDY — OSCRDY — PLLRDY (1) E00 7:0 — CLKODIV<1:0> SCLKDIV LPMEN OSCDIS — PLLEN

IOCON 31:24 — INTOD SOF TXCANOD — — PM1 PM0 23:16 — — — — — — GPIO1 GPIO0

15:8 — — — — — — LAT1 LAT0

E04 7:0 — XSTBYEN — — — — TRIS1 TRIS0

CRC 31:24 — — — — — — FERRIE CRCERRIE 23:16 — — — — — — FERRIF CRCERRIF 15:8 CRC<15:8>

E08 7:0 CRC<7:0>

ECCCON 31:24 — — — — — — — — 23:16 — — — — — — — —

15:8 — PARITY<6:0>

E0C 7:0 — — — — — DEDIE SECIE ECCEN

ECCSTAT 31:24 — — — — ERRADDR<11:8> 23:16 ERRADDR<7:0>

15:8 — — — — — — — —

E10 7:0 — — — — — DEDIF SECIF —

DEVID 31:24 — — — — — — — — 23:16 — — — — — — — —

15:8 — — — — — — — —

E14 7:0 ID[3:0] REV[3:0] 注 1： 32 位寄存器的低字节位于低地址。

DS20006027A_CN 第 8页  2020 Microchip Technology Inc.

# MCP2518FD

表3-2： CAN FD 控制器模块寄存器汇总

BitBitBitBitBitBitBitBit 地址 名称 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

03 C1CON 31:24 TXBWS<3:0> ABAT REQOP<2:0> 02 23:16 OPMOD<2:0> TXQEN STEF SERR2LOM ESIGM RTXAT 01 15:8 — — — BRSDIS BUSY WFT<1:0> WAKFIL [1] 00 7:0 — PXEDIS ISOCRCEN DNCNT<4:0> C1NBTCFG 31:24 BRP<7:0> 23:16 TSEG1<7:0> 15:8 — TSEG2<6:0> 04 7:0 — SJW<6:0> C1DBTCFG 31:24 BRP<7:0> 23:16 — — — TSEG1<4:0> 15:8 — — — — TSEG2<3:0> 08 7:0 — — — — SJW<3:0> C1TDC 31:24 — — — — — — EDGFLTEN SID11EN 23:16 — — — — — — TDCMOD<1:0> 15:8 — TDCO<6:0> 0C 7:0 — — TDCV<5:0> C1TBC 31:24 TBC<31:24> 23:16 TBC<23:16> 15:8 TBC<15:8> 10 7:0 TBC<7:0> C1TSCON 31:24 — — — — — — — — 23:16 — — — — — TSRES TSEOF TBCEN 15:8 — — — — — — TBCPRE<9:8> 14 7:0 TBCPRE<7:0> C1VEC 31:24 — RXCODE<6:0> 23:16 — TXCODE<6:0> 15:8 — — — FILHIT<4:0> 18 7:0 — ICODE<6:0> C1INT 31:24 IVMIE WAKIE CERRIE SERRIE RXOVIE TXATIE SPICRCIE ECCIE 23:16 — — — TEFIE MODIE TBCIE RXIE TXIE 15:8 IVMIF WAKIF CERRIF SERRIF RXOVIF TXATIF SPICRCIF ECCIF 1C 7:0 — — — TEFIF MODIF TBCIF RXIF TXIF C1RXIF 31:24 RFIF<31:24> 23:16 RFIF<23:16> 15:8 RFIF<15:8> 20 7:0 RFIF<7:1> — C1TXIF 31:24 TFIF<31:24> 23:16 TFIF<23:16> 15:8 TFIF<15:8> 24 7:0 TFIF<7:0> C1RXOVIF 31:24 RFOVIF<31:24> 23:16 RFOVIF<23:16> 15:8 RFOVIF<15:8> 28 7:0 RFOVIF<7:1> — C1TXATIF 31:24 TFATIF<31:24> 23:16 TFATIF<23:16> 15:8 TFATIF<15:8> 2C 7:0 TFATIF<7:0> 注 1： 32位寄存器的低字节位于低地址。 2： 保留寄存器读为 0。

 2020 Microchip Technology Inc. DS20006027A_CN 第9 页

# MCP2518FD

表3-2： CAN FD 控制器模块寄存器汇总（续）

BitBitBitBitBitBitBitBit 地址 名称 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

C1TXREQ 31:24 TXREQ<31:24> 23:16 TXREQ<23:16> 15:8 TXREQ<15:8> 30 7:0 TXREQ<7:0> C1TREC 31:24 — — — — — — — — 23:16 — — TXBO TXBP RXBP TXWARN RXWARN EWARN 15:8 TEC<7:0> 34 7:0 REC<7:0> C1BDIAG0 31:24 DTERRCNT<7:0> 23:16 DRERRCNT<7:0> 15:8 NTERRCNT<7:0> 38 7:0 NRERRCNT<7:0> C1BDIAG1 31:24 DLCMM ESI DCRCERR DSTUFERR DFORMERR — DBIT1ERR DBIT0ERR 23:16 TXBOERR — NCRCERR NSTUFERR NFORMERR NACKERR NBIT1ERR NBIT0ERR 15:8 EFMSGCNT<15:8> 3C 7:0 EFMSGCNT<7:0> C1TEFCON 31:24 — — — FSIZE<4:0> 23:16 — — — — — — — — 15:8 — — — — — FRESET — UINC 40 7:0 — — TEFTSEN — TEFOVIE TEFFIE TEFHIE TEFNEIE C1TEFSTA 31:24 — — — — — — — — 23:16 — — — — — — — — 15:8 — — — — — — — — 44 7:0 — — — — TEFOVIF TEFFIF TEFHIF TEFNEIF C1TEFUA 31:24 TEFUA<31:24> 23:16 TEFUA<23:16> 15:8 TEFUA<15:8> 48 7:0 TEFUA<7:0> (2) 保留31:24 保留 <31:24> 23:16 保留 <23:16> 15:8 保留 <15:8> 4C 7:0 保留 <7:0> C1TXQCON 31:24 PLSIZE<2:0> FSIZE<4:0> 23:16 — TXAT<1:0> TXPRI<4:0> 15:8 — — — — — FRESET TXREQ UINC 50 7:0 TXEN — — TXATIE — TXQEIE — TXQNIE C1TXQSTA 31:24 — — — — — — — — 23:16 — — — — — — — — 15:8 — — — TXQCI<4:0> 54 7:0 TXABT TXLARB TXERR TXATIF — TXQEIF — TXQNIF C1TXQUA 31:24 TXQUA<31:24> 23:16 TXQUA<23:16> 15:8 TXQUA<15:8> 58 7:0 TXQUA<7:0> 注 1： 32位寄存器的低字节位于低地址。 2： 保留寄存器读为 0。

DS20006027A_CN 第 10页  2020 Microchip Technology Inc.

# MCP2518FD

表3-2： CAN FD 控制器模块寄存器汇总（续）

BitBitBitBitBitBitBitBit 地址 名称 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

C1FIFOCON1 31:24 PLSIZE<2:0> FSIZE<4:0> 23:16 — TXAT<1:0> TXPRI<4:0> 15:8 — — — — — FRESET TXREQ UINC 5C 7:0 TXEN RTREN RXTSEN TXATIE RXOVIE TFERFFIE TFHRFHIE TFNRFNIE C1FIFOSTA1 31:24 — — — — — — — — 23:16 — — — — — — — — 15:8 — — — FIFOCI<4:0> 60 7:0 TXABT TXLARB TXERR TXATIF RXOVIF TFERFFIF TFHRFHIF TFNRFNIF C1FIFOUA1 31:24 FIFOUA<31:24> 23:16 FIFOUA<23:16> 15:8 FIFOUA<15:8> 64 7:0 FIFOUA<7:0> 68 C1FIFOCON2 31:0 与 C1FIFOCON1 相同 6C C1FIFOSTA2 31:0 与 C1FIFOSTA1 相同 70 C1FIFOUA2 31:0 与 C1FIFOUA1相同 74 C1FIFOCON3 31:0 与 C1FIFOCON1 相同 78 C1FIFOSTA3 31:0 与 C1FIFOSTA1 相同 7C C1FIFOUA3 31:0 与 C1FIFOUA1相同 80 C1FIFOCON4 31:0 与 C1FIFOCON1 相同 84 C1FIFOSTA4 31:0 与 C1FIFOSTA1 相同 88 C1FIFOUA4 31:0 与 C1FIFOUA1相同 8C C1FIFOCON5 31:0 与 C1FIFOCON1 相同 90 C1FIFOSTA5 31:0 与 C1FIFOSTA1 相同 94 C1FIFOUA5 31:0 与 C1FIFOUA1相同 98 C1FIFOCON6 31:0 与 C1FIFOCON1 相同 9C C1FIFOSTA6 31:0 与 C1FIFOSTA1 相同 A0 C1FIFOUA6 31:0 与 C1FIFOUA1相同 A4 C1FIFOCON7 31:0 与 C1FIFOCON1 相同 A8 C1FIFOSTA7 31:0 与 C1FIFOSTA1 相同 AC C1FIFOUA7 31:0 与 C1FIFOUA1相同 B0 C1FIFOCON8 31:0 与 C1FIFOCON1 相同 B4 C1FIFOSTA8 31:0 与 C1FIFOSTA1 相同 B8 C1FIFOUA8 31:0 与 C1FIFOUA1相同 BC C1FIFOCON9 31:0 与 C1FIFOCON1 相同 C0 C1FIFOSTA9 31:0 与 C1FIFOSTA1 相同 C4 C1FIFOUA9 31:0 与 C1FIFOUA1相同 C8 C1FIFOCON10 31:0 与 C1FIFOCON1 相同 CC C1FIFOSTA10 31:0 与 C1FIFOSTA1 相同 D0 C1FIFOUA10 31:0 与 C1FIFOUA1相同 D4 C1FIFOCON11 31:0 与 C1FIFOCON1 相同 D8 C1FIFOSTA11 31:0 与 C1FIFOSTA1 相同 DC C1FIFOUA11 31:0 与 C1FIFOUA1相同 E0 C1FIFOCON12 31:0 与 C1FIFOCON1 相同 E4 C1FIFOSTA12 31:0 与 C1FIFOSTA1 相同 E8 C1FIFOUA12 31:0 与 C1FIFOUA1相同 EC C1FIFOCON13 31:0 与 C1FIFOCON1 相同 F0 C1FIFOSTA13 31:0 与 C1FIFOSTA1 相同 F4 C1FIFOUA13 31:0 与 C1FIFOUA1相同 F8 C1FIFOCON14 31:0 与 C1FIFOCON1 相同 FC C1FIFOSTA14 31:0 与 C1FIFOSTA1 相同 100 C1FIFOUA14 31:0 与 C1FIFOUA1相同 注 1： 32位寄存器的低字节位于低地址。 2： 保留寄存器读为 0。

 2020 Microchip Technology Inc. DS20006027A_CN 第11 页

# MCP2518FD

表3-2： CAN FD 控制器模块寄存器汇总（续）

BitBitBitBitBitBitBitBit 地址 名称 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

104 C1FIFOCON15 31:0 与 C1FIFOCON1 相同 108 C1FIFOSTA15 31:0 与 C1FIFOSTA1相同 10C C1FIFOUA15 31:0 与 C1FIFOUA1相同 110 C1FIFOCON16 31:0 与 C1FIFOCON1 相同 114 C1FIFOSTA16 31:0 与 C1FIFOSTA1相同 118 C1FIFOUA16 31:0 与 C1FIFOUA1相同 11C C1FIFOCON17 31:0 与 C1FIFOCON1 相同 120 C1FIFOSTA17 31:0 与 C1FIFOSTA1相同 124 C1FIFOUA17 31:0 与 C1FIFOUA1相同 128 C1FIFOCON18 31:0 与 C1FIFOCON1 相同 12C C1FIFOSTA18 31:0 与 C1FIFOSTA1相同 130 C1FIFOUA18 31:0 与 C1FIFOUA1相同 134 C1FIFOCON19 31:0 与 C1FIFOCON1 相同 138 C1FIFOSTA19 31:0 与 C1FIFOSTA1相同 13C C1FIFOUA19 31:0 与 C1FIFOUA1相同 140 C1FIFOCON20 31:0 与 C1FIFOCON1 相同 144 C1FIFOSTA20 31:0 与 C1FIFOSTA1相同 148 C1FIFOUA20 31:0 与 C1FIFOUA1相同 14C C1FIFOCON21 31:0 与 C1FIFOCON1 相同 150 C1FIFOSTA21 31:0 与 C1FIFOSTA1相同 154 C1FIFOUA21 31:0 与 C1FIFOUA1相同 158 C1FIFOCON22 31:0 与 C1FIFOCON1 相同 15C C1FIFOSTA22 31:0 与 C1FIFOSTA1相同 160 C1FIFOUA22 31:0 与 C1FIFOUA1相同 164 C1FIFOCON23 31:0 与 C1FIFOCON1 相同 168 C1FIFOSTA23 31:0 与 C1FIFOSTA1相同 16C C1FIFOUA23 31:0 与 C1FIFOUA1相同 170 C1FIFOCON24 31:0 与 C1FIFOCON1 相同 174 C1FIFOSTA24 31:0 与 C1FIFOSTA1相同 178 C1FIFOUA24 31:0 与 C1FIFOUA1相同 17C C1FIFOCON25 31:0 与 C1FIFOCON1 相同 180 C1FIFOSTA25 31:0 与 C1FIFOSTA1相同 184 C1FIFOUA25 31:0 与 C1FIFOUA1相同 188 C1FIFOCON26 31:0 与 C1FIFOCON1 相同 18C C1FIFOSTA26 31:0 与 C1FIFOSTA1相同 190 C1FIFOUA26 31:0 与 C1FIFOUA1相同 194 C1FIFOCON27 31:0 与 C1FIFOCON1 相同 198 C1FIFOSTA27 31:0 与 C1FIFOSTA1相同 19C C1FIFOUA27 31:0 与 C1FIFOUA1相同 1A0 C1FIFOCON28 31:0 与 C1FIFOCON1 相同 1A4 C1FIFOSTA28 31:0 与 C1FIFOSTA1相同 1A8 C1FIFOUA28 31:0 与 C1FIFOUA1相同 1AC C1FIFOCON29 31:0 与 C1FIFOCON1 相同 1B0 C1FIFOSTA29 31:0 与 C1FIFOSTA1相同 1B4 C1FIFOUA29 31:0 与 C1FIFOUA1相同 1B8 C1FIFOCON30 31:0 与 C1FIFOCON1 相同 1BC C1FIFOSTA30 31:0 与 C1FIFOSTA1相同 1C0 C1FIFOUA30 31:0 与 C1FIFOUA1相同 1C4 C1FIFOCON31 31:0 与 C1FIFOCON1 相同 1C8 C1FIFOSTA31 31:0 与 C1FIFOSTA1相同 1CC C1FIFOUA31 31:0 与 C1FIFOUA1相同 注 1： 32位寄存器的低字节位于低地址。 2： 保留寄存器读为 0。

DS20006027A_CN 第 12页  2020 Microchip Technology Inc.

# MCP2518FD

表3-2： CAN FD 控制器模块寄存器汇总（续）

BitBitBitBitBitBitBitBit 地址 名称 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

C1FLTCON0 31:24 FLTEN3 — — F3BP<4:0> 23:16 FLTEN2 — — F2BP<4:0> 15:8 FLTEN1 — — F1BP<4:0> 1D0 7:0 FLTEN0 — — F0BP<4:0> C1FLTCON1 31:24 FLTEN7 — — F7BP<4:0> 23:16 FLTEN6 — — F6BP<4:0> 15:8 FLTEN5 — — F5BP<4:0> 1D4 7:0 FLTEN4 — — F4BP<4:0> C1FLTCON2 31:24 FLTEN11 — — F11BP<4:0> 23:16 FLTEN10 — — F10BP<4:0> 15:8 FLTEN9 — — F9BP<4:0> 1D8 7:0 FLTEN8 — — F8BP<4:0> C1FLTCON3 31:24 FLTEN15 — — F15BP<4:0> 23:16 FLTEN14 — — F14BP<4:0> 15:8 FLTEN13 — — F13BP<4:0> 1DC 7:0 FLTEN12 — — F12BP<4:0> C1FLTCON4 31:24 FLTEN19 — — F19BP<4:0> 23:16 FLTEN18 — — F18BP<4:0> 15:8 FLTEN17 — — F17BP<4:0> 1E0 7:0 FLTEN16 — — F16BP<4:0> C1FLTCON5 31:24 FLTEN23 — — F23BP<4:0> 23:16 FLTEN22 — — F22BP<4:0> 15:8 FLTEN21 — — F21BP<4:0> 1E4 7:0 FLTEN20 — — F20BP<4:0> C1FLTCON6 31:24 FLTEN27 — — F27BP<4:0> 23:16 FLTEN26 — — F26BP<4:0> 15:8 FLTEN25 — — F25BP<4:0> 1E8 7:0 FLTEN24 — — F24BP<4:0> C1FLTCON7 31:24 FLTEN31 — — F31BP<4:0> 23:16 FLTEN30 — — F30BP<4:0> 15:8 FLTEN29 — — F29BP<4:0> 1EC 7:0 FLTEN28 — — F28BP<4:0> C1FLTOBJ0 31:24 — EXIDE SID11 EID<17:6> 23:16 EID<12:5> 15:8 EID<4:0> SID<10:8> 1F0 7:0 SID<7:0> C1MASK0 31:24 — MIDE MSID11 MEID<17:6> 23:16 MEID<12:5> 15:8 MEID<4:0> MSID<10:8> 1F4 7:0 MSID<7:0> 1F8 C1FLTOBJ1 31:0 与 C1FLTOBJ0相同 1FC C1MASK1 31:0 与 C1MASK0 相同 200 C1FLTOBJ2 31:0 与 C1FLTOBJ0相同 204 C1MASK2 31:0 与 C1MASK0 相同 208 C1FLTOBJ3 31:0 与 C1FLTOBJ0相同 20C C1MASK3 31:0 与 C1MASK0 相同 210 C1FLTOBJ4 31:0 与 C1FLTOBJ0相同 214 C1MASK4 31:0 与 C1MASK0 相同 218 C1FLTOBJ5 31:0 与 C1FLTOBJ0相同 21C C1MASK5 31:0 与 C1MASK0 相同 注 1： 32位寄存器的低字节位于低地址。 2： 保留寄存器读为 0。

 2020 Microchip Technology Inc. DS20006027A_CN 第13 页

# MCP2518FD

表3-2： CAN FD 控制器模块寄存器汇总（续）

BitBitBitBitBitBitBitBit 地址 名称 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

220 C1FLTOBJ6 31:0 与 C1FLTOBJ0相同 224 C1MASK6 31:0 与 C1MASK0 相同 228 C1FLTOBJ7 31:0 与 C1FLTOBJ0相同 22C C1MASK7 31:0 与 C1MASK0 相同 230 C1FLTOBJ8 31:0 与 C1FLTOBJ0相同 234 C1MASK8 31:0 与 C1MASK0 相同 238 C1FLTOBJ9 31:0 与 C1FLTOBJ0相同 23C C1MASK9 31:0 与 C1MASK0 相同 240 C1FLTOBJ10 31:0 与 C1FLTOBJ0相同 244 C1MASK10 31:0 与 C1MASK0 相同 248 C1FLTOBJ11 31:0 与 C1FLTOBJ0相同 24C C1MASK11 31:0 与 C1MASK0 相同 250 C1FLTOBJ12 31:0 与 C1FLTOBJ0相同 254 C1MASK12 31:0 与 C1MASK0 相同 258 C1FLTOBJ13 31:0 与 C1FLTOBJ0相同 25C C1MASK13 31:0 与 C1MASK0 相同 260 C1FLTOBJ14 31:0 与 C1FLTOBJ0相同 264 C1MASK14 31:0 与 C1MASK0 相同 268 C1FLTOBJ15 31:0 与 C1FLTOBJ0相同 26C C1MASK15 31:0 与 C1MASK0 相同 270 C1FLTOBJ16 31:0 与 C1FLTOBJ0相同 274 C1MASK16 31:0 与 C1MASK0 相同 278 C1FLTOBJ17 31:0 与 C1FLTOBJ0相同 27C C1MASK17 31:0 与 C1MASK0 相同 280 C1FLTOBJ18 31:0 与 C1FLTOBJ0相同 284 C1MASK18 31:0 与 C1MASK0 相同 288 C1FLTOBJ19 31:0 与 C1FLTOBJ0相同 28C C1MASK19 31:0 与 C1MASK0 相同 290 C1FLTOBJ20 31:0 与 C1FLTOBJ0相同 294 C1MASK20 31:0 与 C1MASK0 相同 298 C1FLTOBJ21 31:0 与 C1FLTOBJ0相同 29C C1MASK21 31:0 与 C1MASK0 相同 2A0 C1FLTOBJ22 31:0 与 C1FLTOBJ0相同 2A4 C1MASK22 31:0 与 C1MASK0 相同 2A8 C1FLTOBJ23 31:0 与 C1FLTOBJ0相同 2AC C1MASK23 31:0 与 C1MASK0 相同 2B0 C1FLTOBJ24 31:0 与 C1FLTOBJ0相同 2B4 C1MASK24 31:0 与 C1MASK0 相同 2B8 C1FLTOBJ25 31:0 与 C1FLTOBJ0相同 2BC C1MASK25 31:0 与 C1MASK0 相同 2C0 C1FLTOBJ26 31:0 与 C1FLTOBJ0相同 2C4 C1MASK26 31:0 与 C1MASK0 相同 2C8 C1FLTOBJ27 31:0 与 C1FLTOBJ0相同 2CC C1MASK27 31:0 与 C1MASK0 相同 2D0 C1FLTOBJ28 31:0 与 C1FLTOBJ0相同 2D4 C1MASK28 31:0 与 C1MASK0 相同 2D8 C1FLTOBJ29 31:0 与 C1FLTOBJ0相同 2DC C1MASK29 31:0 与 C1MASK0 相同 2E0 C1FLTOBJ30 31:0 与 C1FLTOBJ0相同 2E4 C1MASK30 31:0 与 C1MASK0 相同 2E8 C1FLTOBJ31 31:0 与 C1FLTOBJ0相同 2EC C1MASK31 31:0 与 C1MASK0 相同 注 1： 32位寄存器的低字节位于低地址。 2： 保留寄存器读为 0。

DS20006027A_CN 第 14页  2020 Microchip Technology Inc.

# MCP2518FD

3.1 MCP2518FD特定的寄存器

- 寄存器3-1：OSC
- 寄存器3-2：IOCON
- 寄存器3-3：CRC
- 寄存器3-4：ECCCON
- 寄存器3-5：ECCSTAT
- 寄存器3-6：DEVID

表3-3： 寄存器图例 符号 说明 符号 说明 R 可读位 HC 仅由硬件清零 W 可写位 HS 仅由硬件置1 U 未实现位，读为0 1 复位时置1 S 可置1位 0 复位时清零 C 可清零位 x 复位时未知

示例 3-1：

R/W - 0表示位可读写，在复位后读为0。

 2020 Microchip Technology Inc. DS20006027A_CN 第15 页

# MCP2518FD

寄存器 3-1： OSC —— MCP2518FD振荡器控制寄存器

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 23 bit 16

U-0 U-0 U-0 R-0 U-0 R-0 U-0 R-0 — — — SCLKRDY — OSCRDY — PLLRDY bit 15 bit 8

U-0 R/W-1 R/W-1 R/W-0 R/W-0 HS/C-0 U-0 R/W-0 (1) (3) (2) (1) — CLKODIV<1:0> SCLKDIV LPMENOSCDIS— PLLEN bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-13 未实现：读为0 bit 12 SCLKRDY：同步SCLKDIV位 1 = SCLKDIV 1 0 = SCLKDIV 0 bit 11 未实现：读为0 bit 10 OSCRDY：时钟就绪 1 = 时钟正在运行且保持稳定 0 = 时钟未就绪或已关闭 bit 9 未实现：读为0 bit 8 PLLRDY：PLL就绪 1 = PLL锁定 0 = PLL未就绪 bit 7 未实现：读为0 bit 6-5 CLKODIV<1:0>：时钟输出分频比 11 = CLKO 10分频 10 = CLKO 4分频 01 = CLKO 2分频 00 = CLKO 1分频 (1) bit 4 SCLKDIV：系统时钟分频比 1 = SCLK 2 分频 0 = SCLK 1 分频

注 1： 只能在配置模式下修改该位。 2： 在休眠模式下清零OSCDIS将唤醒器件并将其重新置于配置模式。 3： 设置LPMEN实际上并不会将器件置于LPM，而是选择在使用CiCON.REQOP请求休眠模式后进入哪种休眠模 式。为了在RXCAN活动时唤醒，CiINT.WAKIE必须置1。

DS20006027A_CN 第 16页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-1： OSC —— MCP2518FD振荡器控制寄存器（续）

(3) bit 3 LPMEN：低功耗模式（LPM）使能 1 = 在LPM下，器件将停止时钟并使芯片的大部分电路进入掉电模式。寄存器值和RAM值将丢失。器 件将在nCS置为有效或RXCAN活动时唤醒。 0 = 在休眠模式下，器件将停止时钟并保留其寄存器值和RAM值。器件将在OSCDIS位清零或RXCAN 活动时唤醒。 (2) bit 2 OSCDIS：时钟（振荡器）禁止 1 = 禁止时钟，器件处于休眠模式。 0 = 使能时钟 bit 1 未实现：读为0 (1) bit 0 PLLEN：PLL使能 1 = 系统时钟来自10x PLL 0 = 系统时钟直接来自XTAL振荡器

注 1： 只能在配置模式下修改该位。 2： 在休眠模式下清零OSCDIS将唤醒器件并将其重新置于配置模式。 3： 设置LPMEN实际上并不会将器件置于LPM，而是选择在使用CiCON.REQOP请求休眠模式后进入哪种休眠模 式。为了在RXCAN活动时唤醒，CiINT.WAKIE必须置1。

 2020 Microchip Technology Inc. DS20006027A_CN 第17 页

# MCP2518FD

寄存器 3-2： IOCON ——输入 /输出控制寄存器

U-0 R/W-0 R/W-0 R/W-0 U-0 U-0 R/W-1 R/W-1 — INTOD SOF TXCANOD — — PM1 PM0 bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 R/W-x R/W-x — — — — — — GPIO1 GPIO0 bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 U-0 R/W-x R/W-x — — — — — — LAT1 LAT0 bit 15 bit 8

U-0 R/W-0 U-0 U-0 U-0 U-0 R/W-1 R/W-1 (1) (1) — XSTBYEN — — — — TRIS1 TRIS0 bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31 未实现：读为0 bit 30 INTOD：中断引脚漏极开路模式 1 = 漏极开路输出 0 = 推/挽输出 bit 29 SOF：帧起始信号 1 = CLKO引脚上出现SOF信号 0 = CLKO引脚上出现时钟 bit 28 TXCANOD：TXCAN漏极开路模式 1 = 漏极开路输出 0 = 推/挽输出 bit 27-26 未实现：读为0 bit 25 PM1：GPIO引脚模式 1 = 引脚用作GPIO1 0 = 中断引脚INT1，在CiINT.RXIF和RXIE置1时置为有效 bit 24 PM0：GPIO引脚模式 1 = 引脚用作GPIO0 0 = 中断引脚INT0，在CiINT.TXIF和TXIE置1时置为有效 bit 23-18 未实现：读为0 bit 17 GPIO1：GPIO1状态 1 = V GPIO1 > VIH 0 = V GPIO1 < V IL bit 16 GPIO0：GPIO0状态 1 = V GPIO0 > VIH 0 = V GPIO0 < VIL bit 15-10 未实现：读为0

注 1： 如果PMx = 0，TRISx将被忽略，引脚将为输出。

DS20006027A_CN 第 18页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-2： IOCON ——输入 /输出控制寄存器（续）

bit 9 LAT1：GPIO1锁存器 1 = 将引脚驱动为高电平 0 = 将引脚驱动为低电平 bit 8 LAT0：GPIO0锁存器 1 = 将引脚驱动为高电平 0 = 将引脚驱动为低电平 bit 7 未实现：读为0 bit 6 XSTBYEN：使能收发器待机引脚控制 1 = 使能XSTBY控制 0 = 禁止XSTBY控制 bit 5-2 未实现：读为0 (1) bit 1 TRIS1：GPIO1数据方向 1 = 输入引脚 0 = 输出引脚 (1) bit 0 TRIS0：GPIO0数据方向 1 = 输入引脚 0 = 输出引脚

注 1： 如果PMx = 0，TRISx将被忽略，引脚将为输出。

 2020 Microchip Technology Inc. DS20006027A_CN 第19 页

# MCP2518FD

寄存器 3-3： CRC —— CRC 寄存器

U-0 U-0 U-0 U-0 U-0 U-0 R/W-0 R/W-0 — — — — — — FERRIE CRCERRIE bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 HS/C-0 HS/C-0 — — — — — — FERRIF CRCERRIF bit 23 bit 16

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 CRC<15:8> bit 15 bit 8

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 CRC<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-26 未实现：读为0 bit 25 FERRIE：CRC命令格式错误中断允许 bit 24 CRCERRIE：CRC错误中断允许 bit 23-18 未实现：读为0 bit 17 FERRIF：CRC命令格式错误中断标志 1 = “SPI + CRC”命令发生期间字节数不匹配 0 = 未发生SPI CRC命令格式错误 bit 16 CRCERRIF：CRC错误中断标志 1 = 发生CRC不匹配 0 = 未发生CRC错误 bit 15-0 CRC<15:0>：自上一次CRC不匹配起的循环冗余校验

DS20006027A_CN 第 20页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-4： ECCCON —— ECC 控制寄存器

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 23 bit 16

U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 — PARITY<6:0> bit 15 bit 8

U-0 U-0 U-0 U-0 U-0 R/W-0 R/W-0 R/W-0 — — — — — DEDIE SECIE ECCEN bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-15 未实现：读为0 bit 14-8 PARITY<6:0>：禁止ECC 时，在写入RAM期间使用的奇偶校验位 bit 7-3 未实现：读为0 bit 2 DEDIE：双位错误检测中断允许标志 bit 1 SECIE：单个位错误纠正中断允许标志 bit 0 ECCEN：ECC使能 1 = 使能ECC 0 = 禁止ECC

 2020 Microchip Technology Inc. DS20006027A_CN 第21 页

# MCP2518FD

寄存器 3-5： ECCSTAT —— ECC 状态寄存器

U-0 U-0 U-0 U-0 R-0 R-0 R-0 R-0 — — — — ERRADDR<11:8> bit 31 bit 24

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 ERRADDR<7:0> bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 15 bit 8

U-0 U-0 U-0 U-0 U-0 HS/C-0 HS/C-0 U-0 — — — — — DEDIF SECIF — bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-28 未实现：读为0 bit 27-16 ERRADDR<11:0>：发生上一个ECC错误的地址 bit 15-3 未实现：读为0 bit 2 DEDIF：双位错误检测中断标志 1 = 检测到双位错误 0 = 未检测到双位错误 bit 1 SECIF：单个位错误纠正中断标志 1 = 纠正了单个位错误 0 = 未发生单个位错误 bit 0 未实现：读为0

DS20006027A_CN 第 22页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-6： DEVID ——器件ID 寄存器

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 15 bit 8

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 ID[3:0] REV[3:0] bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-8 未实现：读为0 bit 7-4 ID[3:0]：器件ID bit 3-0 REV[3:0]：芯片版本

 2020 Microchip Technology Inc. DS20006027A_CN 第23 页

# MCP2518FD

注：

DS20006027A_CN 第 24页  2020 Microchip Technology Inc.

# MCP2518FD

3.2 CAN FD 控制器模块寄存器FIFO控制和状态寄存器
- 寄存器3-23：CiTEFCON 配置寄存器
- 寄存器3-24：CiTEFSTA
- 寄存器3-7：CiCON• 寄存器3-25：CiTEFUA
- 寄存器3-8：CiNBTCFG• 寄存器3-26：CiTXQCON
- 寄存器3-9：CiDBTCFG• 寄存器3-27：CiTXQSTA
- 寄存器3-10：CiTDC• 寄存器3-28：CiTXQUA
- 寄存器3-11：CiTBC• 寄存器3-29：CiFIFOCONm —— m = 1至31
- 寄存器3-12：CiTSCON• 寄存器3-30：CiFIFOSTAm —— m = 1 至31
- 寄存器3-31：CiFIFOUAm —— m = 1至31 中断和状态寄存器 过滤器配置和控制寄存器
- 寄存器3-13：CiVEC
- 寄存器3-14：CiINT• 寄存器3-32：CiFLTCONm —— m = 0至7
- 寄存器3-15：CiRXIF• 寄存器3-33：CiFLTOBJm —— m = 0至31
- 寄存器3-16：CiRXOVIF• 寄存器3-34：CiMASKm —— m = 0 至31
- 寄存器3-17：CiTXIF
- 寄存器3-18：CiTXATIF注： 寄存器标识符中显示的“i”表示 CANi，例
- 寄存器3-19：CiTXREQ如C1CON。MCP2518FD器件包含一个CAN FD控制器模块。 错误和诊断寄存器
- 寄存器3-20：CiTREC
- 寄存器3-21：CiBDIAG0
- 寄存器3-22：CiBDIAG1

表3-4： 寄存器图例 符号 说明 符号 说明 R 可读位 HC 仅由硬件清零 W 可写位 HS 仅由硬件置1 U 未实现位，读为0 1 复位时置1 S 可置1位 0 复位时清零 C 可清零位 x 复位时未知

示例 3-2：

R/W - 0 表示位可读写，在复位后读为0。

 2020 Microchip Technology Inc. DS20006027A_CN 第25 页

# MCP2518FD

寄存器 3-7： CiCON —— CAN控制寄存器

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-1 R/W-0 R/W-0 TXBWS<3:0> ABAT REQOP<2:0> bit 31 bit 24

R-1 R-0 R-0 R/W-1 R/W-1 R/W-0 R/W-0 R/W-0 (1) (1) (1) (1) OPMOD<2:0> TXQEN STEFSERR2LOMESIGMRTXAT (1)

bit 23 bit 16

U-0 U-0 U-0 R/W-0 R-0 R/W-1 R/W-1 R/W-1 (1) — — — BRSDIS BUSY WFT<1:0> WAKFIL bit 15 bit 8

U-0 R/W-1 R/W-1 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) — PXEDISISOCRCENDNCNT<4:0> (1)

bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-28 TXBWS<3:0>：发送带宽共用位 两次连续传输之间的延时（以仲裁位时间为单位） 0000 = 无延时 0001 = 2 0010 = 4 0011 = 8 0100 = 16 0101 = 32 0110 = 64 0111 = 128 1000 = 256 1001 = 512 1010 = 1024 1011 = 2048 1111-1100 = 4096 bit 27 ABAT：中止所有等待的发送位 1 = 通知所有发送FIFO中止发送 0 = 模块将在所有发送中止时清零该位 bit 26-24 REQOP<2:0>：请求工作模式位 000 = 设置为正常CAN FD 模式；支持混用CAN FD帧和经典CAN 2.0帧 001 = 设置为休眠模式 010 = 设置为内部环回模式 011 = 设置为仅监听模式 100 = 设置为配置模式 101 = 设置为外部环回模式 110 = 设置为正常CAN 2.0模式；接收CAN FD 帧时可能生成错误帧 111 = 设置为受限工作模式

注 1： 只能在配置模式下修改这些位。

DS20006027A_CN 第 26页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-7： CiCON —— CAN控制寄存器（续）

bit 23-21 OPMOD<2:0>：工作模式状态位 000 = 模块处于正常CAN FD 模式；支持混用CAN FD帧和经典CAN 2.0帧 001 = 模块处于休眠模式 010 = 模块处于内部环回模式 011 = 模块处于仅监听模式 100 = 模块处于配置模式 101 = 模块处于外部环回模式 110 = 模块处于正常CAN 2.0模式；接收CAN FD 帧时可能生成错误帧 111 = 模块处于受限工作模式 (1) bit 20 TXQEN：使能发送队列位 1 = 使能TXQ并在RAM中预留空间 0 = 不在RAM中为TXQ预留空间 (1) bit 19 STEF：发送事件FIFO存储位 1 = 将发送的报文保存到TEF 中并在RAM中预留空间 0 = 不将发送的报文保存到TEF 中 (1) bit 18 SERR2LOM：发生系统错误时切换到仅监听模式位 1 = 切换到仅监听模式 0 = 切换到受限工作模式 (1) bit 17 ESIGM：在网关模式下发送ESI位 1 = 当报文的ESI 为高电平或CAN控制器处于被动错误状态时，ESI隐性发送 0 = ESI 反映CAN控制器的错误状态 (1) bit 16 RTXAT：限制重发尝试位 1 = 重发尝试受限，使用CiFIFOCONm.TXAT 0 = 重发尝试次数不受限，CiFIFOCONm.TXAT将被忽略 bit 15-13 未实现：读为0 bit 12 BRSDIS：比特率切换禁止位 1 = 无论发送报文对象中的BRS状态如何，都禁止比特率切换 0 = 根据发送报文对象中的BRS进行比特率切换 bit 11 BUSY：CAN模块忙状态位 1 = CAN模块正在发送或接收报文 0 = CAN模块不工作 bit 10-9 WFT<1:0>：可选唤醒滤波器时间位 00 = T00FILTER 01 = T01FILTER 10 = T10FILTER 11 = T11FILTER 注： 请参见表7-5。 (1) bit 8 WAKFIL：使能CAN总线线路唤醒滤波器位 1 = 使用CAN总线线路滤波器来唤醒 0 = 不使用CAN总线线路滤波器来唤醒 bit 7 未实现：读为0 (1) bit 6 PXEDIS：协议异常事件检测禁止位 隐性FDF 位后的隐性“保留位”称为“协议异常”。 1 = 协议异常被视为格式错误。 0 = 如果检测到协议异常，CAN FD控制器模块将进入总线集成状态。 (1) bit 5 ISOCRCEN：使能CAN FD帧中的ISO CRC位 1 = CRC字段中包含填充位计数，使用非零CRC 初始化向量（符合ISO 11898-1:2015 规范） 0 = CRC字段中不包含填充位计数，使用全零CRC 初始化向量

注 1： 只能在配置模式下修改这些位。

 2020 Microchip Technology Inc. DS20006027A_CN 第27 页

# MCP2518FD

寄存器 3-7： CiCON —— CAN控制寄存器（续）

bit 4-0 DNCNT<4:0>：DeviceNet 过滤器位编号位 10011-11111 = 无效选择（最多可将数据的18 位与EID进行比较） 10010 = 最多可将数据字节2的bit 6与EID17 进行比较 ... 00001 = 最多可将数据字节0的bit 7与EID0进行比较 00000 = 不比较数据字节

注 1： 只能在配置模式下修改这些位。

寄存器 3-8： CiNBTCFG ——标称位时间配置寄存器

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 BRP<7:0> bit 31 bit 24

R/W-0 R/W-0 R/W-1 R/W-1 R/W-1 R/W-1 R/W-1 R/W-0 TSEG1<7:0> bit 23 bit 16

U-0 R/W-0 R/W-0 R/W-0 R/W-1 R/W-1 R/W-1 R/W-1 — TSEG2<6:0> bit 15 bit 8

U-0 R/W-0 R/W-0 R/W-0 R/W-1 R/W-1 R/W-1 R/W-1 — SJW<6:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-24 BRP<7:0>：波特率预分频比位 1111 1111 = T Q = 256/Fsys ... 0000 0000 = T Q = 1/Fsys bit 23-16 TSEG1<7:0>：时间段1 位（传播段 + 相位段1） 1111 1111 = 长度为256个T Q ... 0000 0000 = 长度为1个TQ bit 15 未实现：读为0 bit 14-8 TSEG2<6:0>：时间段2 位（相位段2） 111 1111 = 长度为128 个T Q ... 000 0000 = 长度为1 个TQ bit 7 未实现：读为0 bit 6-0 SJW<6:0>：同步跳转宽度位 111 1111 = 长度为128个T Q ... 000 0000 = 长度为1 个TQ

注 1： 只能在配置模式下修改该寄存器。

DS20006027A_CN 第 28页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-9： CiDBTCFG ——数据位时间配置寄存器

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 BRP<7:0> bit 31 bit 24

U-0 U-0 U-0 R/W-0 R/W-1 R/W-1 R/W-1 R/W-0 — — — TSEG1<4:0> bit 23 bit 16

U-0 U-0 U-0 U-0 R/W-0 R/W-0 R/W-1 R/W-1 — — — — TSEG2<3:0> bit 15 bit 8

U-0 U-0 U-0 U-0 R/W-0 R/W-0 R/W-1 R/W-1 — — — — SJW<3:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-24 BRP<7:0>：波特率预分频比位 1111 1111 = T Q = 256/Fsys ... 0000 0000 = T Q = 1/Fsys bit 23-21 未实现：读为0 bit 20-16 TSEG1<4:0>：时间段1 位（传播段 + 相位段1） 1 1111 = 长度为32个T Q ... 0 0000 = 长度为1个TQ bit 15-12 未实现：读为0 bit 11-8 TSEG2<3:0>：时间段2 位（相位段2） 1111 = 长度为16 个T Q ... 0000 = 长度为1个T Q bit 7-4 未实现：读为0 bit 3-0 SJW<3:0>：同步跳转宽度位 1111 = 长度为16 个T Q ... 0000 = 长度为1个T Q

注 1： 只能在配置模式下修改该寄存器。

 2020 Microchip Technology Inc. DS20006027A_CN 第29 页

# MCP2518FD

寄存器 3-10： CiTDC —— 发送器延时补偿寄存器

U-0 U-0 U-0 U-0 U-0 U-0 R/W-0 R/W-0 — — — — — — EDGFLTEN SID11EN bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 R/W-1 R/W-0 — — — — — — TDCMOD<1:0> bit 23 bit 16

U-0 R/W-0 R/W-0 R/W-1 R/W-0 R/W-0 R/W-0 R/W-0 — TDCO<6:0> bit 15 bit 8

U-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 — — TDCV<5:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-26 未实现：读为0 bit 25 EDGFLTEN：使能在总线集成状态下边沿滤波位 1 = 根据ISO 11898-1:2015 标准使能边沿滤波 0 = 禁止边沿滤波 bit 24 SID11EN：使能CAN FD基本格式报文中的12位SID 位 1 = RRS用作CAN FD基本格式报文中的SID11：SID<11:0> = {SID<10:0>, SID11} 0 = 不使用RRS；SID<10:0> 符合ISO 11898-1:2015规范 bit 23-18 未实现：读为0 bit 17-16 TDCMOD<1:0>：发送器延时补偿模式位；二次采样点（Secondary Sample Point，SSP） 10-11 = 自动；测量延时并添加TDCO。 01 = 手动；不测量，使用来自寄存器的TDCV + TDCO 00 = 禁止TDC bit 15 未实现：读为0 bit 14-8 TDCO<6:0>：发送器延时补偿偏移位；二次采样点（SSP） 二进制补码；偏移可以是正值、零或负值。 011 1111 = 63 x TSYSCLK ... 000 0000 = 0 x TSYSCLK ... 111 1111 = –64 x TSYSCLK bit 7-6 未实现：读为0 bit 5-0 TDCV<5:0>：发送器延时补偿值位；二次采样点（SSP） 11 1111 = 63 x TSYSCLK ... 00 0000 = 0 x TSYSCLK

注 1： 只能在配置模式下修改该寄存器。

DS20006027A_CN 第 30页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-11： CiTBC —— 时基计数器寄存器

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 TBC<31:24> bit 31 bit 24

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 TBC<23:16> bit 23 bit 16

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 TBC<15:8> bit 15 bit 8

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 TBC<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-0 TBC<31:0>：时基计数器位 这是自由运行的定时器，当TBCEN置1 时，每经过一个TBCPRE时钟递增一次。 注 1： 当TBCEN = 0 时，TBC将停止并复位。 2： 对CiTBC的任何写操作都会使TBC 的预分频器计数复位（CiTSCON.TBCPRE不受影响）。

 2020 Microchip Technology Inc. DS20006027A_CN 第31 页

# MCP2518FD

寄存器 3-12： CiTSCON ——时间戳控制寄存器

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 R/W-0 R/W-0 R/W-0 — — — — — TSRES TSEOF TBCEN bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 U-0 R/W-0 R/W-0 — — — — — — TBCPRE<9:8> bit 15 bit 8

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 TBCPRE<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-19 未实现：读为0 bit 18 TSRES：时间戳保留位（仅限FD帧） 1 = 在FDF 位后的位的采样点 0 = 在SOF的采样点 bit 17 TSEOF：时间戳EOF位 1 = 在帧生效后添加时间戳：
- 在EOF的倒数第二位之前RX未产生错误
- 在EOF结束之前TX未产生错误 0 = 在帧“开始”时添加时间戳：
- 经典帧：在SOF的采样点
- FD 帧：请参见TSRES位。 bit 16 TBCEN：时基计数器使能位 1 = 使能TBC 0 = 停止并复位TBC bit 15-10 未实现：读为0 bit 9-0 TBCPRE<9:0>：时基计数器预分频比位 1023 = 每经过1024个时钟TBC 递增一次 ... 0 = 每经过1个时钟TBC 递增一次

DS20006027A_CN 第 32页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-13： CiVEC ——中断代码寄存器

U-0 R-1 R-0 R-0 R-0 R-0 R-0 R-0 (1) — RXCODE<6:0> bit 31 bit 24

U-0 R-1 R-0 R-0 R-0 R-0 R-0 R-0 (1) — TXCODE<6:0> bit 23 bit 16

U-0 U-0 U-0 R-0 R-0 R-0 R-0 R-0 (1) — — — FILHIT<4:0> bit 15 bit 8

U-0 R-1 R-0 R-0 R-0 R-0 R-0 R-0 (1) — ICODE<6:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31 未实现：读为0 (1) bit 30-24 RXCODE<6:0>：接收中断标志代码位 1000001-1111111 = 保留 1000000 = 无中断 0100000-0111111 = 保留

0011111 = FIFO 31中断（RFIF<31>置1） ... 0000010 = FIFO 2 中断（RFIF<2> 置1） 0000001 = FIFO 1 中断（RFIF<1> 置1） 0000000 = 保留。FIFO 0无法接收。 bit 23 未实现：读为0 (1) bit 22-16 TXCODE<6:0>：发送中断标志代码位 1000001-1111111 = 保留 1000000 = 无中断 0100000-0111111 = 保留

0011111 = FIFO 31中断（TFIF<31> 置1） ... 0000001 = FIFO 1 中断（TFIF<1>置1） 0000000 = TXQ中断（TFIF<0>置1） bit 15-13 未实现：读为0 (1) bit 12-8 FILHIT<4:0>：命中过滤器编号位 11111 = 过滤器31 11110 = 过滤器30 ... 00001 = 过滤器1 00000 = 过滤器0

注 1： 如果有多个中断待处理，将指示编号最大的中断。

 2020 Microchip Technology Inc. DS20006027A_CN 第33 页

# MCP2518FD

寄存器 3-13： CiVEC ——中断代码寄存器（续）

bit 7 未实现：读为0 (1) bit 6-0 ICODE[6:0]：中断标志代码位 1001011-1111111 = 保留 1001010 = 发送尝试中断（CiTXATIF中的任意一位置1） 1001001 = 发送事件FIFO中断（CiTEFIF中的任意一位置1） 1001000 = 出现无效报文（IVMIF/IE） 1000111 = 工作模式发生改变（MODIF/IE） 1000110 = TBC溢出（TBCIF/IE） 1000101 = RX/TX MAB上溢/下溢（RX：在将前一个报文存储到存储器之前接收到新报文； TX：馈送TX MAB的速度不够快，以致于无法发送一致的数据。）（SERRIF/IE） 1000100 = 地址错误中断（向系统送入了非法FIFO地址）（SERRIF/IE） 1000011 = 接收FIFO溢出中断（CiRXOVIF 中的任意一位置1） 1000010 = 唤醒中断（WAKIF/WAKIE） 1000001 = 错误中断（CERRIF/IE） 1000000 = 无中断 0100000-0111111 = 保留 0011111 = FIFO 31中断（TFIF<31> 或RFIF<31>置1） ... 0000001 = FIFO 1 中断（TFIF<1>或RFIF<1>置1） 0000000 = TXQ中断（TFIF<0> 置1）

注 1： 如果有多个中断待处理，将指示编号最大的中断。

DS20006027A_CN 第 34页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-14： CiINT ——中断寄存器

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 IVMIE WAKIE CERRIE SERRIE RXOVIE TXATIE SPICRCIE ECCIE bit 31 bit 24

U-0 U-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 — — — TEFIE MODIE TBCIE RXIE TXIE bit 23 bit 16

HS/C-0 HS/C-0 HS/C-0 HS/C-0 R-0 R-0 R-0 R-0 (1) (1) (1) (1) IVMIF WAKIF CERRIFSERRIFRXOVIF TXATIF SPICRCIF ECCIF bit 15 bit 8

U-0 U-0 U-0 R-0 HS/C-0 HS/C-0 R-0 R-0 (1) (1) — — — TEFIF MODIF TBCIFRXIF TXIF bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31 IVMIE：无效报文中断允许位 bit 30 WAKIE：总线唤醒中断允许位 bit 29 CERRIE：CAN总线错误中断允许位 bit 28 SERRIE：系统错误中断允许位 bit 27 RXOVIE：接收FIFO溢出中断允许位 bit 26 TXATIE：发送尝试中断允许位 bit 25 SPICRCIE：SPI CRC 错误中断允许位 bit 24 ECCIE：ECC 错误中断允许位 bit 23-21 未实现：读为0 bit 20 TEFIE：发送事件FIFO中断允许位 bit 19 MODIE：模式改变中断允许位 bit 18 TBCIE：时基计数器中断允许位 bit 17 RXIE：接收FIFO中断允许位 bit 16 TXIE：发送FIFO中断允许位 (1) bit 15 IVMIF：无效报文中断标志位 (1) bit 14 WAKIF：总线唤醒中断标志位 (1) bit 13 CERRIF：CAN总线错误中断标志位 (1) bit 12 SERRIF：系统错误中断标志位 1 = 发生了系统错误 0 = 未发生系统错误 bit 11 RXOVIF：接收对象溢出中断标志位 1 = 发生了接收FIFO溢出 0 = 未发生接收FIFO溢出 bit 10 TXATIF：发送尝试中断标志位

注 1： 标志由硬件置1，由应用程序清零。

 2020 Microchip Technology Inc. DS20006027A_CN 第35 页

# MCP2518FD

寄存器 3-14： CiINT —— 中断寄存器（续）

bit 9 SPICRCIF：SPI CRC错误中断标志位 bit 8 ECCIF：ECC错误中断标志位 bit 7-5 未实现：读为0 bit 4 TEFIF：发送事件FIFO中断标志位 1 = 有TEF 中断待处理 0 = 没有TEF 中断待处理 (1) bit 3 MODIF：工作模式改变中断标志位 1 = 工作模式发生了改变（OPMOD 已改变） 0 = 模式未发生改变 (1) bit 2 TBCIF：时基计数器溢出中断标志位 1 = TBC已溢出 0 = TBC未溢出 bit 1 RXIF：接收FIFO中断标志位 1 = 有接收FIFO中断待处理 0 = 没有接收FIFO中断待处理 bit 0 TXIF：发送FIFO中断标志位 1 = 有发送FIFO中断待处理 0 = 没有发送FIFO中断待处理

注 1： 标志由硬件置1，由应用程序清零。

DS20006027A_CN 第 36页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-15： CiRXIF ——接收中断状态寄存器

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 RFIF<31:24> bit 31 bit 24

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 RFIF<23:16> bit 23 bit 16

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 RFIF<15:8> bit 15 bit 8

R-0 R-0 R-0 R-0 R-0 R-0 R-0 U-0 RFIF<7:1> — bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

(1) bit 31-1 RFIF<31:1>：接收FIFO中断待处理位 1 = 有一个或多个已允许的接收FIFO中断待处理 0 = 没有已允许的接收FIFO中断待处理 bit 0 未实现：读为0

注 1： RFIF = 已使能的RXFIFO标志的逻辑或；这些标志将在FIFO条件终止时清零。

 2020 Microchip Technology Inc. DS20006027A_CN 第37 页

# MCP2518FD

寄存器 3-16： CiRXOVIF —— 接收溢出中断状态寄存器

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 RFOVIF<31:24> bit 31 bit 24

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 RFOVIF<23:16> bit 23 bit 16

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 RFOVIF<15:8> bit 15 bit 8

R-0 R-0 R-0 R-0 R-0 R-0 R-0 U-0 RFOVIF<7:1> — bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-1 RFOVIF<31:1>：接收FIFO溢出中断待处理位 1 = 中断待处理 0 = 中断未处于待处理状态 bit 0 未实现：读为0 注 1： 标志需在FIFO寄存器中清零。

DS20006027A_CN 第 38页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-17： CiTXIF ——发送中断状态寄存器

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 TFIF<31:24> bit 31 bit 24

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 (1) TFIF<23:16> bit 23 bit 16

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 (1) TFIF<15:8> bit 15 bit 8

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 (1) TFIF<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

(2) (1) bit 31-0 TFIF<31:0>：发送FIFO/TXQ中断待处理位 1 = 有一个或多个已允许的发送FIFO/TXQ中断待处理 0 = 没有已允许的发送FIFO/TXQ 中断待处理 注 1： TFIF = 已使能的TXFIFO标志的逻辑或；这些标志将在FIFO条件终止时清零。 2： TFIF<0>用于发送队列。

 2020 Microchip Technology Inc. DS20006027A_CN 第39 页

# MCP2518FD

寄存器 3-18： CiTXATIF ——发送尝试中断状态寄存器

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 (1) TFATIF<31:24> bit 31 bit 24

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 (1) TFATIF<23:16> bit 23 bit 16

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 (1) TFATIF<15:8> bit 15 bit 8

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 (1) TFATIF<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

(2) (1) bit 31-0 TFATIF<31:0>：发送FIFO/TXQ 尝试中断待处理位 1 = 中断待处理 0 = 中断未处于待处理状态 注 1： 标志需在FIFO寄存器中清零。 2： TFATIF<0> 用于发送队列。

DS20006027A_CN 第 40页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-19： CiTXREQ ——发送请求寄存器

S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 TXREQ<31:24> bit 31 bit 24

S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 TXREQ<23:16> bit 23 bit 16

S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 TXREQ<15:8> bit 15 bit 8

S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 S/HC-0 TXREQ<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-1 TXREQ<31:1>：报文发送请求位 TXEN= 1（对象配置为发送对象） 将该位置1会请求发送报文。 在成功发送对象中排队的报文之后，该位将自动清零。 该位不能用于中止发送。 TXEN= 0（对象配置为接收对象） 该位无影响 bit 0 TXREQ<0>：发送队列报文发送请求位 将该位置1会请求发送报文。 在成功发送对象中排队的报文之后，该位将自动清零。 该位不能用于中止发送。

 2020 Microchip Technology Inc. DS20006027A_CN 第41 页

# MCP2518FD

寄存器 3-20： CiTREC ——发送 /接收错误计数寄存器

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 R-1 R-0 R-0 R-0 R-0 R-0 — — TXBO TXBP RXBP TXWARN RXWARN EWARN bit 23 bit 16

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 TEC<7:0> bit 15 bit 8

R-0 R-0 R-0 R-0 R-0 R-0 R-0 R-0 REC<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-22 未实现：读为0 bit 21 TXBO：发送器处于离线状态位（TEC > 255） 在配置模式下，由于模块未处于总线上而将TXBO置1。 bit 20 TXBP：发送器处于被动错误状态位（TEC > 127） bit 19 RXBP：接收器处于被动错误状态位（REC > 127） bit 18 TXWARN：发送器处于警告错误状态位（128 > TEC > 95） bit 17 RXWARN：接收器处于警告错误状态位（128 > REC > 95） bit 16 EWARN：发送器或接收器处于警告错误状态位 bit 15-8 TEC<7:0>：发送错误计数器位 bit 7-0 REC<7:0>：接收错误计数器位

DS20006027A_CN 第 42页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-21： CiBDIAG0 —— 总线诊断寄存器 0

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 DTERRCNT<7:0> bit 31 bit 24

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 DRERRCNT<7:0> bit 23 bit 16

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 NTERRCNT<7:0> bit 15 bit 8

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 NRERRCNT<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-24 DTERRCNT<7:0>：数据比特率发送错误计数器位 bit 23-16 DRERRCNT<7:0>：数据比特率接收错误计数器位 bit 15-8 NTERRCNT<7:0>：标称比特率发送错误计数器位 bit 7-0 NRERRCNT<7:0>：标称比特率接收错误计数器位

 2020 Microchip Technology Inc. DS20006027A_CN 第43 页

# MCP2518FD

寄存器 3-22： CiBDIAG1 —— 总线诊断寄存器 1

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 U-0 R/W-0 R/W-0 DLCMM ESI DCRCERR DSTUFERR DFORMERR — DBIT1ERR DBIT0ERR bit 31 bit 24

R/W-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 TXBOERR — NCRCERR NSTUFERR NFORMERR NACKERR NBIT1ERR NBIT0ERR bit 23 bit 16

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 EFMSGCNT<15:8> bit 15 bit 8

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 EFMSGCNT<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31 DLCMM：DLC 不匹配位 在发送或接收期间，指定的DLC大于FIFO元素的PLSIZE。 bit 30 ESI：接收的CAN FD 报文的ESI 标志置1。 bit 29 DCRCERR：与标称比特率相同（见下文）。 bit 28 DSTUFERR：与标称比特率相同（见下文）。 bit 27 DFORMERR：与标称比特率相同（见下文）。 bit 26 未实现：读为0 bit 25 DBIT1ERR：与标称比特率相同（见下文）。 bit 24 DBIT0ERR：与标称比特率相同（见下文）。 bit 23 TXBOERR：器件进入离线状态（且自动恢复）。 bit 22 未实现：读为0 bit 21 NCRCERR：接收的报文的CRC校验和不正确。输入报文的CRC与通过接收到的数据计算得到的CRC 不匹配。 bit 20 NSTUFERR：在接收报文的一部分中，序列中包含了5个以上相等位，而报文中不允许出现这种序列。 bit 19 NFORMERR：接收帧的固定格式部分格式错误。 bit 18 NACKERR：发送报文未应答。 bit 17 NBIT1ERR：在发送报文（仲裁字段除外）期间，器件要发送隐性电平（逻辑值为1 的位），但监视 到的总线值为显性。 bit 16 NBIT0ERR：在发送报文（或应答位、主动错误标志或过载标志）期间，器件要发送显性电平（逻辑 值为0的数据或标识符位），但监视的总线值为隐性。 bit 15-0 EFMSGCNT<15:0>：无错误报文计数器位

DS20006027A_CN 第 44页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-23： CiTEFCON ——发送事件 FIFO 控制寄存器

U-0 U-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) — — — FSIZE<4:0> bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 S/HC-1 U-0 S/HC-0 — — — — — FRESET — UINC bit 15 bit 8

U-0 U-0 R/W-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) — — TEFTSEN— TEFOVIE TEFFIE TEFHIE TEFNEIE bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-29 未实现：读为0 (1) bit 28-24 FSIZE<4:0>：FIFO大小位 0_0000 = FIFO深度为1个报文 0_0001 = FIFO深度为2个报文 0_0010 = FIFO深度为3个报文 ... 1_1111 = FIFO深度为32 个报文 bit 23-11 未实现：读为0 bit 10 FRESET：FIFO复位位 1 = 当该位置1时，FIFO复位；当FIFO复位时，该位由硬件清零。用户在采取任何操作前应等待该位 清零。 0 = 无影响 bit 9 未实现：读为0 bit 8 UINC：递增尾部位 当该位置1时，FIFO尾部递增一个报文。 bit 7-6 未实现：读为0 (1) bit 5 TEFTSEN：发送事件FIFO时间戳使能位 1 = 对TEF 中的对象加时间戳 0 = 不对TEF 中的对象加时间戳 bit 4 未实现：读为0 bit 3 TEFOVIE：发送事件FIFO溢出中断允许位 1 = 允许在发生溢出事件时产生中断 0 = 禁止在发生溢出事件时产生中断 bit 2 TEFFIE：发送事件FIFO满中断允许位 1 = 允许在FIFO满时产生中断 0 = 禁止在FIFO满时产生中断

注 1： 只能在配置模式下修改这些位。

 2020 Microchip Technology Inc. DS20006027A_CN 第45 页

# MCP2518FD

寄存器 3-23： CiTEFCON ——发送事件 FIFO 控制寄存器（续）

bit 1 TEFHIE：发送事件FIFO半满中断允许位 1 = 允许在FIFO半满时产生中断 0 = 禁止在FIFO半满时产生中断 bit 0 TEFNEIE：发送事件FIFO非空中断允许位 1 = 允许在FIFO非空时产生中断 0 = 禁止在FIFO非空时产生中断

注 1： 只能在配置模式下修改这些位。

DS20006027A_CN 第 46页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-24： CiTEFSTA ——发送事件FIFO状态寄存器

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 15 bit 8

U-0 U-0 U-0 U-0 HS/C-0 R-0 R-0 R-0 (1) (1) (1) — — — — TEFOVIF TEFFIF TEFHIFTEFNEIF bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-4 未实现：读为0 bit 3 TEFOVIF：发送事件FIFO溢出中断标志位 1 = 发生了溢出事件 0 = 未发生溢出事件 (1) bit 2 TEFFIF：发送事件FIFO满中断标志位 1 = FIFO已满 0 = FIFO 未满 (1) bit 1 TEFHIF：发送事件FIFO半满中断标志位 1 = FIFO ≥ 半满 0 = FIFO < 半满 (1) bit 0 TEFNEIF：发送事件FIFO非空中断标志位 1 = FIFO非空，至少包含一个报文 0 = FIFO 为空

注 1： 该位是只读位，用于反映FIFO的状态。

 2020 Microchip Technology Inc. DS20006027A_CN 第47 页

# MCP2518FD

寄存器 3-25： CiTEFUA —— 发送事件FIFO用户地址寄存器

R-x R-x R-x R-x R-x R-x R-x R-x TEFUA<31:24> bit 31 bit 24

R-x R-x R-x R-x R-x R-x R-x R-x TEFUA<23:16> bit 23 bit 16

R-x R-x R-x R-x R-x R-x R-x R-x TEFUA<15:8> bit 15 bit 8

R-x R-x R-x R-x R-x R-x R-x R-x TEFUA<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-0 TEFUA<31:0>：发送事件FIFO用户地址位 读取该寄存器将返回用于读取下一个对象的地址（FIFO尾部）。

注 1： 在配置模式下，不能保证可以正确读取该寄存器，应当仅在模块不处于配置模式时访问该寄存器。

DS20006027A_CN 第 48页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-26： CiTXQCON ——发送队列控制寄存器

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) (1) PLSIZE<2:0> FSIZE<4:0> bit 31 bit 24

U-0 R/W-1 R/W-1 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 — TXAT<1:0> TXPRI<4:0> bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 S/HC-1 R/W/HC-0 S/HC-0 (3) (2) — — — — — FRESETTXREQUINC bit 15 bit 8

R-1 U-0 U-0 R/W-0 U-0 R/W-0 U-0 R/W-0 TXEN — — TXATIE — TXQEIE — TXQNIE bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

(1) bit 31-29 PLSIZE<2:0>：有效负载大小位 000 = 8个数据字节 001 = 12 个数据字节 010 = 16 个数据字节 011 = 20 个数据字节 100 = 24 个数据字节 101 = 32 个数据字节 110 = 48 个数据字节 111 = 64 个数据字节 (1) bit 28-24 FSIZE<4:0>：FIFO大小位 0_0000 = FIFO深度为1个报文 0_0001 = FIFO深度为2个报文 0_0010 = FIFO深度为3个报文 ... 1_1111 = FIFO深度为32 个报文 bit 23 未实现：读为0 bit 22-21 TXAT<1:0>：重发尝试位 CiCON.RTXAT置1时使能该功能。 00 = 禁止重发尝试 01 = 3 次重发尝试 10 = 重发尝试次数不受限制 11 = 重发尝试次数不受限制 bit 20-16 TXPRI<4:0>：报文发送优先级位 00000 = 最低报文优先级 ... 11111 = 最高报文优先级 bit 15-11 未实现：读为0 注 1： 只能在配置模式下修改这些位。 2： 该位在报文完成（或中止）或FIFO复位时更新。 3： FRESET 在配置模式下置1，在正常模式下自动清零。

 2020 Microchip Technology Inc. DS20006027A_CN 第49 页

# MCP2518FD

寄存器 3-26： CiTXQCON ——发送队列控制寄存器（续）

(3) bit 10 FRESET：FIFO复位位 1 = 当该位置1时，FIFO复位；当FIFO复位时，该位由硬件清零。用户在采取任何操作前应等待该位 清零。 0 = 无影响 (2) bit 9 TXREQ：报文发送请求位 1 = 请求发送报文；在成功发送TXQ中排队的所有报文之后，该位会自动清零。 0 = 在该位置1的情况下清零该位将请求中止报文。 bit 8 UINC：递增头部位 当该位置1时，FIFO头部递增一个报文。 bit 7 TXEN：TX使能 1 = 发送报文队列。该位将总是读为1。 bit 6-5 未实现：读为0 bit 4 TXATIE：超过发送尝试次数中断允许位 1 = 允许中断 0 = 禁止中断 bit 3 未实现：读为0 bit 2 TXQEIE：发送队列空中断允许位 1 = 允许在TXQ为空时产生中断 0 = 禁止在TXQ为空时产生中断 bit 1 未实现：读为0 bit 0 TXQNIE：发送队列未满中断允许位 1 = 允许在TXQ未满时产生中断 0 = 禁止在TXQ未满时产生中断 注 1： 只能在配置模式下修改这些位。 2： 该位在报文完成（或中止）或FIFO复位时更新。 3： FRESET在配置模式下置1，在正常模式下自动清零。

DS20006027A_CN 第 50页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-27： CiTXQSTA —— 发送队列状态寄存器

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 23 bit 16

U-0 U-0 U-0 R-0 R-0 R-0 R-0 R-0 (1) — — — TXQCI<4:0> bit 15 bit 8

HS/C-0 HS/C-0 HS/C-0 HS/C-0 U-0 R-1 U-0 R-1 (2)(3) (2)(3) TXABTTXLARBTXERRTXATIF — TXQEIF — TXQNIF (2)(3)

bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-13 未实现：读为0 (1) bit 12-8 TXQCI<4:0>：发送队列报文索引位 读取该寄存器将返回一个报文索引，该索引指向FIFO下一次尝试发送的报文。 (2)(3) bit 7 TXABT：报文中止状态位 1 = 报文中止 0 = 报文成功完成 (2)(3) bit 6 TXLARB：报文仲裁失败状态位 1 = 报文在发送过程中仲裁失败 0 = 报文在发送过程中仲裁未失败 (2)(3) bit 5 TXERR：在发送过程中检测到错误位 1 = 发送报文时发生总线错误 0 = 发送报文时未发生总线错误 bit 4 TXATIF：超过发送尝试次数中断待处理位 1 = 中断待处理 0 = 中断未处于待处理状态 bit 3 未实现：读为0 bit 2 TXQEIF：发送队列空中断标志位 1 = TXQ 为空 0 = TXQ 非空，至少有一个报文在排队等待发送 bit 1 未实现：读为0 bit 0 TXQNIF：发送队列未满中断标志位 1 = TXQ 未满 0 = TXQ 已满

注 1： TXQCI<4:0> 位为 TXQ 中的报文分配从零开始索引值。如果 TXQ 为 4 个报文深（FSIZE = 5’h03），则 TXQCI 将根据TXQ的状态从0到3 中取值。 2： 当TXREQ 置1或使用SPI写0时，该位清零。 3： 该位在报文完成（或中止）或TXQ复位时更新。

 2020 Microchip Technology Inc. DS20006027A_CN 第51 页

# MCP2518FD

寄存器 3-28： CiTXQUA—— 发送队列用户地址寄存器

R-x R-x R-x R-x R-x R-x R-x R-x TXQUA<31:24> bit 31 bit 24

R-x R-x R-x R-x R-x R-x R-x R-x TXQUA<23:16> bit 23 bit 16

R-x R-x R-x R-x R-x R-x R-x R-x TXQUA<15:8> bit 15 bit 8

R-x R-x R-x R-x R-x R-x R-x R-x TXQUA<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-0 TXQUA<31:0>：TXQ用户地址位 读取该寄存器将返回用于写入下一个报文的地址（TXQ头部）。

注 1： 在配置模式下，不能保证可以正确读取该寄存器，应当仅在模块不处于配置模式时访问该寄存器。

DS20006027A_CN 第 52页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-29： CiFIFOCONm —— FIFO 控制寄存器 m（m = 1 至 31）

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) (1) PLSIZE<2:0> FSIZE<4:0> bit 31 bit 24

U-0 R/W-1 R/W-1 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 — TXAT<1:0> TXPRI<4:0> bit 23 bit 16

U-0 U-0 U-0 U-0 U-0 S/HC-1 R/W/HC-0 S/HC-0 (3) (2) — — — — — FRESETTXREQUINC bit 15 bit 8

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) (1) TXENRTREN RXTSENTXATIE RXOVIE TFERFFIE TFHRFHIE TFNRFNIE bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

(1) bit 31-29 PLSIZE<2:0>：有效负载大小位 000 = 8个数据字节 001 = 12 个数据字节 010 = 16 个数据字节 011 = 20 个数据字节 100 = 24 个数据字节 101 = 32 个数据字节 110 = 48 个数据字节 111 = 64 个数据字节 (1) bit 28-24 FSIZE<4:0>：FIFO大小位 0_0000 = FIFO深度为1个报文 0_0001 = FIFO深度为2个报文 0_0010 = FIFO深度为3个报文 ... 1_1111 = FIFO深度为32 个报文 bit 23 未实现：读为0 bit 22-21 TXAT<1:0>：重发尝试位 CiCON.RTXAT置1时使能该功能。 00 = 禁止重发尝试 01 = 3 次重发尝试 10 = 重发尝试次数不受限制 11 = 重发尝试次数不受限制 bit 20-16 TXPRI<4:0>：报文发送优先级位 00000 = 最低报文优先级 ... 11111 = 最高报文优先级

注 1： 只能在配置模式下修改这些位。 2： 该位在报文完成（或中止）或FIFO复位时更新。 3： FRESET 在配置模式下置1，在正常模式下自动清零。

 2020 Microchip Technology Inc. DS20006027A_CN 第53 页

# MCP2518FD

寄存器 3-29： CiFIFOCONm —— FIFO 控制寄存器 m（m = 1 至 31）（续）

bit 15-11 未实现：读为0 (3) bit 10 FRESET：FIFO复位位 1 = 当该位置1时，FIFO复位；当FIFO复位时，该位由硬件清零。用户在采取任何操作前应等待该位 清零。 0 = 无影响 (2) bit 9 TXREQ：报文发送请求位 TXEN = 1（FIFO配置为发送FIFO） 1 = 请求发送报文；在成功发送FIFO中排队的所有报文之后，该位会自动清零。 0 = 在该位置1的情况下清零该位将请求中止报文。 TXEN = 0（FIFO配置为接收FIFO） 该位无影响。 bit 8 UINC：递增头部/尾部位 TXEN = 1（FIFO配置为发送FIFO） 当该位置1时，FIFO头部递增一个报文。 TXEN = 0（FIFO配置为接收FIFO） 当该位置1时，FIFO尾部递增一个报文。 (1) bit 7 TXEN：TX/RX FIFO选择位 1 = 发送FIFO 0 = 接收FIFO bit 6 RTREN：自动RTR使能位 1 = 接收到远程发送时，TXREQ 置1。 0 = 接收到远程发送时，TXREQ 不受影响。 (1) bit 5 RXTSEN：接收的报文时间戳使能位 1 = 捕捉RAM中接收到的报文对象的时间戳。 0 = 不捕捉时间戳。 bit 4 TXATIE：超过发送尝试次数中断允许位 1 = 允许中断 0 = 禁止中断 bit 3 RXOVIE：溢出中断允许位 1 = 允许在发生溢出事件时产生中断 0 = 禁止在发生溢出事件时产生中断 bit 2 TFERFFIE：发送/接收FIFO空/ 满中断允许位 TXEN = 1（FIFO配置为发送FIFO） 发送FIFO空中断允许 1 = 允许在FIFO为空时产生中断 0 = 禁止在FIFO为空时产生中断 TXEN = 0（FIFO配置为接收FIFO） 接收FIFO满中断允许 1 = 允许在FIFO满时产生中断 0 = 禁止在FIFO满时产生中断

注 1： 只能在配置模式下修改这些位。 2： 该位在报文完成（或中止）或FIFO复位时更新。 3： FRESET在配置模式下置1，在正常模式下自动清零。

DS20006027A_CN 第 54页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-29： CiFIFOCONm —— FIFO 控制寄存器 m（m = 1 至 31）（续）

bit 1 TFHRFHIE：发送/接收FIFO半空/ 半满中断允许位 TXEN = 1（FIFO配置为发送FIFO） 发送FIFO半空中断允许 1 = 允许在FIFO半空时产生中断 0 = 禁止在FIFO半空时产生中断 TXEN = 0（FIFO配置为接收FIFO） 接收FIFO半满中断允许 1 = 允许在FIFO半满时产生中断 0 = 禁止在FIFO半满时产生中断 bit 0 TFNRFNIE：发送/接收FIFO未满/ 非空中断允许位 TXEN = 1（FIFO配置为发送FIFO） 发送FIFO未满中断允许 1 = 允许在FIFO未满时产生中断 0 = 禁止在FIFO未满时产生中断 TXEN = 0（FIFO配置为接收FIFO） 接收FIFO非空中断允许 1 = 允许在FIFO非空时产生中断 0 = 禁止在FIFO非空时产生中断

注 1： 只能在配置模式下修改这些位。 2： 该位在报文完成（或中止）或FIFO复位时更新。 3： FRESET 在配置模式下置1，在正常模式下自动清零。

 2020 Microchip Technology Inc. DS20006027A_CN 第55 页

# MCP2518FD

寄存器 3-30： CiFIFOSTAm —— FIFO状态寄存器 m（m = 1至 31）

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 31 bit 24

U-0 U-0 U-0 U-0 U-0 U-0 U-0 U-0 — — — — — — — — bit 23 bit 16

U-0 U-0 U-0 R-0 R-0 R-0 R-0 R-0 (1) — — — FIFOCI<4:0> bit 15 bit 8

HS/C-0 HS/C-0 HS/C-0 HS/C-0 HS/C-0 R-0 R-0 R-0 (2)(3) (2)(3) TXABTTXLARBTXERRTXATIF RXOVIF TFERFFIF TFHRFHIF TFNRFNIF (2)(3)

bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-13 未实现：读为0 (1) bit 12-8 FIFOCI<4:0>：FIFO报文索引位 TXEN = 1（FIFO配置为发送FIFO） 读取该位域将返回一个索引，该索引指向FIFO下一次尝试发送的报文。 TXEN = 0（FIFO配置为接收FIFO） 读取该位域将返回一个索引，FIFO使用该索引保存下一个报文。 (2)(3) bit 7 TXABT：报文中止状态位 1 = 报文中止 0 = 报文成功完成 (2)(3) bit 6 TXLARB：报文仲裁失败状态位 1 = 报文在发送过程中仲裁失败 0 = 报文在发送过程中仲裁未失败 (2)(3) bit 5 TXERR：在发送过程中检测到错误位 1 = 发送报文时发生总线错误 0 = 发送报文时未发生总线错误 bit 4 TXATIF：超过发送尝试次数中断待处理位 TXEN = 1（FIFO配置为发送FIFO） 1 = 中断待处理 0 = 中断未处于待处理状态 TXEN = 0（FIFO配置为接收FIFO） 读为0 注 1： FIFOCI<4:0>位为FIFO中的报文分配从零开始索引值。如果FIFO为4个报文深（FSIZE = 5’h03），则FIFOCI 将根据FIFO的状态从0 到3 中取值。 2： 当TXREQ 置1或使用SPI写0时，该位清零。 3： 该位在报文完成（或中止）或FIFO复位时更新。

DS20006027A_CN 第 56页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-30： CiFIFOSTAm —— FIFO状态寄存器 m（m = 1至 31）（续）

bit 3 RXOVIF：接收FIFO溢出中断标志位 TXEN = 1（FIFO配置为发送FIFO） 未使用，读为0 TXEN = 0（FIFO配置为接收FIFO） 1 = 发生了溢出事件 0 = 未发生溢出事件 bit 2 TFERFFIF：发送/接收FIFO空/ 满中断标志位 TXEN = 1（FIFO配置为发送FIFO） 发送FIFO空中断标志 1 = FIFO 为空 0 = FIFO 非空；至少有一个报文在排队等待发送 TXEN = 0（FIFO配置为接收FIFO） 接收FIFO满中断标志 1 = FIFO 已满 0 = FIFO 未满 bit 1 TFHRFHIF：发送/接收FIFO半空/半满中断标志位 TXEN = 1（FIFO配置为发送FIFO） 发送FIFO半空中断标志 1 = FIFO ≤ 半满 0 = FIFO > 半满 TXEN = 0（FIFO配置为接收FIFO） 接收FIFO半满中断标志 1 = FIFO ≥ 半满 0 = FIFO < 半满 bit 0 TFNRFNIF：发送/接收FIFO未满/非空中断标志位 TXEN = 1（FIFO配置为发送FIFO） 发送FIFO未满中断标志 1 = FIFO 未满 0 = FIFO 已满 TXEN = 0（FIFO配置为接收FIFO） 接收FIFO非空中断标志 1 = FIFO 非空，至少包含一个报文 0 = FIFO 为空 注 1： FIFOCI<4:0>位为FIFO中的报文分配从零开始索引值。如果FIFO为4个报文深（FSIZE = 5’h03），则FIFOCI 将根据FIFO的状态从0 到3 中取值。 2： 当TXREQ 置1或使用SPI写0时，该位清零。 3： 该位在报文完成（或中止）或FIFO复位时更新。

 2020 Microchip Technology Inc. DS20006027A_CN 第57 页

# MCP2518FD

寄存器 3-31： CiFIFOUAm —— FIFO用户地址寄存器 m（m = 1 至31）

R-x R-x R-x R-x R-x R-x R-x R-x FIFOUA<31:24> bit 31 bit 24

R-x R-x R-x R-x R-x R-x R-x R-x FIFOUA<23:16> bit 23 bit 16

R-x R-x R-x R-x R-x R-x R-x R-x FIFOUA<15:8> bit 15 bit 8

R-x R-x R-x R-x R-x R-x R-x R-x FIFOUA<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31-0 FIFOUA<31:0>：FIFO用户地址位 TXEN = 1（FIFO配置为发送FIFO） 读取该寄存器将返回用于写入下一个报文的地址（FIFO头部）。 TXEN = 0（FIFO配置为接收FIFO） 读取该寄存器将返回用于读取下一个报文的地址（FIFO尾部）。

注 1： 在配置模式下，不能保证可以正确读取该位，应当仅在模块不处于配置模式时访问该位。

DS20006027A_CN 第 58页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-32： CiFLTCONm —— 过滤器控制寄存器 m（m = 0 至7）

R/W-0 U-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) FLTEN3 — — F3BP<4:0> bit 31 bit 24

R/W-0 U-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) FLTEN2 — — F2BP<4:0> bit 23 bit 16

R/W-0 U-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) FLTEN1 — — F1BP<4:0> bit 15 bit 8

R/W-0 U-0 U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 (1) FLTEN0 — — F0BP<4:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31 FLTEN3：使能过滤器3 接收报文位 1 = 使能过滤器 0 = 禁止过滤器 bit 30-29 未实现：读为0 (1) bit 28-24 F3BP<4:0>：过滤器3命中时指向FIFO的指针位 1_1111 = 与过滤器匹配的报文存储在FIFO 31中 1_1110 = 与过滤器匹配的报文存储在FIFO 30中 ........ 0_0010 = 与过滤器匹配的报文存储在FIFO 2中 0_0001 = 与过滤器匹配的报文存储在FIFO 1中 0_0000 = 保留；FIFO 0 为TX队列，不能接收报文 bit 23 FLTEN2：使能过滤器2 接收报文位 1 = 使能过滤器 0 = 禁止过滤器 bit 22-21 未实现：读为0 (1) bit 20-16 F2BP<4:0>：过滤器2命中时指向FIFO的指针位 1_1111 = 与过滤器匹配的报文存储在FIFO 31中 1_1110 = 与过滤器匹配的报文存储在FIFO 30中 ........ 0_0010 = 与过滤器匹配的报文存储在FIFO 2中 0_0001 = 与过滤器匹配的报文存储在FIFO 1中 0_0000 = 保留；FIFO 0 为TX队列，不能接收报文 bit 15 FLTEN1：使能过滤器1 接收报文位 1 = 使能过滤器 0 = 禁止过滤器 bit 14-13 未实现：读为0

注 1： 仅当禁止相应过滤器（FLTEN = 0）时，才能修改该位。

 2020 Microchip Technology Inc. DS20006027A_CN 第59 页

# MCP2518FD

寄存器 3-32： CiFLTCONm —— 过滤器控制寄存器 m（m = 0 至7）（续）

(1) bit 12-8 F1BP<4:0>：过滤器1命中时指向FIFO的指针位 1_1111 = 与过滤器匹配的报文存储在FIFO 31中 1_1110 = 与过滤器匹配的报文存储在FIFO 30中 ........ 0_0010 = 与过滤器匹配的报文存储在FIFO 2中 0_0001 = 与过滤器匹配的报文存储在FIFO 1中 0_0000 = 保留；FIFO 0 为TX队列，不能接收报文 bit 7 FLTEN0：使能过滤器0 接收报文位 1 = 使能过滤器 0 = 禁止过滤器 bit 6-5 未实现：读为0 (1) bit 4-0 F0BP<4:0>：过滤器0命中时指向FIFO的指针位 1_1111 = 与过滤器匹配的报文存储在FIFO 31中 1_1110 = 与过滤器匹配的报文存储在FIFO 30中 ........ 0_0010 = 与过滤器匹配的报文存储在FIFO 2中 0_0001 = 与过滤器匹配的报文存储在FIFO 1中 0_0000 = 保留；FIFO 0 为TX队列，不能接收报文

注 1： 仅当禁止相应过滤器（FLTEN = 0）时，才能修改该位。

DS20006027A_CN 第 60页  2020 Microchip Technology Inc.

# MCP2518FD

寄存器 3-33： CiFLTOBJm ——过滤器对象寄存器 m（m = 0至31）

U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 — EXIDE SID11 EID<17:13> bit 31 bit 24

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 EID<12:5> bit 23 bit 16

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 EID<4:0> SID<10:8> bit 15 bit 8

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 SID<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31 未实现：读为0 bit 30 EXIDE：扩展标识符使能位 如果MIDE = 1： 1 = 仅匹配带有扩展标识符的报文 0 = 仅匹配带有标准标识符的报文 bit 29 SID11：标准标识符过滤位 bit 28-11 EID<17:0>：扩展标识符过滤位 在DeviceNet 模式下，这些位是用于前18个数据位的过滤位。 bit 10-0 SID<10:0>：标准标识符过滤位

注 1： 仅当禁止过滤器（CiFLTCON.FLTENm = 0）时，才能修改该寄存器。

 2020 Microchip Technology Inc. DS20006027A_CN 第61 页

# MCP2518FD

寄存器 3-34： CiMASKm ——屏蔽寄存器m（m = 0至 31）

U-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 — MIDE MSID11 MEID<17:13> bit 31 bit 24

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 MEID<12:5> bit 23 bit 16

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 MEID<4:0> MSID<10:8> bit 15 bit 8

R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 R/W-0 MSID<7:0> bit 7 bit 0

图注： R = 可读位 W = 可写位 U = 未实现位，读为0 -n = POR时的值 1 = 置1 0 = 清零 x = 未知

bit 31 未实现：读为0 bit 30 MIDE：标识符接收模式位 1 = 只匹配与过滤器中EXIDE位对应的报文类型（标准ID或扩展ID） 0 = 如果过滤器匹配，则同时匹配标准报文帧和扩展报文帧 bit 29 MSID11：标准标识符屏蔽位 bit 28-11 MEID<17:0>：扩展标识符屏蔽位 在DeviceNet 模式下，这些位是用于前18个数据位的屏蔽位。 bit 10-0 MSID<10:0>：标准标识符屏蔽位

DS20006027A_CN 第 62页  2020 Microchip Technology Inc.

# MCP2518FD

3.3 报文存储器3.3.1.3 RAM 读取 在RAM 读取期间，解码器检查来自RAM 的输出数据的 MCP2518FD 器件包含一个2 KB RAM，用于存储报文 一致性并删除奇偶校验位。它可以纠正单个位错误并检 对象。有三种不同的报文对象： 测双位错误。
- 表3-5：TXQ和TX FIFO使用的发送报文对象。 图3-2： 报文存储器构成
- 表3-6：RX FIFO使用的接收报文对象。
- 表3-7：TEF对象。 TEF 图3-2说明了报文对象如何映射到RAM中。TEF、TXQ TXࡇ䱏 和每个FIFO 的报文对象数均可配置。图中仅详细显示 了FIFO2 的报文对象。对于TXQ 和每个FIFO 而言，每 FIFO1 个报文对象（有效负载）的数据字节数可单独配置。 FIFO2˖ᣕ᮷ሩ䊑0 FIFO和报文对象只能在配置模式下配置。 首先分配TEF 对象。只有CiCON.STEF = 1 时才会保留FIFO2˖ᣕ᮷ሩ䊑1 RAM中的空间。 接下来分配TXQ对象。只有CiCON.TXQEN = 1时才会 FIFO2˖ᣕ᮷ሩ䊑n 保留RAM中的空间。 接下来分配FIFO1 至FIFO31的报文对象。FIFO3 这种高度灵活的配置可以有效地使用RAM。 报文对象的地址取决于所选的配置。应用程序不必计算 FIFO31 地址。用户地址字段提供要读取或写入的下一个报文对 象的地址。

3.3.1 RAM ECC图3-3： ECC 逻辑 RAM 由纠错码（ECC）保护。ECC 逻辑支持单个位错 ECC.PARITYޕ߉ሶᮠᦞ 误纠正（Single Error Correction，SEC）和双位错误 检测（Double Error Detection，DED）。 P<6:0>D<31:0> 除32 个数据位外，SEC/DED还需要7 个奇偶校验位。 图3-3给出了ECC 逻辑的框图。 ᮠᦞ/ ཷṑ傼ڦ㕆⸱ಘ

3.3.1.1 ECC 使能和禁止 可以通过将ECCCON.ECCEN置1来使能ECC逻辑。当DP<38:0>DE<38:0> 使能ECC 时，将对写入RAM 的数据进行编码，对从 RAM读取的数据进行解码。 ECCCON.ECCEN 禁止 ECC 逻辑时，数据写入 RAM，奇偶校验位取自 DR<38:0> ECCCON.PARITY。这使用户能够测试ECC 逻辑。在 读取期间，将剔除奇偶校验位，按原样回读数据。 RAM 512x(32+7) 3.3.1.2 RAM 写入 QR<38:0> 在RAM 写入期间，编码器计算奇偶校验位并将奇偶校 验位加到输入数据。 QR<31:0>ECCSTAT.SECIF 䀓⸱ಘ ᰐཷڦṑ傼ECCSTAT.DEDIF

D<31:0>DO<31:0>

ECCCON.ECCEN

Q<31:0>

䈫ਆᮠᦞ

 2020 Microchip Technology Inc. DS20006027A_CN 第63 页

# MCP2518FD

表3-5： 发送报文对象（TXQ 和TX FIFO）

BitBitBitBitBitBitBitBit 字 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

T0 31:24 — — SID11 EID<17:13> 23:16 EID<12:5> 15:8 EID<4:0> SID<10:8> 7:0 SID<7:0> T1 31:24 SEQ<22:15> 23:16 SEQ<14:7> 15:8 SEQ<6:0> ESI 7:0 FDF BRS RTR IDE DLC<3:0> (1) T231:24 发送数据字节 3 23:16 发送数据字节 2 15:8 发送数据字节 1 7:0 发送数据字节 0 T3 31:24 发送数据字节 7 23:16 发送数据字节 6 15:8 发送数据字节 5 7:0 发送数据字节 4 Ti 31:24 发送数据字节 n 23:16 发送数据字节 n-1 15:8 发送数据字节 n-2 7:0 发送数据字节 n-3

bit T0.31-30 未实现：读为x bit T0.29 SID11：在FD模式下，标准ID可通过r1扩展为12位 bit T0.28-11 EID<17:0>：扩展标识符 bit T0.10-0 SID<10:0>：标准标识符 bit T1.31-9 SEQ<22:0>：用于跟踪发送事件FIFO中已发送报文的序列 bit T1.8 ESI：错误状态指示符 在CAN-CAN网关模式（CiCON.ESIGM=1）下，发送的ESI标志为T1.ESI与CAN 控制器被动错误状态 的“逻辑或”结果。 在正常模式下，ESI 指示错误状态 1 = 发送节点处于被动错误状态 0 = 发送节点处于主动错误状态 bit T1.7 FDF：FD 帧；用于区分CAN 和CAN FD格式 bit T1.6 BRS：比特率切换；选择是否切换数据比特率 bit T1.5 RTR：远程发送请求；不适用于CAN FD bit T1.4 IDE：标识符扩展标志；用于区分基本格式和扩展格式 bit T1.3-0 DLC<3:0>：数据长度码 注 1： 数据字节0-n：在控制寄存器（CiFIFOCONm.PLSIZE<2:0>）中单独配置有效负载大小。

DS20006027A_CN 第 64页  2020 Microchip Technology Inc.

# MCP2518FD

表3-6： 接收报文对象

BitBitBitBitBitBitBitBit 字 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

R0 31:24 — — SID11 EID<17:13> 23:16 EID<12:5> 15:8 EID<4:0> SID<10:8> 7:0 SID<7:0> R1 31:24 ————————

23:16 ————————

15:8 FILHIT<4:0> ——ESI

7:0 FDF BRS RTR IDE DLC<3:0> (2) R231:24 RXMSGTS<31:24> 23:16 RXMSGTS<23:16> 15:8 RXMSGTS<15:8> 7:0 RXMSGTS<7:0> (1) R331:24 接收数据字节 3 23:16 接收数据字节 2 15:8 接收数据字节 1 7:0 接收数据字节 0 R4 31:24 接收数据字节 7 23:16 接收数据字节 6 15:8 接收数据字节 5 7:0 接收数据字节 4 Ri 31:24 接收数据字节 n 23:16 接收数据字节 n-1 15:8 接收数据字节 n-2 7:0 接收数据字节 n-3

bit R0.31-30 未实现：读为x bit R0.29 SID11：在FD模式下，标准ID可通过r1扩展为12位 bit R0.28-11 EID<17:0>：扩展标识符 bit R0.10-0 SID<10:0>：标准标识符 bit R1.31-16 未实现：读为x bit R1.15-11 FILTHIT<4:0>：命中的过滤器；匹配的过滤器编号 bit R1.10-9 未实现：读为x bit R1.8 ESI：错误状态指示符 1 = 发送节点处于被动错误状态 0 = 发送节点处于主动错误状态 bit R1.7 FDF：FD 帧；用于区分CAN 和CAN FD格式 bit R1.6 BRS：比特率切换；指示是否切换数据比特率 bit R1.5 RTR：远程发送请求；不适用于CAN FD bit R1.4 IDE：标识符扩展标志；用于区分基本格式和扩展格式 bit R1.3-0 DLC<3:0>：数据长度码 bit R2.31-0 RXMSGTS<31:0>：接收报文时间戳 注 1： RXMOBJ：数据字节0-n：在FIFO控制寄存器（CiFIFOCONm.PLSIZE<2:0>）中单独配置有效负载大小。 2： R2（RXMSGTS）仅存在于CiFIFOCONm.RXTSEN 置 1的对象中。

 2020 Microchip Technology Inc. DS20006027A_CN 第65 页

# MCP2518FD

表3-7： 发送事件 FIFO对象

BitBitBitBitBitBitBitBit 字 31/23/15/730/22/14/629/21/13/528/20/12/427/19/11/326/18/10/225/17/9/124/16/8/0

TE0 31:24 — — SID11 EID<17:13> 23:16 EID<12:5> 15:8 EID<4:0> SID<10:8> 7:0 SID<7:0> TE1 31:24 SEQ<22:15> 23:16 SEQ<14:7> 15:8 SEQ<6:0> ESI 7:0 FDF BRS RTR IDE DLC<3:0> (1) TE231:24 TXMSGTS<31:24> 23:16 TXMSGTS<23:16> 15:8 TXMSGTS<15:8> 7:0 TXMSGTS<7:0>

bit TE0.31-30 未实现：读为x bit TE0.29 SID11：在FD 模式下，标准ID可通过r1 扩展为12位 bit TE0.28-11 EID<17:0>：扩展标识符 bit TE0.10-0 SID<10:0>：标准标识符 bit TE1.31-9 SEQ<22:0>：用于跟踪已发送报文的序列 bit TE1.8 ESI：错误状态指示符 1 = 发送节点处于被动错误状态 0 = 发送节点处于主动错误状态 bit TE1.7 FDF：FD帧；用于区分CAN和CAN FD 格式 bit TE1.6 BRS：比特率切换；选择是否切换数据比特率 bit TE1.5 RTR：远程发送请求；不适用于CAN FD bit TE1.4 IDE：标识符扩展标志；用于区分基本格式和扩展格式 bit TE1.3-0 DLC<3:0>：数据长度码

(1) bit TE2.31-0 TXMSGTS<31:0>：发送报文时间戳 注 1： TE2（TXMSGTS）仅存在于CiTEFCON.TEFTSEN置1的对象中。

DS20006027A_CN 第 66页  2020 Microchip Technology Inc.

# MCP2518FD

有关模式0,0和模式1,1的详细输入和输出时序，请参

### 4.0 SPI 接口

见图7-1。 MCP2518FD 器件可与大多数单片机上提供的串行外设 表4-1 列出了SPI指令及其格式。 接口端口直接相连。单片机中的SPI 必须在8 位工作模 式下配置为0,0或1,1模式。 注 1： SCK 的频率必须小于或等于 SYSCLK 频率 SFR 和报文存储器（RAM）通过SPI 指令访问。图4-1 的一半。这可确保SCK 和SYSCLK 之间能 说明了SPI 指令的通用格式（SPI 模式0,0）。每条指 够正常同步。 令均以nCS 驱动为低电平（nCS 的下降沿）开始。4 位 2： 为 了 最 大 限 度 地 降 低 休 眠 电 流， 命令和12位地址在SCK的上升沿移入SDI。在写指令期 MCP2518FD 器件的SDO 引脚在器件处于 间，数据位在SCK的上升沿移入SDI。在读指令期间， 休 眠 模 式 时 不 得 悬 空。这 可 以 通 过 在 数据位在SCK 的下降沿移出SDO。一条指令可传输一 MCP2518FD器件处于休眠模式时使能MCU 个或多个数据字节。数据位在SCK 的下降沿更新，在 内与SDO 引脚相连的引脚上的上拉或下拉 SCK的上升沿必须有效。每条指令均以nCS驱动为高电电阻来实现。 平（nCS的上升沿）结束。

图4-1： SPI指令格式

nCS

1 2 3 4 5 6 7 8 9 1010  11 12 13 14 1516 17 18 19 20 21 22 2324

SCK

䟷ṧ ᴤᯠ 䟷ṧ

SDIC<3> C<2> C<1> C<0> A<11> A<10> A<9> A<8> A<7> A<6> A<5> A<4> A<3> A<2> A<1> A<0>D<7> D<6> D<5> D<4> D<3> D<2> D<1> D<0>

ᴤᯠ䟷ṧ

SDO D<7> D<6> D<5> D<4> D<3> D<2> D<1> D<0>

表4-1： SPI指令 名称 格式 说明 RESET C = 0b0000；A = 0x000 将内部寄存器复位为默认状态；选择配置模式。 READ C = 0b0011；A；D = SDO 从地址A读取SFR/RAM的内容。 WRITE C = 0b0010；A；D = SDI 将SFR/RAM的内容写入地址A。 READ_CRC C = 0b1011；A；N；从地址A读取SFR/RAM的内容。N个数据字节。2字节CRC。 D = SDO；CRC = SDO基于C、A、N和D计算CRC。 WRITE_CRC C = 0b1010；A；N；将SFR/RAM的内容写入地址A。N个数据字节。2字节CRC。 D = SDI；CRC = SDI基于C、A、N和D计算CRC。 WRITE_SAFE C = 0b1100；A；将SFR/RAM的内容写入地址A。写入前校验CRC。基于C、A和D 计 D = SDI；CRC = SDI算CRC。 图注： C = 命令（4位），A = 地址（12位），D = 数据（1 至n字节），N = 字节数（1字节），CRC（2字节）

 2020 Microchip Technology Inc. DS20006027A_CN 第67 页

# MCP2518FD

4.1 SFR访问4.1.2 SFR读指令 —— READ 图4-3 说明了访问SFR 时的READ 指令。该指令从nCS SFR访问是面向字节的。可以使用一条指令读取或写入 变为低电平开始。命令（C<3:0> = 0b0011）后跟地址 任意数量的数据字节。在每个数据字节后，地址自动递 （A<11:0>）。之后，来自地址A（DB[A]）的数据字节 增1。地址从0x3FF计满返回至0x000，从0xFFF计满 移出，接 着 来 自 地 址 A+1（DB[A+1]）的数据字节移 返回至0xE00。 出。可以读取任意数量的数据字节。该指令在nCS变为 以下SPI 指令仅显示不同的位域及其值。每条指令均遵 高电平时结束。 循通用格式，如图4-1所示。 4.1.3 SFR写指令 —— WRITE 4.1.1 RESET 图4-4说明了访问SFR时的WRITE指令。该指令从nCS 图4-2 说 明 了RESET 指 令。该 指 令 从nCS 变 为 低 变为低电平开始。命令（C<3:0> = 0b0010）后跟地址 电 平 开 始。命 令（C<3:0> = 0b0000）后 跟 地 址 （A<11:0>）。之后，数据字节移入地址A（DB[A]）， （A<11:0> = 0x000）。该 指 令 在nCS 变 为 高 电 平 时 然后移入地址A+1（DB[A+1]）。可以写入任意数量的 结束。 数据字节。该指令在nCS 变为高电平时结束。 只有在器件进入配置模式后才能发出RESET 指令。所 数 据 字 节 在 第8 个 数 据 位 之 后 的SCK 下降沿写入寄 有SFR 和状态机都会像上电复位（Power-on Reset， 存器。 POR）期间一样复位，器件会立即转换为配置模式。 报文存储器不会更改。图4-2：RESET指令 当nCS变为高电平时，实际复位在指令结束时发生。 nCSվ⭥ᒣ 0b0000 0x000nCS儈⭥ᒣ

图4-3： SFR 读指令

nCSվ⭥ᒣ 0b0011 A<11:0> DB[A] DB[A+1] DB[A+n-1]nCS儈⭥ᒣ

图4-4： SFR 写指令

nCSվ⭥ᒣ 0b0010 A<11:0> DB[A] DB[A+1] DB[A+n-1]nCS儈⭥ᒣ

DS20006027A_CN 第 68页  2020 Microchip Technology Inc.

# MCP2518FD

4.2 报文存储器访问从RAM读取命令时读取的大小必须始终为4个数据字节 的倍数。在地址字段之后以及在SPI 上每读取四个数据 报 文 存 储 器（RAM）访 问 是 面 向 字 的（一 次 4 个 字 字节之后，从RAM 内部读取字。如果在SDO 上读取的 节）。可以使用一条指令读取或写入大小为4 个数据字 大小达到4 个数据字节的倍数之前nCS 变为高电平，则 节任意倍数的数据。在每个数据字节后，地址自动递增 单片机会丢弃不完整的读取。 1。地址从0xBFF计满返回至0x400。 读/ 写操作必须按字对齐。始终假定地址的低2 位为0。4.2.2报文存储器写指令——WRITE 无法执行非对齐的读/写操作。图4-6说明了访问RAM时的WRITE_CRC指令。该指令从 以下SPI 指令仅显示不同的位域及其值。每条指令均遵nCS变为低电平开始。命令（C<3:0> = 0b0010）后跟地 循通用格式，如图4-1所示。址（A<11:0>）。之后，数据字节移入地址A（DB[A]）， 然后移入地址A+1（DB[A+1]）。该指令在nCS 变为高 4.2.1 报文存储器读指令 —— READ电平时结束。 图4-5说明了访问RAM时的READ指令。该指令从nCS写入命令时写入的大小必须始终为4 个数据字节的倍 变为低电平开始。命令（C<3:0> = 0b0011）后跟地址数。每4个数据字节之后，在SCK的下降沿，均会写入 （A<11:0>）。之后，来自地址A（DB[A]）的数据字节RAM 字。如果在SDI上接收的大小达到4 个数据字节的 移出，接 着 来 自 地 址A+1（DB[A+1]）的 数 据字 节移倍数之前nCS变为高电平，则具有不完整字的数据不会 出。该指令在nCS变为高电平时结束。写入RAM。

图4-5： 报文存储器读指令

DW[A] nCSվ⭥ᒣ 0b0011 A<11:0>nCS儈⭥ᒣ DB[A] DB[A+1] DB[A+2]DB[A+3]

图4-6： 报文存储器写指令

DW[A] nCSվ⭥ᒣ 0b0010 A<11:0>nCS儈⭥ᒣ DB[A] DB[A+1] DB[A+2]DB[A+3]

 2020 Microchip Technology Inc. DS20006027A_CN 第69 页

# MCP2518FD

4.3 带 CRC的SPI 命令MCP2518FD器件使用以下发生器多项式：CRC-16/USB （0x8005）。CRC-16 可以检测所有单个位和双位错 为了在SPI 通信期间检测或避免位错误，可以使用带 误、所有奇数位数的错误、所有长度小于或等于16 的 CRC的SPI命令。 突发错误，以及大多数更长的突发错误。这可以极好地 检测系统中可能发生的SPI 通信错误，即使是在噪声环 4.3.1 CRC 计算 境下，也可以极大地降低错误通信的风险。 CRC计算器与SPI移位寄存器并行工作（见图4-7）。 读取和写入TX 或RX 报文对象时使用最大数量的数据 当nCS置为有效时，CRC 计算器复位为0xFFFF。位。具有64字节数据 + 12字节ID和时间戳的RX报文对 象包含76字节（即608位）。相比之下，USB数据包最 CRC 计算的结果在CRC 命令的数据段之后提供。在检 多包含1024位。CRC-16的汉明距离为4 至1024 位。 测到CRC 不匹配的情况下，CRC 计算的结果写入CRC 寄存器。如果CRC不匹配，则CRC.CRCERRIF置1。

图4-7： CRC 计算

nCS SDO SDISPI 〫սᇴᆈಘ

SCK

༽սCRC䇑㇇ಘ SDI SDO

CRCભԔ˖ ᮠᦞ⇥㔃ᶏCRC㔃᷌ ޘᆹ

DS20006027A_CN 第 70页  2020 Microchip Technology Inc.

# MCP2518FD

4.3.2 带CRC 的SFR 读指令 ——4.3.3 带CRC 的 SFR 写指令 —— READ_CRCWRITE_CRC 图4-8 说明了访问SFR 时的READ_CRC 指令。该指令图4-9 说明了访问SFR时的WRITE_CRC指令。该指令 从nCS 变为低电平开始。命令（C<3:0> = 0b1011）后从nCS变为低电平开始。命令（C<3:0> = 0b1010）后跟 跟 地 址（A<11:0>）以 及 数 据 字 节 数（N<7:0>）。之地址（A<11:0>）以及数据字节数（N<7:0>）。之后， 后，来自地址A（DB[A]）的数据字节移出，接着来自地数 据 字 节 移 入 地 址 A（DB[A]），然 后 移 入 地 址 A+1 址A+1（DB[A+1]）的数据字节移出。可以读取任意数量（DB[A+1]）。可以写入任意数量的数据字节。接下 的数据字节。接下来，CRC移出（CRC<15:0>）。该指来，CRC 移入（CRC<15:0>）。该指令在nCS 变为高 令在nCS变为高电平时结束。电平时结束。 系 统 将 CRC 提 供 给 单 片 机，单 片 机 校 验 CRC。在数据字节移入SDI后，在SCK的下降沿，SFR会写入寄 MCP2518FD 器件内的READ_CRC 命令期间，CRC 不存器。数据字节在CRC 校验前写入寄存器。 匹配时不产生中断。 CRC 校验在写访问结束时进行。如果CRC 不匹配，则 如果在CRC 的最后一个字节移出之前nCS 变为高电会产生CRC 错误中断：CRC.CRCERRIF。 平，则会产生CRC格式错误中断：CRC.FERRIF。 如果在CRC 的最后一个字节移入之前nCS 变为高电 平，则会产生CRC 格式错误中断：CRC.FERRIF。

图4-8： 带 CRC 的SFR 读指令

nCSվ⭥ᒣ 0b1011 A<11:0> N<7:0>DB[A] DB[A+1] DB[A+n-1]CRC<15:8> CRC<7:0> nCS儈⭥ᒣ

图4-9： 带 CRC 的SFR 写指令

nCS Low 0b1010 A<11:0> N<7:0>DB[A] DB[A+1] DB[A+n-1]CRC<15:8> CRC<7:0> nCS High

4.3.4 带CRC 的SFR 安全写指令——仅在CRC校验后且发生匹配时，数据字节才写入SFR。 WRITE_SAFE 如果CRC 不匹配，则数据字节不会写入SFR，且会产 该指令确保只将正确的数据写入SFR。生CRC错误中断：CRC.CRCERRIF。 图4-10 说明了访问SFR时的WRITE_SAFE指令。该指如果在CRC的最后一个字节移入之前nCS变为高电 令从nCS变为低电平开始。命令（C<3:0> = 0b1100）平，则会产生CRC格式错误中断：CRC.FERRIF。 后跟地址（A<11:0>）。之后，一个数据字节移入地址 A（DB[A]）。接下来，CRC（CRC<15:0>）移入。该 指令在nCS变为高电平时结束。

图4-10： 带 CRC 的SFR 安全写指令

nCSվ⭥ᒣ 0b1100 A<11:0> DB[A] CRC<15:8> CRC<7:0>nCS儈⭥ᒣ

 2020 Microchip Technology Inc. DS20006027A_CN 第71 页

# MCP2518FD

4.3.5 带CRC 的报文存储器读指令 ——如果在CRC 的最后一个字节移出之前nCS 变为高电 READ_CRC平，则会产生CRC 格式错误中断：CRC.FERRIF。 图4-11说明了访问RAM时的READ_CRC指令。该指令 4.3.6 带CRC 的报文存储器写指令 —— 从nCS 变为低电平开始。命令（C<3:0> = 0b1011）后 WRITE_CRC 跟地址（A<11:0>）以及数据字数（N<7:0>）。之后， 来自地址A（DB[A]）的数据字节移出，接着来自地址图4-12说明了访问RAM时的写指令。该指令从nCS变 A+1（DB[A+1]）的 数 据 字 节 移 出。接 下 来，CRC为 低 电 平 开 始。命 令（C<3:0> = 0b1010）后 跟 地 址 （CRC<15:0>）移出。该 指 令 在nCS 变 为 高 电 平 时（A<11:0>）以及数据字数（N<7:0>）。之后，数据字节 结束。移入地址A（DB[A]），然后移入地址A+1（DB[A+1]）。 接下来，CRC（CRC<15:0>）移入。该指令在nCS 变 读/ 写操作必须按字对齐。始终假定地址的低2 位为0。 为高电平时结束。 无法执行非对齐的读/写操作。 写入命令时写入的大小必须始终为4 个数据字节的倍 读取命令时读取的大小应始终为4 个数据字节的倍数。 数。每4个数据字节之后，在SCK的下降沿，均会写入 在“N”字段之后以及在SPI 上每读取四个数据字节之 RAM。如果在SDI 上接收的大小达到4 个数据字节的倍 后，从RAM 内部读取字。如果在SDO 上读取的大小达 数之前nCS变为高电平，则具有不完整字的数据不会写 到4 个数据字节的倍数之前nCS 变为高电平，则单片机 入RAM。 会丢弃不完整的读取。 CRC 校验在写访问结束时进行。如果CRC 不匹配，则 系 统 将 CRC 提 供 给 单 片 机，单 片 机 校 验 CRC。在 会产生CRC 中断：CRC.CRCERRIF。 MCP2518FD 器件内的READ_CRC 命令期间，CRC 不 匹配时不产生中断。如果在CRC的最后一个字节移入之前nCS变为高电 平，则会产生CRC 中断：CRC.FERRIF。

图4-11： 带 CRC 的报文存储器读指令

DW[A] nCSվ⭥ᒣ 0b1011 A<11:0>N<7:0> CRC<15:8> CRC<7:0>nCS儈⭥ᒣ DB[A] DB[A+1] DB[A+2]DB[A+3]

图4-12： 带 CRC 的报文存储器写指令

DW[A] nCSվ⭥ᒣ 0b1010 A<11:0>N<7:0> CRC<15:8> CRC<7:0>nCS儈⭥ᒣ DB[A] DB[A+1] DB[A+2]DB[A+3]

4.3.7 带CRC 的报文存储器安全写指令 ——（DB[A+2] ）和 A+3 （DB[A+3] ）。接下来，CRC WRITE_SAFE（CRC<15:0>）移入。该 指 令 在nCS 变 为 高 电 平 时 结束。 该指令确保只将正确的数据写入RAM。 仅在CRC 校验后且发生匹配时，数据字才写入RAM。 图4-10说明了访问RAM时的WRITE_SAFE指令。该指 令从nCS 变为低电平开始。命令（C<3:0> = 0b1100）如果CRC不匹配，则数据字不会写入RAM，且会产生 后 跟 地 址（A<11:0>）。之后，数 据 字 节 移 入 地 址 ACRC错误中断：CRC.CRCERRIF。 （DB[A]），然 后 移 入 地 址 A+1（DB[A+1]）、A+2如果在CRC的最后一个字节移入之前nCS变为高电 平，则会产生CRC 中断：CRC.FERRIF。

图4-13： 带 CRC 的报文存储器安全写指令

DW[A] nCSվ⭥ᒣ 0b1100 A<11:0>CRC<15:8> CRC<7:0>nCS儈⭥ᒣ DB[A] DB[A+1] DB[A+2]DB[A+3]

DS20006027A_CN 第 72页  2020 Microchip Technology Inc.

# MCP2518FD

时钟生成的时间参考可以是外部40、20 或4 MHz 晶

### 5.0 振荡器

振、陶瓷谐振器或外部时钟。 图5-1 给出了MCP2518FD器件中振荡器的框图。振荡器 OSC寄存器控制振荡器。可以使能PLL，将4 MHz时钟 系统生成SYSCLK，用于CAN FD控制器模块以及RAM 乘以10。 访问。CAN FD社区建议使用40或20 MHz SYSCLK。 内部40/20 MHz可以2 分频。 内部生成的时钟可以分频并在CLKO引脚上输出。

图5-1： MCP2518FD 振荡器框图

OSC1

CLKODIV 4ǃ40ᡆ20 MHz CLKINǃCLKO ᲦᥟᡆOSCDIS1ǃ2ǃ4 ઼10仁࠶ 䲦⬧䉀ᥟಘ

OSC2 PLL40/20 MHz x10

1઼2仁࠶SYSCLK

SCLKDIV PLLEN

 2020 Microchip Technology Inc. DS20006027A_CN 第73 页

# MCP2518FD

- INTOD：中断引脚可配置为漏极开路或推挽输出。

### 6.0 I/O配置

IOCON寄存器用于配置I/O引脚：6.0.1中断引脚
- CLKO/SOF：选择时钟输出或帧起始。MCP2518FD 器件包含三个不同的中断引脚，请参见
- TXCANOD：TXCAN 可配置为推挽输出或漏极开路图6-1： 输出。漏极开路输出允许用户将多个控制器连接到
- INT 在 CiINT 寄存器中的任何中断发生时置为有效 一起来构建CAN网络，无需使用收发器。 （xIF和xIE），包括RX和TX中断。
- INT0和INT1可配置为GPIO（具有与PIC单片机中
- INT1/GPIO1可配置为GPIO或RX中断引脚 相似的寄存器）或者发送和接收中断。 （CiINT.RXIF 和RXIE）。
- INT0/GPIO0/XSTBY也可用于自动控制收发器的待
- INT0/GPIO0可配置为GPIO或TX中断引脚 机引脚。 （CiINT.TXIF和TXIE）。 所有中断引脚低电平有效。

图6-1： 中断引脚

INT1 ᧕᭦ѝᯝਁ INT0INT 䘱ѝᯝؑOR

᚟ѝᯝ

DS20006027A_CN 第 74页  2020 Microchip Technology Inc.

# MCP2518FD

### 7.0 电气规范

7.1 绝对最大值 †

VDD ............................................................................................................................................................... –0.3V至6.0V 所有I/O相对于GND 的直流电压....................................................................................................... –0.3V至VDD + 0.3V 虚拟结温TVJ（IEC60747-1） ..................................................................................................................-40°C至+165°C 引脚焊接温度（10 秒） ......................................................................................................................................... +300°C 所有引脚上的ESD保护（IEC 801；人体模型）...................................................................................................... ±4 kV 所有引脚上的ESD保护（IEC 801；机器模型）.....................................................................................................±400V 所有引脚上的ESD保护（IEC 801；充电设备模型） .............................................................................................±750V

† 注：如果器件的工作条件超过上述“最大值”，可能对器件造成永久性损坏。上述值仅代表本规范规定的极限工作 条件，不代表器件在上述极限值或超出极限值的情况下仍可正常工作。器件长时间工作在最大值条件下，其可靠性可 能受到影响。

 2020 Microchip Technology Inc. DS20006027A_CN 第75 页

# MCP2518FD

表7-1： 直流特性 直流规范 电气特性： 扩展 级（E）：TAMB = –40°C 至 +125°C ； 高 温（H）：TAMB = –40°C 至 +150°C ；V DD = 2.7V至5.5V

符号 特性 最小值 典型值 最大值 单位 条件/ 备注

VDD 引脚 VDD 电压范围 2.7 — 5.5 V 确保RAM数据保持 VPORH 上电复位电压 — — 2.65 V 器件释放POR前VDD上的最高电压 V PORL 上电复位电压 2.2 — — V 器件置为POR前VDD上的最低电压 S VDD 用于确保POR的VDD上升率 0.05 — — V/ms 注1 IDD 电源电流 — 15 20 mA 40 MHz SYSCLK， 20 MHz SPI 活动 IDDS 休眠电流 — 15 60 μA 时钟停止 TAMB ≤ +85°C（注1） — — 600 — 时钟停止 TAMB ≤ +150°C IDD LPM LPM电流 — 4 10 μA 数字逻辑掉电

数字输入引脚 VIH 高电平输入电压 0.7 V DD — VDD + 0.3 V VIL 低电平输入电压 -0.3 — 0.3 V DD V VOSCPP OSC1检测电压 0.5 — — V OSC1 引脚上的最小峰-峰值电压 （注1） I LI 输入泄漏电流 OSC1 -5 — +5 μA 所有其他引脚 -1 — +1 μA

数字输出引脚 VOH 高电平输出电压 V DD – 0.7 — — V IOH = –2 mA，VDD = 2.7V VOL 低电平输出电压 TXCAN — — 0.6 V IOL = 8 mA，VDD = 2.7V 所有其他引脚 — — 0.6 V IOL = 2 mA，VDD = 2.7V 注 1： 已经过表征，但未完全测试。

DS20006027A_CN 第 76页  2020 Microchip Technology Inc.

# MCP2518FD

表7-2： CLKOUT和 SOF交流特性 交流规范 电气特性： 扩 展 级（E）：TAMB = –40°C 至 +125°C ； 高 温（H）：TAMB = –40°C 至 +150°C；V DD = 2.7V至5.5V

符号 特性 最小值 典型值 最大值 单位 条件/ 备注 TCLKOH CLKO输出高电平时间 8 — — ns 40 MHz时（注1） TCLKOL CLKO输出低电平时间 8 — — ns 注1 TCLKOR CLKO输出上升时间 — — 5 ns 注1 TCLKOF CLKO输出下降时间 — — 5 ns 注1 TSOFH SOF输出高电平时间— 31 TOSC — ns 注2

TSOFPD SOF传播延时：RXCAN下— 1 TOSC — ns 注2 降沿到SOF上升沿的时间 注 1： 已经过表征，但未完全测试。 2： 仅供设计参考。

表 7-3： 晶振交流特性 交流规范 电气特性： 扩展级（E）：TAMB = –40°C 至 +125°C ；高温（H）：TAMB = –40°C 至 +150°C；VDD = 2.7V至5.5V 符号 特性 最小值 典型值 最大值 单位 条件/备注 F OSC1 , CLKI OSC1 输入频率 2 40 40 MHz 外部数字时钟 FOSC 1,4 M OSC1 输入频率 4 - 0.5% 4 4 + 0.5% MHz 4 MHz晶振/ 谐振器（注1） FDRIFT SYSCLK频率漂移 — — 10 ppm 4 MHz时，因内部PLL 额外引起的 SYSCLK频率漂移（注1） F OSC1,20M OSC1 输入频率 20 - 0.5% 20 20 + 0.5% MHz 20 MHz晶振/谐振器（注1） F OSC 1,40M OSC1 输入频率 40 - 0.5% 40 40 + 0.5% MHz 40 MHz晶振/谐振器（注1） TOSC 1 TOSC1= 1/F OSC1,x 25 — — ns TOSC 1H OSC1 输入高电平时间 0.45 *— 0.55 *ns 注1 TOSCTOSC TOSC 1L OSC1输入低电平时间0.45 *— 0.55 *ns 注1 TOSCTOSC TOSC 1R OSC1 输入上升时间 — — 20 ns 注2 TOSC1 F OSC1输入下降时间— — 20 ns 注2

DCOSC 1 OSC1 的占空比 45 50 55 % 外部时钟占空比要求（注1） TOSCSTAB 振荡器稳定周期 — — 3 ms 从POR到最终频率（注1） TOSCSLEEP 从休眠到振荡器稳定的时间 — — 3 ms 从休眠到最终频率（注1） GM ,4M 跨导 1470 — 2210 μA/V 4 MHz晶振（注2） G M ,40M 跨导 2040 — 3060 μA/V 40 MHz晶振（注2） 注 1： 已经过表征，但未完全测试。 2： 仅供设计参考。

 2020 Microchip Technology Inc. DS20006027A_CN 第77 页

# MCP2518FD

表7-4： CAN 比特率 交流规范 电气特性： 扩展 级（E）：TAMB = –40°C 至 +125°C ； 高 温（H）：TAMB = –40°C 至 +150°C ；V DD = 2.7V至5.5V

符号 特性 最小值 典型值 最大值 单位 条件/ 备注 BRNOM 标称比特率 0.125 0.5 1 Mbps BRDATA 数据比特率 0.5 2 8 Mbps BR DATA ≥ BRNOM 注 1： 测试的比特率。器件允许配置更多的比特率，包括比所述最小值更小的比特率。

表 7-5： CAN RX 滤波器交流特性 交流规范 电气特性： 扩展 级（E）：TAMB = –40°C 至 +125°C ； 高 温（H）：TAMB = –40°C 至 +150°C ；V DD = 2.7V至5.5V 符号 特性 最小值 典型值 最大值 单位 条件/ 备注 T PROP 滤波器传播延时 — 1 — ns 注2 TFILTER 滤波时间 50— 100ns T00 FILTER 80140T01 FILTER 130220T10 FILTER 225390T11 FILTER 注3 TREVOCERY 使输出再次变为高电平5 — — ns 注2 所需的最小输入高电平时间

注 1： 已经过表征，但未完全测试。 2： 仅供设计参考。 3： RXCAN 上短于最小TFILTER时间的脉冲将被忽略；长于最大TFILTER 时间的脉冲将唤醒器件。

DS20006027A_CN 第 78页  2020 Microchip Technology Inc.

# MCP2518FD

表7-6： SPI交流特性 交流规范 电气特性： 扩展级（E）：TAMB = –40°C至+125°C； 高温（H）：TAMB = –40°C至+150°C；VDD = 2.7V至5.5V

参数 符号 特性 最小值 典型值 最大值 单位 条件 F SCK SCK输入频率— — 20 MHz 注3

TSCK SCK周期，TSCK=1/FSCK 50 — — ns 注3 1 TSCKH SCK高电平时间 20 — — ns 2 TSCKL SCK低电平时间 20 — — ns 3 TSCKR SCK上升时间 — — 100 ns 注2 4 TSCKF SCK下降时间— — 100 ns 注2

5 TCS2 SCK nCS ↓到SCK ↑的时间 TSCK/2 — — ns 6 TSCK2 CS SCK ↑到nCS ↑的时间 TSCK — — ns 7 TSDI 2 SCK SDI 建立时间：SDI ↕到SCK ↑的时间 5 — — ns 8 TSCK2 SDI SDI 保持时间：SCK ↑到SDI ↕的时间 5 — — ns 9 TSCK2 SDO SDO有效时间：SCK ↓到SDO ↕的时间— — 20 ns C LOAD = 50 pF

10 TCS2 SDOZ SDO 高阻态时间：nCS ↑到SDO— — 2 TSCK ns C LOAD = 50 pF 高阻态的时间 11 TCSD nCS ↑到nCS ↓的时间 TSCK — — ns 注2

注 1： 已经过表征，但未完全测试。 2： 仅供设计参考。 3： FSCK必须小于或等于FSYSCLK/2。

图 7-1： SPI I/O 时序

nCS

51 2 36 ⁑ᔿ1,11,1

SCK0,00,0

7 8

SDIC<3>A<0> D<7>D<0>

SDOD<7>D<0>

表7-7： 温度规范 参数 符号 最小值 典型值 最大值 单位 条件 温度范围 工作温度范围 TA –40 — +150 °C 储存温度范围 TA –55 — +150 °C 封装热阻 SOIC-14 的热阻 JA — +149.5 — °C/W DFN-14的热阻 JA — +64.1 — °C/W

 2020 Microchip Technology Inc. DS20006027A_CN 第79 页

# MCP2518FD

注：

DS20006027A_CN 第 80页  2020 Microchip Technology Inc.

# MCP2518FD

### 8.0 典型性能曲线

注： 以下图表为基于有限数量样片的统计结果，仅供参考。所列出的性能特性未经测试，我们不做保证。一些图 表中列出的数据可能超出规定的工作范围（例如，超出了规定的电源范围），因此不在担保范围内。

VDD=3.3V VDD=5.5V VDD=3.3V VDD=5.5V

A]5 PA]250[P [ 4

DDS I3 DDLPM 150I

-40 -20 0 20 40 60 80 100 120 140 160-40 -20 0 20 40 60 80 100 120 140 160 Temperature [°C]Temperature [°C]

图 8-1： 平均 IDDS ——温度曲线图 8-2： 平均 IDDLPM ——温度曲线

 2020 Microchip Technology Inc. DS20006027A_CN 第81 页

# MCP2518FD

注：

DS20006027A_CN 第 82页  2020 Microchip Technology Inc.

# MCP2518FD

### 9.0 封装信息

9.1 封装标识信息

14引脚SOIC示例：

MCP2518FD

### SLe3

14 引脚 VDFN示例：

2518FD QBBe3

图注： XX...X 客户指定信息 Y 年份代码（日历年的最后一位数字） YY 年份代码（日历年的最后两位数字） WW 星期代码（一月一日的星期代码为“01”） NNN 以字母数字组成的追踪代码 ® e3雾锡（Matte Tin，Sn）的JEDEC无铅标志
* 表示无铅封装。JEDEC 无铅标志（ e3）标示于此种封装的外包装 上。

注： Microchip部件编号如果无法在同一行内完整标注，将换行标出，因此会限制表示客户指定信息的 字符数。

 2020 Microchip Technology Inc. DS20006027A_CN 第83 页

# MCP2518FD

### 14 引脚塑封窄条小外形封装（SL）——主体3.90 mm [SOIC]

14-Lead Plastic Small Outline (SL) - Narrow, 3.90 mm Body [SOIC] ⌘˖ ᴰᯠሱ㻵മ䈧㠣http://www.microchip.com/packagingḕⴻMicrochipሱ㻵㿴㤳Ǆ Note:For the most current package drawings, please see the Microchip Packaging Specification located at http://www.microchip.com/packaging

2X 0.10 C A–B D ANOTE 5 D N

E E2

E1E

2X 0.10 C D 2X N/2 TIPS NOTE 1 1 230.20 C eNX b NOTE 50.25 C A–B D B TOP VIEW

0.10 C

CAA2 SEATING PLANE 14X A1SIDE VIEW0.10C

h h

HR0.13 R0.13

c

SEE VIEW C L VIEW A–A(L1)

VIEW C

Microchip Technology Drawing No. C04-065-SL Rev D Sheet 1 of 2

DS20006027A_CN 第 84页  2020 Microchip Technology Inc.

# MCP2518FD

### 1414-Lead Plastic Small Outline (SL) - Narrow, 3.90 mm Body [SOIC]引脚塑封窄条小外形封装（SL）——主体3.90 mm [SOIC]

⌘˖ ᴰᯠሱ㻵മ䈧㠣http://www.microchip.com/packagingḕⴻMicrochipሱ㻵㿴㤳Ǆ Note:For the most current package drawings, please see the Microchip Packaging Specification located at http://www.microchip.com/packaging

UnitsMILLIMETERS Dimension LimitsMINNOMMAX Number of PinsN14 Pitche1.27 BSC Overall HeightA--1.75 Molded Package ThicknessA21.25-- Standoff§A10.10-0.25 Overall WidthE6.00 BSC Molded Package WidthE13.90 BSC Overall LengthD8.65 BSC Chamfer (Optional)h0.25-0.50 Foot Length L 0.40 - 1.27 FootprintL11.04 REF Lead Angle 0° - - Foot Angle 0° - 8° Lead Thicknessc0.10-0.25 Lead Widthb0.31-0.51 Mold Draft Angle Top5°-15° Mold Draft Angle Bottom5°-15°

Notes: 1.Pin 1 visual index feature may vary, but must be located within the hatched area. 2.§ Significant Characteristic 3.Dimension D does not include mold flash, protrusions or gate burrs, which shall not exceed 0.15 mm per end. Dimension E1 does not include interlead flash or protrusion, which shall not exceed 0.25 mm per side. 4.Dimensioning and tolerancing per ASME Y14.5M BSC: Basic Dimension. Theoretically exact value shown without tolerances. REF: Reference Dimension, usually without tolerance, for information purposes only.
5. Datums A & B to be determined at Datum H.

Microchip Technology Drawing No. C04-065-SL Rev D Sheet 2 of 2

 2020 Microchip Technology Inc. DS20006027A_CN 第85 页

# MCP2518FD

### 1414-Lead Plastic Small Outline (SL) - Narrow, 3.90 mm Body [SOIC]引脚塑封窄条小外形封装（SL）——主体3.90 mm [SOIC]

⌘˖ ᴰᯠሱ㻵മ䈧㠣http://www.microchip.com/packagingḕⴻMicrochipሱ㻵㿴㤳Ǆ Note:For the most current package drawings, please see the Microchip Packaging Specification located at http://www.microchip.com/packaging

SILK SCREEN

C

Y

1 2 X E

RECOMMENDED LAND PATTERN

UnitsMILLIMETERS Dimension LimitsMINNOMMAX Contact PitchE1.27 BSC Contact Pad Spacing C5.40 Contact Pad Width (X14)X0.60 Contact Pad Length (X14)Y1.55

Notes: 1.Dimensioning and tolerancing per ASME Y14.5M BSC: Basic Dimension. Theoretically exact value shown without tolerances.

Microchip Technology Drawing No. C04-2065-SL Rev D

DS20006027A_CN 第 86页  2020 Microchip Technology Inc.

# MCP2518FD

### 1414-Lead Very Thin Plastic Dual Flat, No Lead Package (QBB) - 4.5x3 mm Body [VDFN]引脚塑封超薄双列扁平无引线封装（QBB）——主体4.5x3 mm [VDFN]

### 带With 1.6x4.2 mm Exposed Pad and Stepped Wettable Flanks1.6x4.2 mm外露焊盘和梯形可润湿侧翼

Note:⌘˖For the most current package drawings, please see the Microchip Packaging Specification located atᴰᯠሱ㻵മ䈧㠣http://www.microchip.com/packagingḕⴻMicrochipሱ㻵㿴㤳Ǆ http://www.microchip.com/packaging

DA B N

(DATUM A) (DATUM B) E

NOTE 1

2X 0.10 C 1 2 2X 0.10 CTOP VIEW

0.10 C

CA A1 SEATING PLANE14X 0.08 C SIDE VIEW (A3)

0.10 C A B D2 A 1 2 NOTE 1

A0.10 C A B

E2

K N L 14X b 0.10 C A B e 0.05 C BOTTOM VIEW

Microchip Technology Drawing C04-21361 Rev B Sheet 1 of 2

 2020 Microchip Technology Inc. DS20006027A_CN 第87 页

# MCP2518FD

### 1414-Lead Very Thin Plastic Dual Flat, No Lead Package (QBB) - 4.5x3 mm Body [VDFN]引脚塑封超薄双列扁平无引线封装（QBB）——主体4.5x3 mm [VDFN]

### 带With 1.6x4.2 mm Exposed Pad and Stepped Wettable Flanks1.6x4.2 mm 外露焊盘和梯形可润湿侧翼

Note:For the most current package drawings, please see the Microchip Packaging Specification located at ⌘˖ ᴰᯠሱ㻵മ䈧㠣http://www.microchip.com/packagingḕⴻMicrochipሱ㻵㿴㤳Ǆ http://www.microchip.com/packaging

A4

E3PARTIALLY PLATED SECTION A–A

UnitsMILLIMETERS Dimension LimitsMIN NOMMAX Number of TerminalsN14 Pitche0.65 BSC Overall HeightA0.800.850.90 StandoffA10.000.030.05 Terminal ThicknessA30.203 REF Overall LengthD4.50 BSC Exposed Pad LengthD2 4.154.20 4.25 Overall WidthE3.00 BSC Exposed Pad WidthE21.501.601.70 Terminal Widthb0.270.320.37 Terminal LengthL0.350.400.45 Terminal-to-Exposed-PadK 0.20 -- Wettable Flank Step Cut Depth A4 0.10 0.13 0.15 Wettable Flank Step Cut WidthE3 - -0.04 Notes: 1.Pin 1 visual index feature may vary, but must be located within the hatched area. 2.Package is saw singulated 3.Dimensioning and tolerancing per ASME Y14.5M BSC: Basic Dimension. Theoretically exact value shown without tolerances. REF: Reference Dimension, usually without tolerance, for information purposes only.

Microchip Technology Drawing C04-21361 Rev B Sheet 2 of 2

DS20006027A_CN 第 88页  2020 Microchip Technology Inc.

# MCP2518FD

### 1414-Lead Very Thin Plastic Dual Flat, No Lead Package (QBB) - 4.5x3 mm Body [VDFN]引脚塑封超薄双列扁平无引线封装（QBB）——主体4.5x3 mm [VDFN]

### 带With 1.6x4.2 mm Exposed Pad and Stepped Wettable Flanks1.6x4.2 mm外露焊盘和梯形可润湿侧翼

Note:For the most current package drawings, please see the Microchip Packaging Specification located at ⌘˖ ᴰᯠሱ㻵മ䈧㠣http://www.microchip.com/packagingḕⴻMicrochipሱ㻵㿴㤳Ǆ http://www.microchip.com/packaging

Y2 EV

ØV

CX2 CHEVG1

Y1

1 2 SILK SCREENX1 G2 E

RECOMMENDED LAND PATTERN

UnitsMILLIMETERS Dimension LimitsMINNOMMAX Contact PitchE0.65 BSC Optional Center Pad WidthX21.70 Optional Center Pad LengthY24.25 Contact Pad Spacing C3.00 Contact Pad Width (X14)X10.35 Contact Pad Length (X14)Y10.80 Pin 1 Index Chamfer CH0.30 Contact Pad to Center Pad (X14) G1 0.20 Contact Pad to Center Pad (X12) G2 0.20 Thermal Via Diameter V0.30 Thermal Via Pitch EV1.00

Notes: 1.Dimensioning and tolerancing per ASME Y14.5M BSC: Basic Dimension. Theoretically exact value shown without tolerances. 2.For best soldering results, thermal vias, if used, should be filled or tented to avoid solder loss during reflow process

Microchip Technology Drawing C04-23361 Rev B

 2020 Microchip Technology Inc. DS20006027A_CN 第89 页

# MCP2518FD

注：

DS20006027A_CN 第 90页  2020 Microchip Technology Inc.

# MCP2518FD

### 附录A： 版本历史

版本 A（2019年 4月）

- 本文档的初始版本

 2020 Microchip Technology Inc. DS20006027A_CN 第91 页

# MCP2518FD

### 附录B： CAN FD合规性

MCP2518FD 通过了ISO 16845-1:2016中指定的CAN FD合规性测试。 ISO 11898-1:2015列出了非强制特性。表B-1阐明了已实现哪些可选特性。

表B-1： ISO 可选特性 编号 可选特性 已实现 1 FD帧格式是 2 禁止帧格式 是。经典CAN 帧格式。 3 有限LLC帧否。实现了完整的ID和DLC。 4 不发送包括填充字节的帧 N/A。请参见编号3。 5 LLC中止接口是 6 ESI和BRS位值 是 7 提供MAC数据一致性的方法是 8 时间和时间触发 帧起始输出。 9 时间戳是。32位TBC。 10 总线监视模式 是 11 句柄是 12 受限工作 是 13 标称位和数据位使用单独的预分频器是 14 禁止自动重发 是 15 最大重发次数是。1、3或无限制。 16 检测到保留位为隐性时，禁止协议异常事件 是。可选。 17 PCS_Status 否 18 总线集成状态期间的边沿滤波 是。可选。 19 SSP放置的时间分辨率是。128 T。测量、手动或禁止。 Q 20 FD_T/R 报文 TX和RX中断。

DS20006027A_CN 第 92页  2020 Microchip Technology Inc.

# MCP2518FD

### 产品标识体系

欲订货或获取价格、交货等信息，请与我公司生产厂或各销售办事处联系 。

(1) 部件编号 X -X /XX 示例： 器件卷带式选项温度范围封装a) MCP2518FDT-E/SL = 卷带式，扩展级温度， 塑封 SOIC（主体 150 mil），14 引脚 b) MCP2518FDT-H/SL = 卷带式，高温， 塑封 SOIC（主体 150 mil），14 引脚 器件： MCP2518FD：CAN FD 控制器 c) MCP2518FDT- E/QBB = 卷带式，扩展级温度， 塑封 VDFN（主体 4.5 x 3 mm）， (1)14引脚，带 1.6 x 4.2 mm外露焊盘 卷带式选项： T = 卷带式 和梯形可润湿侧翼 d) MCP2518FDT-H/QBB = 卷带式，高温， 温度范围： E = -40C 至 +125C（扩展级） 塑封 VDFN（主体 4.5 x 3 mm）， H = -40C 至 +150C（高温） 14 引脚，带 1.6 x 4.2 mm 外露焊盘 和梯形可润湿侧翼 封装： SL = 塑封 SOIC（主体 150 mil），14引脚注 1： 卷带式标识符仅出现在产品目录的部件编号描述中。该标识 QBB = 塑封 VDFN（主体 4.5 x 3 mm），符用于订货目的，不会印刷在器件封装上。关于包装是否提 14引脚，带 1.6 x 4.2 mm外露焊盘和供卷带式选项的信息，请咨询当地的 Microchip 销售办事处。 梯形可润湿侧翼

 2020 Microchip Technology Inc. DS20006027A_CN 第93 页

# MCP2518FD

注：

DS20006027A_CN 第 94页  2020 Microchip Technology Inc.

请注意以下有关 Microchip 器件代码保护功能的要点：
- Microchip 的产品均达到 Microchip 数据手册中所述的技术规范。

- Microchip 确信：在正常使用的情况下， Microchip 系列产品非常安全。

- 目前，仍存在着用恶意、甚至是非法的方法来试图破坏代码保护功能的行为。我们确信，所有这些行为都不是以 Microchip 数据 手册中规定的操作规范来使用 Microchip 产品的。这种试图破坏代码保护功能的行为极可能侵犯 Microchip 的知识产权。

- Microchip 愿与那些注重代码完整性的客户合作。

- Microchip 或任何其他半导体厂商均无法保证其代码的安全性。代码保护并不意味着我们保证产品是 “牢不可破”的。代码保护 功能处于持续发展中。Microchip 承诺将不断改进产品的代码保护功能。任何试图破坏 Microchip 代码保护功能的行为均可视为违 反了 《数字器件千年版权法案 （Digital Millennium Copyright Act）》。如果这种行为导致他人在未经授权的情况下，能访问您的 软件或其他受版权保护的成果，您有权依据该法案提起诉讼，从而制止这种行为。

提供本文档的中文版本仅为了便于理解。请勿忽视文档中包含商标 的英文部分，因为其中提供了有关 Microchip 产品性能和使用Microchip的名称和徽标组合、Microchip徽标、Adaptec、 情况的有用信息。Microchip Technology Inc. 及其分公司和相AnyRate、AVR、AVR 徽标、AVR Freaks、BesTime、BitCloud、 chipKIT、 chipKIT 徽标、 CryptoMemory、 CryptoRF、 dsPIC、 关公司、各级主管与员工及事务代理机构对译文中可能存在的 FlashFlex、 flexPWR、 HELDO、 IGLOO、 JukeBlox、 KeeLoq、 任何差错不承担任何责任。建议参考 Microchip Technology Kleer、 LANCheck、 LinkMD、 maXStylus、 maXTouch、 Inc. 的英文原版文档。MediaLB、 megaAVR、 Microsemi、 Microsemi 徽标、 MOST、 MOST 徽标、 MPLAB、 OptoLyzer、 PackeTime、 PIC、 本出版物中提供的信息仅仅是为方便您使用 Microchip 产品或picoPower、 PICSTART、 PIC32 徽标、 PolarFire、 Prochip Designer、 QTouch、 SAM-BA、 SenGenuity、 SpyNIC、 SST、 使用这些产品来进行设计。本出版物中所述的器件应用信息及 SST 徽标、 SuperFlash、 Symmetricom、 SyncServer、 其他类似内容仅为您提供便利，它们可能由更新之信息所替Tachyon、 TimeSource、 tinyAVR、 UNI/O、 Vectron 及 XMEGA 代。确保应用符合技术规范，是您自身应负的责任。均为 Microchip Technology Incorporated 在美国和其他国家或地 区的注册商标。 Microchip “按原样”提供这些信息。 Microchip 对这些信息AgileSwitch、APT、ClockWorks、TheEmbeddedControl Solutions Company、 EtherSynch、 FlashTec、 Hyper Speed 不作任何明示或暗示、书面或口头、法定或其他形式的声明或 Control、 HyperLight Load、 IntelliMOS、 Libero、 motorBench、 担保，包括但不限于针对非侵权性、适销性和特定用途的适用mTouch、 Powermite 3、 Precision Edge、 ProASIC、 ProASIC 性的暗示担保，或针对其使用情况、质量或性能的担保。Plus、 ProASIC Plus 徽标、 Quiet-Wire、 SmartFusion、 SyncWorld、 Temux、 TimeCesium、 TimeHub、 TimePictra、 TimeProvider、 WinPath 和 ZL 均 为 Microchip Technology 在任何情况下，对于因这些信息或使用这些信息而产生的任 Incorporated 在美国的注册商标。 何间接的、特殊的、惩罚性的、偶然的或间接的损失、损害或 Adjacent Key Suppression、 AKS、 Analog-for-the-Digital Age、 任 何 类 型 的 开 销， Microchip 概 不 承 担 任 何 责 任，即 使Any Capacitor、 AnyIn、 AnyOut、 Augmented Switching、 Microchip 已被告知可能发生损害或损害可以预见。在法律BlueSky、 BodyCom、 CodeGuard、 CryptoAuthentication、 CryptoAutomotive、 CryptoCompanion、 CryptoController、 允许的最大范围内，对于因这些信息或使用这些信息而产生 dsPICDEM、 dsPICDEM.net、 Dynamic Average Matching、 的所有索赔， Microchip 在任何情况下所承担的全部责任均DAM、ECAN、Espresso T1S、EtherGREEN、IdealBridge、In- 不超出您为获得这些信息向 Microchip 直接支付的金额 （如Circuit Serial Programming、 ICSP、 INICnet、 Intelligent Paralleling、Inter-Chip Connectivity、JitterBlocker、maxCrypto、 有）。如果将 Microchip 器件用于生命维持和 / 或生命安全应 maxView、memBrain、Mindi、MiWi、MPASM、MPF、MPLAB 用，一切风险由买方自负。买方同意在由此引发任何一切损 Certified 徽标、 MPLIB、 MPLINK、 MultiTRAK、 NetDetach、 害、索赔、诉讼或费用时，会维护和保障 Microchip 免于承担Omniscient Code Generation、PICDEM、 PICDEM.net、PICkit、 法律责任。除非另外声明，在 Microchip 知识产权保护下，不PICtail、 PowerSmart、 PureSilicon、 QMatrix、 REAL ICE、 Ripple Blocker、 RTAX、 RTG4、 SAM-ICE、 Serial Quad I/O、 得暗中或以其他方式转让任何许可证。 simpleMAP、SimpliPHY、SmartBuffer、SMART-I.S.、storClad、 SQI、 SuperSwitcher、 SuperSwitcher II、 Switchtec、 SynchroPHY、 Total Endurance、 TSHARC、 USBCheck、 VariSense、 VectorBlox、 VeriPHY、 ViewSpan、 WiperLock、 XpressConnect 和 ZENA 均为 Microchip Technology Incorporated 在美国和其他国家或地区的商标。 SQTP 为 Microchip Technology Incorporated 在美国的服务标记。 Adaptec 徽 标、 Frequency on Demand、 Silicon Storage Technology 和 Symmcom 均为 Microchip Technology Inc. 在除美 国外的国家或地区的注册商标。 GestIC 为 Microchip Technology Inc. 的子 公司 Microchip Technology Germany II GmbH & Co. KG 在除美国外的国家或地区 的注册商标。 在此提及的所有其他商标均为各持有公司所有。 有关 Microchip质量管理体系的更多信息，请访问 © 2020, Microchip Technology Incorporated 版权所有。 www.microchip.com/quality。 ISBN：978-1-5224-7047-2

 2020 Microchip Technology Inc. DS20006027A_CN 第95 页

02/28/20

# 全球销售及服务网点

美洲亚太地区亚太地区欧洲 公司总部 Corporate Office中国 - 北京澳大利亚 Australia - Sydney奥地利 Austria - Wels 2355 West Chandler Blvd.Tel: 86-10-8569-7000Tel: 61-2-9868-6733Tel: 43-7242-2244-39 Chandler, AZ 85224-6199Fax: 43-7242-2244-393 中国 - 成都印度 India - Bangalore Tel: 1-480-792-7200Tel: 86-28-8665-5511Tel: 91-80-3090-4444丹麦 Fax: 1-480-792-7277Denmark - Copenhagen 中国 - 重庆印度 India - New Delhi 技术支持：Tel: 45-4485-5910 Tel: 86-23-8980-9588Tel: 91-11-4160-8631 http://www.microchip.com/Fax: 45-4485-2829 support中国-东莞印度India - Pune芬兰 Finland - Espoo Tel: 86-769-8702-9880Tel: 91-20-4121-0141 网址：www.microchip.comTel: 358-9-4520-820 中国 - 广州日本 Japan - Osaka 法国 France - Paris 亚特兰大 Atlanta Tel: 86-20-8755-8029Tel: 81-6-6152-7160Tel: 33-1-69-53-63-20 Duluth, GA Fax: 33-1-69-30-90-79 Tel: 1-678-957-9614中国 - 杭州日本 Japan - Tokyo Fax: 1-678-957-1455Tel: 86-571-8792-8115Tel: 81-3-6880-3770德国Germany - Garching Tel: 49-8931-9700 奥斯汀 Austin, TX中国 - 南京韩国 Korea - Daegu 德国 Germany - Haan Tel: 1-512-257-3370Tel: 86-25-8473-2460Tel: 82-53-744-4301 Tel: 49-2129-3766400 波士顿 Boston中国-青岛韩国 Korea - Seoul 德国Germany - Heilbronn Westborough, MATel: 86-532-8502-7355Tel: 82-2-554-7200 Tel: 49-7131-72400 Tel: 1-774-760-0087 中国 - 上海马来西亚德国 Germany - Karlsruhe Fax: 1-774-760-0088 Tel: 86-21-3326-8000Malaysia - Kuala LumpurTel: 49-721-625370 芝加哥 ChicagoTel: 60-3-7651-7906 中国 - 沈阳德国 Germany - Munich Itasca, IL Tel: 86-24-2334-2829马来西亚Malaysia - PenangTel: 49-89-627-144-0 Tel: 1-630-285-0071 Fax: 49-89-627-144-44 Tel: 60-4-227-8870 Fax: 1-630-285-0075中国-深圳 德国 Germany - Rosenheim Tel: 86-755-8864-2200菲律宾 Philippines - Manila 达拉斯 DallasTel: 49-8031-354-560 Addison, TX中国 - 苏州Tel: 63-2-634-9065 以色列 Israel - Ra’anana Tel: 1-972-818-7423Tel: 86-186-6233-1526新加坡Singapore Tel: 972-9-744-7705 Fax: 1-972-818-2924中国-武汉Tel: 65-6334-8870 Tel: 86-27-5980-5300意大利Italy - Milan 底特律 Detroit泰国 Thailand - BangkokTel: 39-0331-742611 Novi, MI中国-西安Tel: 66-2-694-1351Fax: 39-0331-466781 Tel: 1-248-848-4000Tel: 86-29-8833-7252 越南 Vietnam - Ho Chi Minh意大利 Italy - Padova 中国 - 厦门 休斯敦 Houston, TXTel: 84-28-5448-2100Tel: 39-049-7625286 Tel: 1-281-894-5983Tel: 86-592-238-8138 荷兰 Netherlands - Drunen 中国 - 香港特别行政区 印第安纳波利斯Tel: 31-416-690399 IndianapolisTel: 852-2943-5100Fax: 31-416-690340 Noblesville, IN挪威Norway - Trondheim 中国 - 珠海 Tel: 1-317-773-8323Tel: 86-756-321-0040Tel: 47-7288-4388 Fax: 1-317-773-5453 台湾地区 - 高雄波兰 Poland - Warsaw Tel: 1-317-536-2380 Tel: 886-7-213-7830Tel: 48-22-3325737 洛杉矶 Los Angeles 台湾地区 - 台北罗马尼亚 Mission Viejo, CA Tel: 886-2-2508-8600Romania - Bucharest Tel: 1-949-462-9523 台湾地区 - 新竹Tel: 40-21-407-87-50 Fax: 1-949-462-9608 Tel: 886-3-577-8366 Tel: 1-951-273-7800西班牙 Spain - Madrid Tel: 34-91-708-08-90 罗利 Raleigh, NC Fax: 34-91-708-08-91 Tel: 1-919-844-7510 瑞典 Sweden - Gothenberg 纽约 New York, NYTel: 46-31-704-60-40 Tel: 1-631-435-6000 瑞典 Sweden - Stockholm 圣何塞 San Jose, CATel: 46-8-5090-4654 Tel: 1-408-735-9110 Tel: 1-408-436-4270英国UK - Wokingham Tel: 44-118-921-5800 加拿大多伦多 TorontoFax: 44-118-921-5820 Tel: 1-905-695-1980 Fax: 1-905-695-2078

DS20006027A_CN 第 96页  2020 Microchip Technology Inc.