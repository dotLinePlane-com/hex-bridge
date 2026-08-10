---
name: build-idf
description: 编译 HEX-Bridge 固件（ESP-IDF v6.0.2 / esp32）。项目级覆盖全局 build-idf，已固化 IDF 路径与目标芯片，无需再次确认。
---

# HEX-Bridge 固件编译（项目级 build-idf）

## 已固化参数（2026-08-09 验证通过）

| 参数 | 值 |
|:---|:---|
| IDF 安装路径 | `D:\project\esp-idf-v6.0.2` |
| 目标芯片 | `esp32`（ESP32-D0WD-V3） |
| 环境激活 | PowerShell: `. D:\project\esp-idf-v6.0.2\export.ps1` |
| 构建目录 | 工程根目录 `build/` |
| 固件产物 | `build/hex-bridge.bin` |

## 首次调用注意

- 本 skill 已在 Project Profile 记录以上参数，无需再次向用户确认 IDF_PATH / 目标芯片。
- 若 IDF 版本或工具链报缺工具，运行：
  `C:\Users\wuke\.espressif\python_env\idf6.0_py3.11_env\Scripts\python.exe D:\project\esp-idf-v6.0.2\tools\idf_tools.py install --targets esp32`

## 执行步骤

1. 激活环境：
   ```powershell
   . D:\project\esp-idf-v6.0.2\export.ps1
   ```
2. 执行构建：
   ```powershell
   idf.py build
   ```
3. 确认产物：
   - `build/hex-bridge.bin`
   - 构建成功标志：`Project build complete. To flash, run: idf.py flash`
4. 将构建结果交给 `flash-idf`。

## 失败分流

- `idf.py` 不可用：检查是否已 `. D:\project\esp-idf-v6.0.2\export.ps1`。
- 编译错误：返回 `project-config-error`，检查 `main/` 源码修改。
- 构建成功但无产物：返回 `artifact-missing`。

## 交接

- 下一步烧录：交给项目级 `flash-idf`（串口 COM5，波特率 460800）。
