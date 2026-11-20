---
name: flash-idf
description: 烧录已编译好的 HEX-Bridge 固件至 ESP32 目标板（COM5 / 460800）。当用户要求“下载固件”、“烧录固件”、“flash”或向开发板写入程序时使用此 skill。
---

# HEX-Bridge 固件烧录 (flash-idf)

本技能针对 HEX-Bridge 嵌入式固件工程，固化了烧录串口、波特率与复位时序。

---

## 固化硬件参数

| 参数项 | 配置值 | 说明 |
|:---|:---|:---|
| **ESP-IDF 路径** | `D:\project\esp-idf-v6.0.2` | 固化安装路径 |
| **烧录串口** | `COM5` | UART0 调试/下载口（CH340K） |
| **烧录波特率** | `460800 bps` | 快速烧录 |
| **芯片型号** | `ESP32-D0WD-V3` | MAC: `28:56:2f:8f:82:88` |
| **产物文件** | `build/hex-bridge.bin` | 需确保已编译成功 |

> **端口防呆提醒**：
> - `COM5`: 固件烧录口与 UART0 调试输出口
> - `COM4`: MCP 协议口（严禁烧录）
> - `COM3`: 外设扩展串口（严禁烧录）

---

## 执行步骤

1. **执行烧录**：
   ```powershell
   cmd.exe /c "D:\project\esp-idf-v6.0.2\export.bat && idf.py -p COM5 -b 460800 flash"
   ```

2. **验证结果**：
   - 确认输出日志包含：
     - `Connecting.....`
     - `Hash of data verified.`
     - `Hard resetting via RTS pin...`
     - `Done`
   - 说明程序已写入 Flash 并完成硬件复位启动。

3. **异常处理**：
   - 若报串口拒绝访问（Access Denied），请确认关闭占用了 COM5 的终端串口监视器，然后重试。

