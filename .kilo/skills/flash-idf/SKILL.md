---
name: flash-idf
description: 烧录 HEX-Bridge 固件到 ESP32（ESP-IDF v6.0.2 / esp32）。项目级覆盖全局 flash-idf，已固化烧录串口 COM5 与波特率 460800，无需再次确认。
---

# HEX-Bridge 固件烧录（项目级 flash-idf）

## 已固化参数

| 参数 | 值 |
|:---|:---|
| IDF 安装路径 | `D:\project\esp-idf-v6.0.2` |
| 烧录串口 | `COM5`（ESP32 UART0 调试口，CH340K） |
| 波特率 | `460800` |
| 目标芯片 | `esp32`（ESP32-D0WD-V3，MAC 28:56:2f:8f:82:88） |
| Flash | 2MB，dio，40MHz |
| 固件产物 | `build/hex-bridge.bin` |

## 执行步骤

1. 执行烧录（推荐使用 `cmd.exe /c` 避免 PowerShell Profile 污染）：
   ```powershell
   cmd.exe /c "D:\project\esp-idf-v6.0.2\export.bat && idf.py -p COM5 -b 460800 flash"
   ```
2. 确认烧录成功：`Hash of data verified` + `Hard resetting via RTS pin...` + `Done`。

## 失败分流

- `could not open port 'COM5'`：检查是否有监视器或其他串口调试助手占用 COM5。
- `Failed to connect to ESP32`：检查开发板供电与数据线。
