# Wi-Fi STA 网络设计

HEX-Bridge 通过 ESP32 内置 Wi-Fi 加入现有 2.4 GHz AP，PC 与设备在可互通的局域网内运行 TCP、UDP 和 WebSocket。首版支持一个 STA、一个保存的网络和 IPv4；通过 UART1 输入已知 SSID。默认 DHCP，静态地址沿用 NET_CONFIG。CAN 和串口启动独立于网络状态。

## 固件职责

1. 启动时初始化 NVS、消息总线和 UART1。网络模块创建默认 STA netif，注册 Wi-Fi/IP 回调。网络初始化失败只影响网络模块，UART1 仍能查询失败原因，CAN 继续工作。
2. 网络由 `mod_network` 通过 ESP32 内置 Wi-Fi STA 管理；TCP/UDP/WebSocket 模块使用 Wi-Fi STA 提供的 IPv4 网络。SPI、CAN、I²C、UART 的引脚仍按板级引脚表固定。
3. 用单个网络任务串行处理命令、驱动事件和重试。Wi-Fi 驱动使用 RAM 配置；应用管理独立 NVS 记录，原子保存 SSID、认证类型与密钥。RAM 配网成功也不覆盖已有记录。下次启动仅尝试已保存配置。CLI 隐藏口令输入，串口帧跟踪对 JOIN 脱敏。
4. 找不到 AP、链路丢失或 DHCP 超时（30 秒）时，按 1、2、4、8、16、30 秒退避，之后每 30 秒重试。认证失败停止重试；通过新的 JOIN 恢复。每次切换会话时撤销旧定时器并等待旧连接断开后再关联。
5. 失去有效 IP 时通过各 socket 模块现有关闭流程回收监听和连接句柄、上报已有断开事件。主机在 IP_ACQUIRED 后重建所需服务；网络未就绪时新建连接返回 NET_NO_IP。UART1 和 CAN 继续服务。
6. 命令及字节布局见 [网络协议](../protocol/08-Network.md)，能力发现见 [系统协议](../protocol/03-System.md)。旧版 CLI 可在已配网设备上使用通用网络命令；新版 CLI 依能力显示接口名称并提供 join/status/leave/forget。

## 上板验收

| 场景 | 判定 |
|---|---|
| 冷启动，无凭据、无 AP | UART1 可 PING，CAN 对 PCAN/SLCAN 双向收发，网络状态为空闲 |
| 正确凭据，DHCP / 静态地址 | 分别验证关联、IP 就绪、DNS、PC 与板端的 TCP/UDP/WS 双向负载 |
| 密码错误、AP 离线、DHCP 无应答 | 可区分失败原因，重试符合策略，串口命令仍响应 |
| 同一 JOIN 重发、重试期间 LEAVE/FORGET | 无重复任务、迟到事件、意外重连或残留凭据 |
| 保存、临时切换、重启、忘记后重启 | 只恢复最后成功保存的配置；忘记后为空闲 |
| Wi-Fi 断开和恢复，CAN 同时收发 | 网络事件顺序正确，旧句柄失效，可重建服务；核对 CAN 序号和错误计数 |
| 新旧主机兼容 | 原 NET_STATUS 记录仍为 17 字节；老设备不出现配网入口 |

上位机通过 GET_INFO 的 WIFI_STA 位确认当前固件支持配网。验收时分别记录协议响应、设备 IPv4 和对端实收数据。
