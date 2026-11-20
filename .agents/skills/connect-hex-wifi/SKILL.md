---
name: connect-hex-wifi
description: 通过 UART1 为 HEX-Bridge 接入 CU_Jm2v，并验证板端 IPv4。用于连接或重连项目 Wi-Fi、检查板端联网状态或确认固件配网能力。
---

从本技能目录运行 `python scripts/connect.py --port COM3`。COM3 是此工作台上次确认的 UART1；换线后使用已确认的 UART1 端口。串口为 115200。仅查询时追加 `--status`。默认临时连接；用户明确要求板端重启后自动连接时追加 `--save`。

脚本读取 GET_INFO 并检查 WIFI_STA 能力位。旧固件会在取用口令前返回。支持该能力时按工程的 08-Network.md 发送 JOIN，并同时核对 SSID、状态与 IPv4。遇到超时先查询状态再决定是否重试。报告板端 IP 或具体失败原因。此流程仅操作板端。

默认凭据位于此工作台工程上一级的 .hex-bridge-private 目录，由 Windows 加密并限制访问。更换电脑时可从受保护的凭据来源向脚本进程注入 HEX_BRIDGE_WIFI_PASSWORD。不要在命令行参数、日志或串口抓包中记录口令。
