# HEX-Bridge 项目文件索引

> 本文档为 AI Agent 和开发者提供项目结构的快速索引。

---

## 项目概述

HEX-Bridge 是一款基于 ESP32 的多功能硬件接口扩展设备，通过 UBCP (Unified Binary Communication Protocol) v2.0 协议与上位机 (MCP Server) 通信，支持 CAN FD、SPI、I2C、UART、以太网 (TCP/UDP/WebSocket)、GPIO 等接口的统一管理。

---

## 目录结构

```
hex-bridge/
├── AGENTS.md                       # ← 本文件（项目索引）
├── files/                          # 项目文档
│   ├── design/
│   │   ├── protocol/               # UBCP v2.0 协议规范
│   │   ├── firmware/               # 固件架构设计
│   │   ├── test/                   # 测试用例
│   │   └── test-report/            # 测试报告
│   │       └── UART-Test-Report.md # UART 模块测试报告 (57 用例)
│   │
│   └── sch/                        # 原理图相关
│       └── esp32-pinout-design.md  # ESP32 引脚分配方案
│
├── main/                           # 固件源代码
│   ├── CMakeLists.txt              # 构建配置
│   ├── main.c                      # 入口 app_main()
│   ├── hex_config.h                # 全局硬件配置宏
│   │
│   ├── protocol/                   # 协议层
│   │   ├── ubcp_def.h              # 协议常量、命令码、错误码
│   │   ├── ubcp_crc16.h            # CRC-16/CCITT-FALSE 计算
│   │   ├── ubcp_frame.h            # 帧结构体与 API 声明
│   │   └── ubcp_frame.c            # 帧解析/构建/转义实现
│   │
│   ├── core/                       # 核心框架
│   │   ├── module_base.h           # 模块接口定义
│   │   ├── seq_num.h               # 事件序列号管理
│   │   ├── msg_bus.h               # 消息总线接口
│   │   └── msg_bus.c               # 消息总线实现
│   │
│   ├── transport/                  # MCP 传输层
│   │   ├── mcp_transport.h         # 传输层接口
│   │   └── mcp_transport.c         # UART1 收发与帧解析
│   │
│   ├── modules/                    # 功能模块
│   │   ├── mod_system.h/.c         # 系统管理 (0x00-0x0F)
│   │   └── mod_uart.h/.c          # UART 扩展 (0xA0-0xAF) (57 测试用例全部通过)
│   │
│   └── utils/                      # 工具
│       └── hex_log.h               # 日志宏封装
│
├── CMakeLists.txt                  # 项目根 CMake
├── sdkconfig                       # ESP-IDF 配置
└── script/                         # 辅助脚本
    ├── cli/                        # CLI 工具
    │   ├── hex-bridge-uart-cli.py  # UART 扩展口 CLI (Python, 推荐)
    │   ├── hex-bridge-uart-cli.js  # UART 扩展口 CLI (Node.js)
    │   ├── package.json            # Node.js 依赖 (serialport)
    │   └── node_modules/
    ├── test/                       # 测试脚本
    │   ├── ubcp_client.py          # UBCP v2.0 Python 客户端库
    │   ├── mcp_transport.py        # COM35 串口传输封装
    │   ├── test_uart.py            # UART 模块 57 项测试
    │   └── ...
    ├── init-idf-menuconfig.bat
    └── push-to-github.ps1
```

---

## 串口分配

| 串口 | 用途 | 参数 |
|:---|:---|:---|
| COM35 | MCP 通信 (UART1) | 921600 bps, 8N1 |
| COM24 | 扩展口 (UART2) | 默认 115200 bps, 8N1 |
| COM34 | 调试输出 (UART0) | 115200 bps, 8N1 |

---

## 硬件引脚速查

| 外设 | TX / SCK | RX / MISO | 其他 |
|:---|:---|:---|:---|
| UART0 (调试) | GPIO 1 | GPIO 3 | — |  
| UART1 (MCP 通信) | GPIO 4 | GPIO 34 (GPI) | 外接 10kΩ 上拉 | 
| UART2 (扩展口) | GPIO 32 | GPIO 35 (GPI) | 外接 10kΩ 上拉 (RX) | 
| CAN FD (MCP2518FD) | GPIO 14 (SCK) | GPIO 36 (MISO) | CS=GPIO15, INT=GPIO39 |
| I2C (EEPROM) | GPIO 12 (SCL) | GPIO 33 (SDA) | SCL=GPIO12(MTDI), 4.7kΩ上拉保复位高电平 |
| 以太网 (LAN8720) | 固定 RMII 引脚 | — | PHY_RST=GPIO5 |

---

## 开发快速入门

以下操作建议通过 Kilo Skills 执行，更可靠且自动处理环境依赖：

| 操作 | 命令 | 推荐 Skill |
|:---|:---|:---|
| 编译 | `idf.py build` | `build-idf` |
| 烧录 | `idf.py -p COMx flash` | `flash-idf` |
| 串口监视 | `idf.py -p COMx monitor` | `serial-monitor` |
| 编译+烧录+监视 (流水线) | — | `workflow` |
| 内存分析 (.map/ELF) | — | `memory-analysis` |
| 静态代码检查 | — | `static-analysis` |


## 模块实现进度

| 模块 | 命令码范围 | 状态 |
|:---|:---|:---|
| 系统管理 | 0x00-0x0F | ✅ 基础实现 (PING, GET_INFO) |
| UART 扩展 | 0xA0-0xAF | ✅ 完整实现 |
| CAN FD | 0x10-0x1F | ⬜ 待实现 |
| SPI | 0x20-0x2F | ⬜ 待实现 |
| I2C | 0x30-0x3F | ⬜ 待实现 |
| 网络配置 | 0x40-0x4F | ⬜ 待实现 |
| TCP | 0x50-0x5F | ⬜ 待实现 |
| UDP | 0x60-0x6F | ⬜ 待实现 |
| WebSocket | 0x70-0x7F | ⬜ 待实现 |
| GPIO | 0x80-0x8F | ⬜ 待实现 |
| 批量传输 | 0x90-0x9F | ⬜ 待实现 |
| OTA | 0xB0-0xBF | ⬜ 待实现 |
