# HEX-Bridge MCP Server

适用于支持本地 stdio MCP 的 Harness。需要 Python 3.10 或更高版本。一个 Server 进程控制一台设备，退出或调用 `disconnect` 会释放连接。

## Windows 安装

在项目根目录的 PowerShell 中执行。环境路径固定，Harness 可以从任意工作目录启动。

```powershell
$venv = Join-Path $env:LOCALAPPDATA "HEX-Bridge\mcp-venv"
python -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --upgrade .\mcp\dist\hexbridge_mcp-0.1.0-py3-none-any.whl
& "$venv\Scripts\hexbridge-mcp.exe" --help
(Get-Item "$venv\Scripts\hexbridge-mcp.exe").FullName
```

在 Harness 中新增本地 stdio 服务。使用上一条命令输出的绝对路径作为 `command`。以下为接受 `mcpServers` 配置的客户端示例，将 USER 替换为实际账户名。

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

1. 调用 `catalog` 查看请求名称、事件和协议主题，无需连接设备。
2. 调用 `device_info` 获取型号和固件版本。向 `request` 传入 `{"command":"GET_TOPOLOGY"}` 查看当前配置启用的通道。
3. 调用 `protocol_guide` 并指定 `topic`，如 `tcp`、`udp`、`websocket` 或 `profile`，查阅载荷格式。命令名取自 `catalog`。例如 `{"command":"UDP_SERVER_OPEN","payload_hex":"00000000000000"}` 在设备上申请一个临时 UDP 端口；成功响应包含句柄和实际端口。完成后用 `UDP_SERVER_CLOSE` 传入该两字节句柄释放端口。
4. `request` 返回的 `status` 为设备状态码，0 表示成功。完整响应在 `payload_hex`；超时后操作可能已执行。通过 `next_event` 领取 TCP_RECV、UDP_RECV、WS_RECV 等异步帧，可用 `timeout_s` 等待。字段 `dropped_since_last_read` 记录队列满时覆盖的事件数。
5. `dap_info` 的默认查询返回探针包大小（小端字节序），SWD 调试与下载使用项目现有 OpenOCD 工作流。

## 开发与验证

从完整项目根目录构建。构建过程从仓库打包共享 UBCP 编解码器、命令头文件和协议章节；生成的 wheel 可复制到其他主机安装。

```powershell
& "$venv\Scripts\python.exe" -m pip wheel --no-deps .\mcp -w .\mcp\dist
& "$venv\Scripts\python.exe" -m pip install --force-reinstall --no-deps .\mcp\dist\hexbridge_mcp-0.1.0-py3-none-any.whl
& "$venv\Scripts\python.exe" .\mcp\tests\smoke.py
```

测试通过 MCP 客户端启动已安装的入口，并使用本机模拟设备验证工具发现、协议资源、请求、异步事件、探针查询和重新连接。固件功能清单和维护要求见[主机端设计](../files/design/host/01-Harness-MCP.md)。
