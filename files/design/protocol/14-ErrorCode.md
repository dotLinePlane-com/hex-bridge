# 14. 错误码定义

## 14.1 错误码结构

错误码为 1 字节 (u8)，按模块分组：

```
高4位: 模块标识    低4位: 模块内错误编号
 ┌───────────┐   ┌───────────┐
 │  0x0-0xF  │   │  0x0-0xF  │
 └───────────┘   └───────────┘
```

---

## 14.2 通用错误码 (0x00-0x0F)

适用于所有模块的通用状态。

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0x00` | SUCCESS | 操作成功 |
| `0x01` | ERR_UNKNOWN | 未知错误 |
| `0x02` | ERR_PARAM | 参数错误（参数值超出范围或格式不正确） |
| `0x03` | ERR_TIMEOUT | 操作超时 |
| `0x04` | ERR_BUSY | 设备忙（资源被占用） |
| `0x05` | ERR_NOT_OPEN | 通道/接口未打开 |
| `0x06` | ERR_NOT_SUPPORT | 不支持的操作或功能 |
| `0x07` | ERR_BUFFER_FULL | 缓冲区满 |
| `0x08` | ERR_CRC | CRC 校验失败 |
| `0x09` | ERR_FRAME | 帧格式错误（帧头、帧尾或长度不正确） |
| `0x0A` | ERR_CHANNEL_INVALID | 无效的通道号 |
| `0x0B` | ERR_ALREADY_OPEN | 通道已打开（重复打开） |
| `0x0C` | ERR_PERMISSION | 权限不足（操作被禁止） |
| `0x0D` | ERR_OVERFLOW | 数据溢出 |
| `0x0E` | ERR_SEQ_MISMATCH | 序列号不匹配 |
| `0x0F` | ERR_VERSION | 协议版本不兼容 |

---

## 14.3 CAN 错误码 (0x10-0x1F)

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0x10` | ERR_CAN_BUS_OFF | CAN 总线关闭 (Bus Off) |
| `0x11` | ERR_CAN_PASSIVE | CAN 被动错误状态 |
| `0x12` | ERR_CAN_TX_FAIL | CAN 发送失败（仲裁丢失或错误） |
| `0x13` | ERR_CAN_FILTER_FULL | 过滤器已满 |
| `0x14` | ERR_CAN_FIFO_OVERFLOW | CAN 接收 FIFO 溢出 |
| `0x15` | ERR_CAN_FD_NOT_SUPPORT | 不支持 CAN FD |
| `0x16-0x1F` | — | 保留 |

---

## 14.4 SPI 错误码 (0x20-0x2F)

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0x20` | ERR_SPI_TRANSFER | SPI 传输错误 |
| `0x21` | ERR_SPI_CS_INVALID | 无效的 CS 引脚 |
| `0x22` | ERR_SPI_CLOCK | SPI 时钟频率不支持 |
| `0x23` | ERR_SPI_CS_MODE | CS 模式错误（自动模式下调用手动控制） |
| `0x24-0x2F` | — | 保留 |

---

## 14.5 I2C 错误码 (0x30-0x3F)

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0x30` | ERR_I2C_NACK | 从设备无应答 (NACK) |
| `0x31` | ERR_I2C_BUS_ERROR | I2C 总线错误（SDA/SCL 异常） |
| `0x32` | ERR_I2C_ARB_LOST | 总线仲裁丢失 |
| `0x33` | ERR_I2C_ADDR_INVALID | 无效的从设备地址 |
| `0x34-0x3F` | — | 保留 |

---

## 14.6 网络错误码 (0x40-0x4F)

适用于网络配置、TCP、UDP、WebSocket。

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0x40` | ERR_NET_DISCONNECTED | 网络未连接（无链路） |
| `0x41` | ERR_NET_CONN_REFUSED | 连接被拒绝 |
| `0x42` | ERR_NET_TIMEOUT | 网络超时（连接/发送/接收） |
| `0x43` | ERR_NET_HANDLE_INVALID | 无效的网络句柄 |
| `0x44` | ERR_NET_BUFFER_FULL | 网络发送缓冲区满 |
| `0x45` | ERR_NET_PORT_IN_USE | 端口已被占用 |
| `0x46` | ERR_NET_DNS_FAIL | DNS 解析失败 |
| `0x47` | ERR_NET_NO_IP | 未获取到 IP 地址 |
| `0x48` | ERR_NET_MAX_CONN | 已达最大连接数 |
| `0x49` | ERR_NET_WS_HANDSHAKE | WebSocket 握手失败 |
| `0x4A` | ERR_NET_WS_PROTOCOL | WebSocket 协议错误 |
| `0x4B-0x4F` | — | 保留 |

---

## 14.7 GPIO 错误码 (0x80-0x8F)

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0x80` | ERR_GPIO_PIN_INVALID | 无效的引脚号 |
| `0x81` | ERR_GPIO_DIR_MISMATCH | 方向不匹配（如对输入引脚写入） |
| `0x82` | ERR_GPIO_IN_USE | 引脚被其他功能占用 |
| `0x83-0x8F` | — | 保留 |

---

## 14.8 UART 错误码 (0xA0-0xAF)

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0xA0` | ERR_UART_PARITY | UART 校验错误 |
| `0xA1` | ERR_UART_FRAME | UART 帧错误 |
| `0xA2` | ERR_UART_OVERFLOW | UART 接收缓冲区溢出 |
| `0xA3` | ERR_UART_BAUD | 不支持的波特率 |
| `0xA4` | ERR_UART_BREAK | 检测到 Break 信号 |
| `0xA5-0xAF` | — | 保留 |

---

## 14.9 批量传输错误码 (0x90-0x9F)

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0x90` | ERR_BULK_SESSION_INVALID | 无效的会话 ID |
| `0x91` | ERR_BULK_SEQ_ERROR | 帧序号错误（乱序） |
| `0x92` | ERR_BULK_CRC_ERROR | 帧数据 CRC 校验失败 |
| `0x93` | ERR_BULK_ABORTED | 传输已被中止 |
| `0x94` | ERR_BULK_MAX_RETRIES | 超过最大重试次数 |
| `0x95-0x9F` | — | 保留 |

---

## 14.10 OTA 错误码 (0xB0-0xBF)

| 错误码 | 名称 | 说明 |
|:---|:---|:---|
| `0xB0` | ERR_OTA_NO_SPACE | 目标分区空间不足 |
| `0xB1` | ERR_OTA_SHA256_MISMATCH | SHA-256 校验不匹配 |
| `0xB2` | ERR_OTA_SIZE_MISMATCH | 固件大小与声明不符 |
| `0xB3` | ERR_OTA_INVALID_IMAGE | 固件格式无效（非合法 ESP-IDF 固件） |
| `0xB4` | ERR_OTA_SESSION_INVALID | 无效的 OTA 会话 ID |
| `0xB5` | ERR_OTA_SEQ_ERROR | 数据块序号错误（乱序或缺失） |
| `0xB6` | ERR_OTA_WRITE_FAIL | 分区写入失败（Flash 写入错误） |
| `0xB7` | ERR_OTA_IN_PROGRESS | 已有 OTA 进行中（不能同时进行两个） |
| `0xB8` | ERR_OTA_ROLLBACK_FAIL | 回滚失败（无可用旧分区） |
| `0xB9` | ERR_OTA_SAME_VERSION | 固件版本相同（未设置强制升级） |
| `0xBA-0xBF` | — | 保留 |
