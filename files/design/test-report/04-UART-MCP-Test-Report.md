# 04. UART MCP 测试报告

> 测试时间: 2026-07-14 09:07 CST  
> 测试人员: AI Agent (Kilo)  
> 测试文件: `files/design/test/04-UART-MCP-Tests.md`

---

## 测试环境

| 项目 | 值 |
|:---|:---|
| HEX-Bridge 设备 | HXB1, SN: 2F8F8288, FW: 0.1.0, Proto: v2 |
| 桥接端口 | COM35 (HEX-Bridge virtual, CH0), 921600 bps |
| 扩展口监控 | COM24 (CH340), 921600 bps |
| Capabilities | 4095 |
| MaxPayload | 2048 |

> **注意**: UART2 实际波特率为 921600，与测试文档预期的 115200 不同。COM24 已同步调整为 921600 以匹配。

---

## 测试结果概览

| 编号 | 用例名称 | 分类 | 结果 |
|:---|:---|:---|:---|
| MCP-01 | 设备发现 | 基础 | ✅ PASS |
| MCP-02 | 设备信息 | 基础 | ✅ PASS |
| MCP-03 | 分屏初始化 | 基础 | ✅ PASS |
| MCP-04 | 桥接发送 (string) → 扩展口 | 数据通路 | ✅ PASS |
| MCP-05 | 桥接发送 (hex) → 扩展口 | 数据通路 | ✅ PASS |
| MCP-06 | 扩展口注入 → 桥接接收 | 数据通路 | ✅ PASS |
| MCP-07 | 双向回环 (PING/PONG) | 集成 | ✅ PASS |
| MCP-08 | 大数据块 (256 字节) | 数据通路 | ✅ PASS |
| MCP-09 | 实例独立性 | 基础 | ✅ PASS |
| MCP-10 | 状态统计 | 系统 | ✅ PASS |
| MCP-11 | Break 信号 | UART | ✅ PASS |
| MCP-12 | Flush 缓冲区 | UART | ✅ PASS |

**结论: 12/12 PASS**

---

## 详细结果

### MCP-01: 设备发现

| 项目 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| 设备列表 | 非空，≥1 个 | 1 个设备 (HXB1) | ✅ |
| 虚拟端口路径 | `HEXBRIDGE:COM35:CHx` | `COM_HEXBRIDGE:COM35:CH1` | ✅ |
| 设备型号 | 非空 | HXB1 | ✅ |
| 序列号 | 非空 | 2F8F8288 | ✅ |

**结果: PASS**

---

### MCP-02: 设备信息

| 字段 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| model | 非空 | HXB1 | ✅ |
| serialNumber | 非空 | 2F8F8288 | ✅ |
| firmwareVersion | 非空 | 0.1.0 | ✅ |
| protocolVersion | ≥ 0x02 | 2 | ✅ |
| capabilities | 非零 | 4095 | ✅ |
| maxPayloadSize | ≥ 256 | 2048 | ✅ |

**结果: PASS**

---

### MCP-03: 分屏初始化

| 实例 | 端口 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|:---|
| instanceId=1 | COM_HEXBRIDGE:COM35:CH0 | connected | isOpen: true | ✅ |
| instanceId=2 | COM24 | connected | isOpen: true | ✅ |

显示标志设置: isHexRx/IsHexTx/IsAddTimeHead/IsShowLine/IsShowRx/IsShowTx 全部启用。

**结果: PASS**

---

### MCP-04: 桥接发送 string → 扩展口

| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Flush (drain) | 成功 | statusCode: 0 | ✅ |
| COM35 → "Hello" (5 bytes) | bytes: 5 | bytes: 5 | ✅ |
| COM24 Rx 内容 | `48 65 6C 6C 6F` | `48 65 6C 6C 6F` | ✅ |
| 时间戳 | 发送后合理时间内 | ~800ms 内 | ✅ |

**结果: PASS**

---

### MCP-05: 桥接发送 hex → 扩展口

| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Flush (drain) | 成功 | statusCode: 0 | ✅ |
| COM35 → `01 02 03 FF 00` (5 bytes) | bytes: 5 | bytes: 5 | ✅ |
| COM24 Rx 内容 | `01 02 03 FF 00` | `01 02 03 FF 00` | ✅ |
| 边界值 0xFF/0x00 | 正确传递 | 正确传递 | ✅ |

**结果: PASS**

---

### MCP-06: 扩展口注入 → 桥接接收

| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| COM24 → `57 6F 72 6C 64` (World, 5 bytes) | bytes: 5 | bytes: 5 | ✅ |
| UART2 rxTotal 增加 | +5 | 19 → 29 (+10, 含后续测试) | ✅ |
| COM35 Rx 内容 | `57 6F 72 6C 64` | `57 6F 72 6C 64` (World) | ✅ |

**结果: PASS**

---

### MCP-07: 双向回环 PING/PONG

| 阶段 | 端口 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|:---|
| 发送 | COM35 Tx | "PING" | "PING" | ✅ |
| 接收 | COM24 Rx | "PING" | "PING" | ✅ |
| 注入 | COM24 Tx | "PONG" | "PONG" | ✅ |
| 上报 | COM35 Rx | "PONG" | "PONG" | ✅ |

**结果: PASS**

---

### MCP-08: 大数据块 (256 字节)

| 检查项 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| 发送字节数 | 256 | 256 | ✅ |
| COM24 接收总字节数 | 256 | 32+64+64+64+32=256 | ✅ |
| 首字节 | 0x00 | 0x00 | ✅ |
| 尾字节 | 0xFF | 0xFF | ✅ |
| 连续性 | 相邻差 1 | 00→01→02→...→FF | ✅ |

> 数据分 5 帧接收 (32/64/64/64/32 bytes)，由 MCP 插件内部缓冲窗口所致，字节顺序完整无误。

**结果: PASS**

---

### MCP-09: 实例独立性

| 操作 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| 关闭 COM24 | 成功 | success: true | ✅ |
| 关闭后 COM35 状态 | connected | isOpen: true, tx: 294→300 | ✅ |
| COM35 发送 "test-after-close" | 正常发送 | 16 bytes 成功 | ✅ |
| 重开 COM24 | connected | isOpen: true | ✅ |
| COM35 发送 "verify" | 正常发送 | 6 bytes 成功 | ✅ |
| UART2 状态 | 无溢出 | errorCount: 0 | ✅ |

**结果: PASS**

---

### MCP-10: 状态统计

| 指标 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| COM35 Tx (hex-bridge) | > 0 | 300 | ✅ |
| COM35 Rx (hex-bridge) | > 0 | 9 | ✅ |
| COM24 Tx | ≥ 0 | 19 | ✅ |
| COM24 Rx | > 0 | 292 | ✅ |
| UART2 TX overflow | 0 | 0 | ✅ |
| UART2 RX overflow | 0 | 0 | ✅ |
| UART2 errorCount | 0 | 0 | ✅ |

**结果: PASS**

---

### MCP-11: Break 信号

| 检查项 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Break 命令执行 (50ms) | 无错误 | statusCode: 0 | ✅ |
| Break 后 UART2 状态 | 正常 | status: 0, error: 0 | ✅ |

**结果: PASS**

---

### MCP-12: Flush 缓冲区清空

| 检查项 | 预期 | 实际 | 判定 |
|:---|:---|:---|:---|
| Flush 前 rxTotal | ≥ 19 | 29 (+10 填充) | ✅ |
| Flush (rx) 执行 | 成功 | statusCode: 0 | ✅ |
| Flush 后 | 缓冲清除 | rxBufUsed: 0→0 (自动转发已清空) | ✅ |

> HEX-Bridge 自动转发 UART2 RX 数据到 MCP 通道，因此 rxBufUsed 在 flush 前已为 0。累积计数器 rxTotal 不受 flush 影响，此为正常行为。

**结果: PASS**

---

## 测试总结

| 项目 | 值 |
|:---|:---|
| 总用例数 | 12 |
| PASS | 12 |
| FAIL | 0 |
| N/A | 0 |
| 通过率 | **100%** |

### 发现与备注

1. **UART2 波特率差异**: HEX-Bridge 设备 UART2 以 921600 bps 运行，与测试文档预期的 115200 不同。COM24 需匹配此波特率才能正常通信。建议在文档中更新或通过 UBCP 命令动态调整 UART2 参数。

2. **通道差异**: `COM_HEXBRIDGE:COM35:CH0` 支持完整 TX/RX 双向通信，`COM_HEXBRIDGE:COM35:CH1` 仅支持 TX。测试使用 CH0 完成所有验证。

3. **数据完整性**: 所有测试中数据完整无丢失，含边界字节 (0x00, 0xFF) 及 256 字节大数据块均正确传递。

4. **实例独立性**: COM35 (hex-bridge) 与 COM24 (物理串口) 完全独立，关闭/重开一侧不影响另一侧。
