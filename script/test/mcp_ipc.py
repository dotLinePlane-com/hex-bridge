"""
MCP24 IPC Handler �?用于 Kilo 逐步处理 MCP 工具请求

请求格式 (test_uart_mcp.py 写入 stdout):
  __MCP24__{"action":"open","port":"COM3","baudRate":115200}
  __MCP24__{"action":"send","data":"48656c6c6f","format":"hex"}
  __MCP24__{"action":"read","count":10,"display":"hex"}
  __MCP24__{"action":"close"}

Kilo 读取 stdout 中的 __MCP24__ 行，调用对应�?MCP 工具�?然后将结果写�?stdin (�?__MCP24_RES__ 前缀)�?  __MCP24_RES__{"status":"ok","data":"48656c6c6f"}

这样 test_uart_mcp.py 可以�?  - 打开 COM4 �?pyserial (UBCP 通信)
  - COM3 操作打印 __MCP24__ �?stdout，从 stdin �?__MCP24_RES__
  - COM3 数据�?serial-monitor MCP UI 中实时可�?"""
import json, sys, os, time
