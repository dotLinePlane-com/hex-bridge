---
name: can-debug
description: 调试 HEX-Bridge CAN（MCP2518FD）通信与寄存器配置。项目级覆盖全局 can-debug，当疑似寄存器设置问题时，除核实 files/can-files/MCP2518FD数据手册.md 外，还要参考 Microchip 官方源码 MCP251xFDcanfdspiAPIforSAMV71_v1_1 对照校验寄存器地址、位域定义与配置流程。
---

# HEX-Bridge CAN 调试（项目级 can-debug）

## 适用场景

- CAN 收/发异常、无法收到报文、发不出去、总线报错（Bus Off / Passive）。
- 疑似寄存器设置问题：位时序、工作模式、FIFO 配置、过滤器/掩码、中断使能等配置值与预期不符。
- 需要确认某寄存器地址、位域偏移、位宽或复位值是否写对。

## 双参考源（寄存器问题必查）

当疑似寄存器设置问题时，**两份资料交叉对照**，不能只看其中一份：

| 参考源 | 路径 | 用途 |
|:---|:---|:---|
| 数据手册（中文） | `files/can-files/MCP2518FD数据手册.md` | 寄存器位域语义、复位值、时序要求（表3-1/3-2 寄存器映射，寄存器3-1~3-6） |
| Microchip 官方源码 | `D:\project\esp-idf-v6.0.1-project\hex-bridge\MCP251xFDcanfdspiAPIforSAMV71_v1_1` | 官方驱动实际的寄存器地址宏、位域结构体、配置/读写 API 实现，是"权威实现"参照 |

### 官方源码关键文件

```
MCP251xFDcanfdspiAPIforSAMV71_v1_1/
└── V71_CANFDSPI/V71_CANFDSPI/
    ├── driver/canfdspi/drv_canfdspi_defines.h   # 枚举、CAN_CONFIG/CAN_FIFO_CONFIG/CAN_MSGOBJ_ID 等配置结构体
    ├── driver/canfdspi/drv_canfdspi_register.h  # 寄存器地址宏 cREGADDR_*、位域结构体 REG_CiCON/CiNBTCFG/...、复位值表
    ├── driver/canfdspi/drv_canfdspi_api.h       # 官方 API 声明（Configure/BitTimeConfigure/FilterMaskConfigure/...）
    ├── driver/canfdspi/drv_canfdspi_api.c       # 官方 API 实现（寄存器读写序列的权威参照）
    ├── driver/spi/drv_spi.c / drv_spi.h         # 底层 SPI 收发实现（可对照本项目 spi_transfer）
    └── src/app.c / main.c                       # 官方配置流程示例（初始化→配置→收发）
```

## 本项目驱动与官方源码对应关系

本项目移植自官方驱动，寄存器地址与位域一致，可互相查证：

| 本项目 | 官方源码 | 说明 |
|:---|:---|:---|
| `main/modules/mcp2518fd.h/.c` | `driver/canfdspi/drv_canfdspi_api.c/.h` | 底层 SPI 驱动 + 寄存器访问 |
| `MCP2518FD_REG_CiCON` (0x000) | `cREGADDR_CiCON` | CAN 控制寄存器（OPMOD/REQOP 等） |
| `MCP2518FD_REG_CiNBTCFG` (0x004) | `cREGADDR_CiNBTCFG` | 仲裁段位时序 |
| `MCP2518FD_REG_CiDBTCFG` (0x008) | `cREGADDR_CiDBTCFG` | FD 数据段位时序 |
| `MCP2518FD_REG_CiTDC` (0x00C) | `cREGADDR_CiTDC` | 发送延迟补偿 |
| `MCP2518FD_REG_CiINT` (0x01C) | `cREGADDR_CiINT` | 中断标志/使能 |
| `MCP2518FD_REG_CiTREC` (0x034) | `cREGADDR_CiTREC` | TEC/REC 错误计数 + 状态位 |
| `MCP2518FD_REG_CiBDIAG0/1` (0x038/0x03C) | `cREGADDR_CiBDIAG0/1` | 总线诊断错误计数 |
| `MCP2518FD_REG_CiTXQCON` (0x050) | `cREGADDR_CiTXQCON` | 发送队列配置 |
| `MCP2518FD_REG_OSC` (0xE00) | `cREGADDR_OSC` | 振荡器/PLL 配置 |
| `MCP2518FD_REG_IOCON` (0xE04) | `cREGADDR_IOCON` | 引脚/收发器待机控制 |
| `MCP2518FD_REG_DEVID` (0xE14) | `cREGADDR_DEVID` | 器件 ID（读 0x08=2518FD） |

