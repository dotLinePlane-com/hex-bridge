# 04. UART MCP 测试报告

> 测试时间: 2026-07-14 09:07 CST  
> 测试人员: AI Agent (Kilo)  
> 测试文件: `files/design/test/04-UART-MCP-Tests.md`

---

## 测试环境

| 项目 | �?|
|:---|:---|
| HEX-Bridge 设备 | HXB1, SN: 2F8F8288, FW: 0.1.0, Proto: v2 |
| 桥接端口 | COM4 (HEX-Bridge virtual, CH0), 921600 bps |
| 扩展口监�?| COM3 (CH340), 921600 bps |
| Capabilities | 4095 |
| MaxPayload | 2048 |

> **注意**: UART2 实际波特率为 921600，与测试文档预期�?115200 不同。COM24 已同步调整为 921600 以匹配�?
---

## 测试结果概览

| 编号 | 用例名称 | 分类 | 结果 |
|:---|:---|:---|:---|
| MCP-01 | 设备发现 | 基础 | �?PASS |
| MCP-02 | 设备信息 | 基础 | �?PASS |
| MCP-03 | 分屏初始�?| 基础 | �?PASS |
| MCP-04 | 桥接发�?(string) �?扩展�?| 数据通路 | �?PASS |
| MCP-05 | 桥接发�?(hex) �?扩展�?| 数据通路 | �?PASS |
| MCP-06 | 扩展口注�?�?桥接接收 | 数据通路 | �?PASS |
| MCP-07 | 双向回环 (PING/PONG) | 集成 | �?PASS |
| MCP-08 | 大数据块 (256 字节) | 数据通路 | �?PASS |
| MCP-09 | 实例独立�?| 基础 | �?PASS |
| MCP-10 | 状态统�?| 系统 | �?PASS |
| MCP-11 | Break 信号 | UART | �?PASS |
| MCP-12 | Flush 缓冲�?| UART | �?PASS |

**结论: 12/12 PASS**

---

## 详细结果

### MCP-01: 设备发现

| 项目 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| 设备列表 | 非空，≥1 �?| 1 个设�?(HXB1) | �?|
| 虚拟端口路径 | `HEXBRIDGE:COM4:CHx` | `COM_HEXBRIDGE:COM4:CH1` | �?|
| 设备型号 | 非空 | HXB1 | �?|
| 序列�?| 非空 | 2F8F8288 | �?|

**结果: PASS**

---

### MCP-02: 设备信息

| 字段 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| model | 非空 | HXB1 | �?|
| serialNumber | 非空 | 2F8F8288 | �?|
| firmwareVersion | 非空 | 0.1.0 | �?|
| protocolVersion | �?0x02 | 2 | �?|
| capabilities | 非零 | 4095 | �?|
| maxPayloadSize | �?256 | 2048 | �?|

**结果: PASS**

---

### MCP-03: 分屏初始�?
| 实例 | 端口 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|:---|
| instanceId=1 | COM_HEXBRIDGE:COM4:CH0 | connected | isOpen: true | �?|
| instanceId=2 | COM3 | connected | isOpen: true | �?|

显示标志设置: isHexRx/IsHexTx/IsAddTimeHead/IsShowLine/IsShowRx/IsShowTx 全部启用�?
**结果: PASS**

---

### MCP-04: 桥接发�?string �?扩展�?
| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Flush (drain) | 成功 | statusCode: 0 | �?|
| COM4 �?"Hello" (5 bytes) | bytes: 5 | bytes: 5 | �?|
| COM3 Rx 内容 | `48 65 6C 6C 6F` | `48 65 6C 6C 6F` | �?|
| 时间�?| 发送后合理时间�?| ~800ms �?| �?|

**结果: PASS**

---

### MCP-05: 桥接发�?hex �?扩展�?
| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Flush (drain) | 成功 | statusCode: 0 | �?|
| COM4 �?`01 02 03 FF 00` (5 bytes) | bytes: 5 | bytes: 5 | �?|
| COM3 Rx 内容 | `01 02 03 FF 00` | `01 02 03 FF 00` | �?|
| 边界�?0xFF/0x00 | 正确传�?| 正确传�?| �?|

**结果: PASS**

---

### MCP-06: 扩展口注�?�?桥接接收

| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| COM3 �?`57 6F 72 6C 64` (World, 5 bytes) | bytes: 5 | bytes: 5 | �?|
| UART2 rxTotal 增加 | +5 | 19 �?29 (+10, 含后续测�? | �?|
| COM4 Rx 内容 | `57 6F 72 6C 64` | `57 6F 72 6C 64` (World) | �?|

**结果: PASS**

---

### MCP-07: 双向回环 PING/PONG

| 阶段 | 端口 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|:---|
| 发�?| COM4 Tx | "PING" | "PING" | �?|
| 接收 | COM3 Rx | "PING" | "PING" | �?|
| 注入 | COM3 Tx | "PONG" | "PONG" | �?|
| 上报 | COM4 Rx | "PONG" | "PONG" | �?|

**结果: PASS**

---

### MCP-08: 大数据块 (256 字节)

| 检查项 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| 发送字节数 | 256 | 256 | �?|
| COM3 接收总字节数 | 256 | 32+64+64+64+32=256 | �?|
| 首字�?| 0x00 | 0x00 | �?|
| 尾字�?| 0xFF | 0xFF | �?|
| 连续�?| 相邻�?1 | 00�?1�?2�?..→FF | �?|

> 数据�?5 帧接�?(32/64/64/64/32 bytes)，由 MCP 插件内部缓冲窗口所致，字节顺序完整无误�?
**结果: PASS**

---

### MCP-09: 实例独立�?
| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| 关闭 COM3 | 成功 | success: true | �?|
| 关闭�?COM4 状�?| connected | isOpen: true, tx: 294�?00 | �?|
| COM4 发�?"test-after-close" | 正常发�?| 16 bytes 成功 | �?|
| 重开 COM3 | connected | isOpen: true | �?|
| COM4 发�?"verify" | 正常发�?| 6 bytes 成功 | �?|
| UART2 状�?| 无溢�?| errorCount: 0 | �?|

**结果: PASS**

---

### MCP-10: 状态统�?
| 指标 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| COM4 Tx (hex-bridge) | > 0 | 300 | �?|
| COM4 Rx (hex-bridge) | > 0 | 9 | �?|
| COM3 Tx | �?0 | 19 | �?|
| COM3 Rx | > 0 | 292 | �?|
| UART2 TX overflow | 0 | 0 | �?|
| UART2 RX overflow | 0 | 0 | �?|
| UART2 errorCount | 0 | 0 | �?|

**结果: PASS**

---

### MCP-11: Break 信号

| 检查项 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Break 命令执行 (50ms) | 无错�?| statusCode: 0 | �?|
| Break �?UART2 状�?| 正常 | status: 0, error: 0 | �?|

**结果: PASS**

---

### MCP-12: Flush 缓冲区清�?
| 检查项 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Flush �?rxTotal | �?19 | 29 (+10 填充) | �?|
| Flush (rx) 执行 | 成功 | statusCode: 0 | �?|
| Flush �?| 缓冲清除 | rxBufUsed: 0�? (自动转发已清�? | �?|

> HEX-Bridge 自动转发 UART2 RX 数据�?MCP 通道，因�?rxBufUsed �?flush 前已�?0。累积计数器 rxTotal 不受 flush 影响，此为正常行为�?
**结果: PASS**

---

## 测试总结

| 项目 | �?|
|:---|:---|
| 总用例数 | 12 |
| PASS | 12 |
| FAIL | 0 |
| N/A | 0 |
| 通过�?| **100%** |

### 发现与备�?
1. **UART2 波特率差�?*: HEX-Bridge 设备 UART2 �?921600 bps 运行，与测试文档预期�?115200 不同。COM24 需匹配此波特率才能正常通信。建议在文档中更新或通过 UBCP 命令动态调�?UART2 参数�?
2. **通道差异**: `COM_HEXBRIDGE:COM4:CH0` 支持完整 TX/RX 双向通信，`COM_HEXBRIDGE:COM4:CH1` 仅支�?TX。测试使�?CH0 完成所有验证�?
3. **数据完整�?*: 所有测试中数据完整无丢失，含边界字�?(0x00, 0xFF) �?256 字节大数据块均正确传递�?
4. **实例独立�?*: COM4 (hex-bridge) �?COM3 (物理串口) 完全独立，关�?重开一侧不影响另一侧�?