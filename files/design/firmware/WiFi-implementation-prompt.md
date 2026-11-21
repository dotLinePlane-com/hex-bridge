# HEX-Bridge Wi-Fi 实现任务 Prompt

在 HEX-Bridge 的 ESP-IDF 工程中实现并验证 ESP32 单接口 Wi-Fi STA。使用 GPT-6.1-sol、中等推理强度的子代理直接修改代码。以 files/design/firmware/06-WiFi-STA.md、files/design/protocol/03-System.md 和 files/design/protocol/08-Network.md 为接口契约。先核对当前实现和工作区变更，保留既有调用方式。

1. 固件代理负责 ESP32 内置 Wi-Fi、启动与构建依赖，接入 UART1 UBCP 的 WIFI_JOIN、WIFI_STATUS、WIFI_LEAVE 和 WIFI_FORGET。实现离线能力发现、异步连接与退避、DHCP/静态地址、IPv4 事件、凭据持久化、取消和重试。UART 与 CAN 在网络不可用时应继续工作。
2. Socket 代理负责 TCP、UDP、WebSocket 的 IP 就绪检查、掉线时回收句柄和事件，确保恢复后可以重新创建服务。与固件代理明确回调和锁的归属。
3. 主机代理负责现有网络 CLI、能力发现及主机测试。复用 UBCP，隐藏口令输入，维持原有 NET 命令和旧设备兼容性。
4. 主代理审查代码、构建 ESP32 镜像、核对分区容量并执行可用测试。硬件验收涵盖关联和 IPv4 两个阶段、实际 socket 收发、断线重连、保存与忘记及并发 CAN；逐项区分已验证结果和待测项。
5. 使用项目内 connect-hex-wifi 技能获取工作台凭据。默认目标网络为 CU_Jm2v。禁止将真实口令写入源代码、测试夹具、任务 prompt 或日志。覆盖板上固件前确认已获烧录授权。