## 执行步骤

1. **确认器件可用**：读取 DEVID（期望 `0x08`），读 OSC 确认 PLLRDY/OSCRDY，确认 SPI 通路正常。
2. **定位疑似寄存器**：根据现象确定涉及寄存器（如收不到→过滤器/FLTCON；发不出→TXQCON/TXREQ；报错→NBTCFG/DBTCFG/TDC；总线状态→TREC/BDIAG）。
3. **双源查证**：
   - 在数据手册中查该寄存器位域含义与复位值（`files/can-files/MCP2518FD数据手册.md` 第3章）。
   - 在官方源码 `drv_canfdspi_register.h` 中查地址宏、`REG_*` 位域结构体、`canControlResetValues`/`canFifoResetValues` 复位值表，确认地址与位宽无误。
   - 在 `drv_canfdspi_api.c` 中对照官方 API 的读写序列，确认本项目 `mcp2518fd.c` 的配置写入方式一致（如进入 Config 模式后才能改位时序、改完回 Normal）。
4. **检查本项目配置代码**：核对 `main/modules/mod_can.c` / `mcp2518fd.c` 中写入的值与查证结果一致。
5. **读回寄存器验证**：通过 `mcp2518fd_read_byte/read_word` 读回实际写入值，确认未被芯片拒绝或覆盖。

## 常用寄存器诊断点

| 现象 | 检查项 |
|:---|:---|
| 无法进配置模式 | `OPMOD`（CiCON byte2）是否等于 0x04；REQOP 与 OPMOD 一致 |
| 波特率不符 | `CiNBTCFG` BRP/TSEG1/TSEG2/SJW 是否与官方 `DRV_CANFDSPI_BitTimeConfigureNominal40MHz` 结果一致（20MHz 晶振 ×2 PLL） |
| 收不到报文 | `CiFLTCON` 过滤器使能/绑定、`CiFLTOBJ`/`CiMASK` 值、FIFO `PLSIZE` 是否够装报文 |
| 发不出去 | `CiTXQCON` TXEN、`CiTXREQ` 是否置位、`CiTXIF` 状态；官方 `DRV_CANFDSPI_TransmitQueueLoad` 流程 |
| 总线错误/掉线 | `CiTREC` TEC/REC 与 TXBO/TXBP 位、`CiBDIAG0/1` 错误类型（NACK/位错误/格式错误） |
| 中断不触发 | `CiINT` 高 16 位 IExxx 使能位是否置位；GPIO39 外部中断配置 |

## 失败分流

- `DEVID 读不到或不对`：SPI 时序/引脚/CS 问题，非寄存器问题 → 检查 `hex_config.h` 引脚与 SPI Mode 0、10MHz。
- `寄存器读回与写入值不符`：芯片未进入可写状态（Config 模式）或地址写错 → 双源核对地址宏。
- `配置按手册正确但仍异常`：以官方源码 `drv_canfdspi_api.c` 的实现流程为准重新走一遍（模式切换顺序、UINC 递增、等待状态位）。

## 交接关系

- 从 `build-idf` 编译、`flash-idf` 烧录后，用本 skill 排查 CAN 问题。
- 总线级联调（PCAN 收监、回环测试）：`python script/test/test_can.py --phase 1 --baud 500k`（Phase 1）与 `--phase 2`（MCP UBCP）。
- 与 `serial-monitor` 配合：COM4 观察 UBCP CAN 命令应答，COM5 看固件日志。
