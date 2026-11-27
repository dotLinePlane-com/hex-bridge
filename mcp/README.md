# HEX-Bridge MCP Server

HEX-Bridge MCP Server 在电脑上运行，由支持本地 stdio MCP 的 AI Agent（Harness）启动。无论使用预编译更新器还是自行编译固件，烧录后都按下面的步骤接入。电脑需要 Python 3.10 或更高版本。固件准备步骤见[项目快速入门](../README_zh.md#flash)。

首次接线请区分两个串口：**UART0** 用于烧录（台架 COM5），**UART1** 用于 Agent 控制（台架 COM4）。在设备管理器中确认自己电脑上的端口号。

## Windows 安装

在项目根目录的 PowerShell 中执行。环境路径固定，Harness 可以从任意工作目录启动。

```powershell
$venv = Join-Path $env:LOCALAPPDATA "HEX-Bridge\mcp-venv"
python -m venv $venv
$wheel = ".\mcp\dist\hexbridge_mcp-0.1.0-py3-none-any.whl"
if (Test-Path $wheel) {
    & "$venv\Scripts\python.exe" -m pip install --upgrade $wheel
} else {
    & "$venv\Scripts\python.exe" -m pip install --upgrade .\mcp
}
& "$venv\Scripts\hexbridge-mcp.exe" --help
(Get-Item "$venv\Scripts\hexbridge-mcp.exe").FullName
```

若单独收到 wheel，可在上述脚本中将 `$wheel` 改为该文件的绝对路径。源码安装使用完整 clone 中的共享协议文件。两种方式均可在具备 Python 的普通电脑上完成。

## 在 Agent 中配置连接

在 Harness 中新增本地 stdio 服务。使用上一条命令输出的绝对路径作为 `command`。以下为接受 `mcpServers` 配置的客户端示例，将 USER 替换为实际账户名。保存后重新加载 MCP 配置，或重启 Agent。

```json
{
  "mcpServers": {
    "hex-bridge": {
      "command": "C:/Users/USER/AppData/Local/HEX-Bridge/mcp-venv/Scripts/hexbridge-mcp.exe",
      "args": ["--serial", "COM4", "--baud", "115200"]
    }
  }
}
```

串口按实际 UART1 控制口与设备保存的波特率填写。Wi-Fi 管理可将 `args` 改为 `["--host", "192.168.1.105", "--tcp-port", "9500"]`，IP 替换为设备地址。TCP 9500 接管设备的唯一 UBCP 会话。使用串口管理时，可另外指定 `--dap-host 板端IP` 查询 TCP 4441 探针。

## 首次调用

可直接对 Agent 说：“请使用 hex-bridge，先调用 `catalog` 列出支持的模块，再调用 `device_info`，告诉我板卡型号、固件版本和序列号。”

看到 `catalog` 返回 `requests`、`events` 和 `guides`，说明 Agent 已能调用本地服务。看到 `device_info` 返回 `model`、`firmware` 和 `serial_number`，说明设备链路也已连通。

## 查询协议、收发数据和读取事件

1. 调用 `catalog` 查看请求名称、事件和协议主题，无需连接设备。
2. 调用 `device_info` 获取型号和固件版本。向 `request` 传入 `{"command":"GET_TOPOLOGY"}` 查看当前配置启用的通道。
3. 调用 `protocol_guide` 并指定 `topic`，如 `tcp`、`udp`、`websocket` 或 `profile`，查阅载荷格式。命令名取自 `catalog`。例如 `{"command":"UDP_SERVER_OPEN","payload_hex":"00000000000000"}` 在设备上申请一个临时 UDP 端口；成功响应包含句柄和实际端口。完成后用 `UDP_SERVER_CLOSE` 传入该两字节句柄释放端口。
4. `request` 返回的 `status` 为设备状态码，0 表示成功。完整响应在 `payload_hex`；超时后操作可能已执行。通过 `next_event` 领取 TCP_RECV、UDP_RECV、WS_RECV 等异步帧，可用 `timeout_s` 等待。字段 `dropped_since_last_read` 记录队列满时覆盖的事件数。
5. `dap_info` 的默认查询返回探针包大小（小端字节序），SWD 调试与下载使用项目现有 OpenOCD 工作流。

## 连接问题

| 现象 | 排查方法 |
|---|---|
| Agent 中找不到 hex-bridge 工具 | 在 PowerShell 运行安装步骤里的 `--help` 命令；确认 Agent 使用同一个 EXE 的绝对路径、本地 stdio 模式，并已重新加载配置。 |
| `catalog` 成功，`device_info` 串口超时或提示占用 | 核对 UART1 的 COM 号和保存的波特率。关闭占用该口的串口助手；若另一 MCP 会话正在使用设备，在该会话调用 `disconnect`。若有客户端已接入 TCP 9500，先断开该 TCP 会话，再重试串口。 |
| 使用 Wi-Fi 时设备无响应 | 确认板卡已联网、IP 正确且电脑可访问 TCP 9500。在 PowerShell 中用 `Test-NetConnection 板端IP -Port 9500` 检查端口可达性，然后重试 `device_info`。 |

一个 Server 进程控制一台设备。退出或调用 `disconnect` 会释放连接并清除排队事件。下一次设备请求将按当前启动参数重新连接。

## 开发与验证

从完整项目根目录构建。构建过程从仓库打包共享 UBCP 编解码器、命令头文件和协议章节；生成的 wheel 可复制到其他主机安装。

```powershell
& "$venv\Scripts\python.exe" -m pip wheel --no-deps .\mcp -w .\mcp\dist
& "$venv\Scripts\python.exe" -m pip install --force-reinstall --no-deps .\mcp\dist\hexbridge_mcp-0.1.0-py3-none-any.whl
& "$venv\Scripts\python.exe" .\mcp\tests\smoke.py
```

测试通过 MCP 客户端启动已安装的入口，并使用本机模拟设备验证工具发现、协议资源、请求、异步事件、探针查询和重新连接。固件功能清单和维护要求见[主机端设计](../files/design/host/01-Harness-MCP.md)。
