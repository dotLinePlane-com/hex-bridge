---
name: flash-idf
description: 烧录 HEX-Bridge 固件到 ESP32（ESP-IDF v6.0.2 / esp32）。项目级覆盖全局 flash-idf，已固化烧录串口 COM5 与波特率 460800，无需再次确认。
---

# HEX-Bridge 固件烧录（项目级 flash-idf）

## 已固化参数（2026-08-09 烧录验证通过）

| 参数 | 值 |
|:---|:---|
| IDF 安装路径 | `D:\project\esp-idf-v6.0.2` |
| 烧录串口 | `COM5`（ESP32 UART0 调试口，CH340K） |
| 波特率 | `460800` |
| 目标芯片 | `esp32`（ESP32-D0WD-V3，MAC 28:56:2f:8f:82:88） |
| Flash | 2MB，dio，40MHz |
| 固件产物 | `build/hex-bridge.bin` |

## 首次调用注意

- 本 skill 已在 Project Profile 记录串口 COM5 与波特率 460800，无需再次向用户确认。
- 若 COM5 被占用或设备离线，重新列出串口探测 ESP32：
  ```powershell
  . D:\project\esp-idf-v6.0.2\export.ps1
  python -m esptool --chip esp32 -p COM5 chip-id
  ```
  其他串口（COM3/COM4 为扩展串口与 HEX-Bridge MCP 口，非烧录口）。

## 执行步骤

1. 激活环境：
   ```powershell
   . D:\project\esp-idf-v6.0.2\export.ps1
   ```
2. 烧录：
   ```powershell
   idf.py -p COM5 -b 460800 flash
   ```
3. 确认烧录成功：`Hash of data verified` + `Hard resetting via RTS pin...` + `Done`。
4. 可选：`idf.py -p COM5 -b 460800 monitor` 查看日志。

## 失败分流

- `Failed to connect to ESP32`：检查串口占用、板子是否供电、USB-TTL 连接；确认端口为 COM5。
- `build/` 无产物：返回 `artifact-missing`，推荐项目级 `build-idf`。
- 多串口歧义：用 `python -m esptool --chip esp32 -p <PORT> chip-id` 确认 MAC 28:56:2f:8f:82:88。

## 交接

- 查看运行日志：交给 `serial-monitor`（COM5，115200）。
- CAN / UART 测试：MCP 口 COM4，扩展口 COM3。
