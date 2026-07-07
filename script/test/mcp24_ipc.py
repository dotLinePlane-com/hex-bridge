"""
MCP24 IPC Handler — 用于 Kilo 逐步处理 MCP 工具请求

请求格式 (test_uart_mcp.py 写入 stdout):
  __MCP24__{"action":"open","port":"COM24","baudRate":115200}
  __MCP24__{"action":"send","data":"48656c6c6f","format":"hex"}
  __MCP24__{"action":"read","count":10,"display":"hex"}
  __MCP24__{"action":"close"}

Kilo 读取 stdout 中的 __MCP24__ 行，调用对应的 MCP 工具，
然后将结果写回 stdin (用 __MCP24_RES__ 前缀)：
  __MCP24_RES__{"status":"ok","data":"48656c6c6f"}

这样 test_uart_mcp.py 可以：
  - 打开 COM35 用 pyserial (UBCP 通信)
  - COM24 操作打印 __MCP24__ 到 stdout，从 stdin 读 __MCP24_RES__
  - COM24 数据在 serial-monitor MCP UI 中实时可见
"""
import json, sys, os, time
