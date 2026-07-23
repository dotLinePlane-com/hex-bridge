# 6. 以太网 (LAN8720) 驱动及网络模块设计

## 6.1 概述

HEX-Bridge 通过 LAN8720A 以太网 PHY 芯片提供 10/100 Mbps 有线网络接入能力。基于 ESP-IDF 内置的 `esp_eth` 框架实现 PHY 驱动、lwIP 协议栈集成以及 UBCP 协议中的网络命令组 (0x40-0x4F / 0x50-0x5F / 0x60-0x6F / 0x70-0x7F)。

### 硬件配置

| 参数 | 值 |
|:---|:---|
| PHY 芯片 | LAN8720A (SMSC) |
| 通信接口 | RMII (Reduced Media Independent Interface) |
| RMII 时钟 | 50 MHz (外部晶振, 由 LAN8720 的 REF_CLK 输出到 GPIO 0) |
| 时钟模式 | `EMAC_CLK_EXT_IN` (PHY 提供 REF_CLK, ESP-IDF v6.0.1 命名) |
| SMI 管理 | MDC=GPIO 23, MDIO=GPIO 18 (**需外接 4.7kΩ 上拉**) |
| PHY 复位 | 无 (PHY 依赖芯片自带 RC 上电复位, GPIO5 当前硬件版本未连接) |
| PHY 地址 | 0x01 (PHYAD0 Pin 拉高) |
| MAC 地址 | 28:56:2f:8f:82:88 (写入到 ESP-IDF efuse 的 MAC 地址) |

### RMII 固定引脚 (ESP32 EMAC)

| 信号 | GPIO | 方向 | 说明 |
|:---|:---|:---|:---|
| EMAC_TXD0 | GPIO 19 | 输出 | RMII 数据发送 Bit0 |
| EMAC_TXD1 | GPIO 22 | 输出 | RMII 数据发送 Bit1 |
| EMAC_TX_EN | GPIO 21 | 输出 | RMII 发送使能 |
| EMAC_RXD0 | GPIO 25 | 输入 | RMII 数据接收 Bit0 |
| EMAC_RXD1 | GPIO 26 | 输入 | RMII 数据接收 Bit1 |
| EMAC_CRS_DV | GPIO 27 | 输入 | RMII 载波检测/数据有效 |
| EMAC_CLK_IN | GPIO 0 | 输入 | **Strapping 引脚** — 50MHz REF_CLK |

> **关键设计约束**：GPIO 0 作为 Strapping 引脚，上电复位时若有外部时钟信号会导致 ESP32 进入错误的 Boot 模式。必须在 `PHY_RST (GPIO 5)` 外接 10kΩ 下拉电阻，确保上电时 LAN8720 处于复位状态 (REF_CLK 输出为高阻态)，固件启动后由软件拉高 GPIO 5 激活 PHY。

---

## 6.2 架构分层

```
┌───────────────────────────────────────────────────────────────────┐
│                     UBCP 网络命令处理                              │
│  [mod_network] (0x40-0x4F)  [mod_tcp] (0x50-0x5F)                │
│  [mod_udp] (0x60-0x6F)      [mod_ws] (0x70-0x7F)                 │
├───────────────────────────────────────────────────────────────────┤
│                    lwIP 协议栈 (ESP-IDF 内置)                       │
│  TCP/IP Stack, Socket API, DHCP Client, DNS Resolver              │
├───────────────────────────────────────────────────────────────────┤
│  esp_netif (Wi-Fi/Ethernet 抽象层)                                 │
│  提供 esp_netif_driver_eth 适配                                    │
├───────────────────────────────────────────────────────────────────┤
│  esp_eth (以太网驱动框架)                                           │
│  ┌──────────────┐  ┌──────────────┐                               │
│  │ esp_eth_mac   │  │ esp_eth_phy  │  (LAN8720)                    │
│  │ (ESP32 EMAC) │  │ (lan8720.c)  │                               │
│  └──────────────┘  └──────────────┘                               │
├───────────────────────────────────────────────────────────────────┤
│  硬件层                                                            │
│  ┌──────────────────────┐  ┌──────────────────────────────┐       │
│  │ ESP32 EMAC (MAC)     │  │ LAN8720A (PHY)               │       │
│  │ RMII 固定引脚        │  │ 10/100 Base-T                │       │
│  └──────────────────────┘  └──────────────────────────────┘       │
└───────────────────────────────────────────────────────────────────┘
```

---

## 6.3 LAN8720 驱动初始化

### 6.3.1 PHY 复位时序

> **2026-07 更新**: 当前硬件版本 GPIO5 未连接到 LAN8720 RST_N 引脚。PHY 依赖芯片自带 RC 上电复位 (POR)。以下为原始设计文档中设定的流程，实际代码中已移除手动 GPIO 复位步骤。

原始设计复位流程：

```
上电默认:  GPIO 5 = LOW (外接 10kΩ 下拉) → LAN8720 处于复位状态
              REF_CLK 输出高阻态 → GPIO 0 安全，ESP32 正常启动

固件启动:   app_main() → network_init() → eth_hw_init()
              │
              ├─ 1. esp_netif_init() / esp_event_loop_create_default()
              │
              ├─ 2. esp_eth_mac_new_esp32(&esp32_emac_config, &mac_config)
              │      └ smi_gpio.mdc_num=23, smi_gpio.mdio_num=18
              │      └ clock_config.rmii = {EMAC_CLK_EXT_IN, clock_gpio=0}
              │
              ├─ 3. esp_eth_phy_new_lan87xx(&phy_config)
              │      └ phy_addr=0x01, reset_gpio_num=-1
              │      └ 组件: espressif/lan87xx (idf_component.yml)
              │
              ├─ 4. esp_eth_driver_install(&eth_config, &eth_handle)
              │      └ MAC + PHY 驱动安装, 至此硬件已就绪
              │
              ├─ 5. esp_netif_new() + esp_eth_new_netif_glue() + esp_netif_attach()
              │      └ 创建 lwIP netif 并挂载到 IP 协议栈
              │
              ├─ 6. [mod_network 注册 ETHERNET_EVENT/IP_EVENT 事件处理器]
              │
              └─ 7. eth_hw_start() → esp_eth_start(eth_handle)
                     └ 启动以太网状态机 + 自动 DHCP
```

> 设计为两阶段初始化: `eth_hw_init()` 创建硬件 → mod_network 注册事件处理器 → `eth_hw_start()` 启动以太网。避免事件在处理器注册前丢失。

### 6.3.2 esp_eth 配置参数 (ESP-IDF v6.0.1)

| 参数 | 值 | 说明 |
|:---|:---|:---|
| `phy_addr` | `0x01` | PHY 地址 (PHYAD0 拉高, 经 SMI 扫描确认) |
| `reset_gpio_num` | `-1` (禁用) | 当前硬件 GPIO5 未连接, PHY 使用 POR |
| `smi_gpio.mdc_num` | `GPIO_NUM_23` | SMI 管理时钟 (v6.0.1 新 API, 替代废弃的 `mdc_gpio_num`) |
| `smi_gpio.mdio_num` | `GPIO_NUM_18` | SMI 管理数据 (v6.0.1 新 API, 替代废弃的 `mdio_gpio_num`) |
| `clock_config.rmii.clock_mode` | `EMAC_CLK_EXT_IN` | 外部时钟输入 (v6.0.1 命名, 旧版为 `EMAC_CLK_OUT`) |
| `clock_config.rmii.clock_gpio` | `0` (GPIO 0) | REF_CLK 输入引脚 |
| `mdc_freq_hz` | `250000` | MDC 频率 250kHz, 适配弱上拉 (内部 45kΩ) |
| MAC 地址 | `28:56:2f:8f:82:88` | 通过 `ETH_CMD_S_MAC_ADDR` 写入 |
| PHY 驱动 | `esp_eth_phy_new_lan87xx()` | 组件 `espressif/lan87xx` (v6.0.1 移出内核) |

### 6.3.3 组件依赖 (idf_component.yml)

```yaml
dependencies:
  idf:
    version: '>=4.1.0'
  espressif/lan87xx: '*'
```

### 6.3.4 DHCP 事件处理

IP 获取流程依赖 lwIP 的 `IP_EVENT_ETH_GOT_IP` 事件通知：

```c
static void eth_event_handler(void *arg, esp_event_base_t event_base,
                              int32_t event_id, void *event_data)
{
    switch (event_id) {
    case ETHERNET_EVENT_CONNECTED:
        // 网线插入, 记录链路 UP
        send_link_event(UBCP_EVT_LINK_UP, 0);
        break;
    case ETHERNET_EVENT_DISCONNECTED:
        // 网线拔出, 标记网络断裂
        send_link_event(UBCP_EVT_LINK_DOWN, 0);
        break;
    }
}

static void ip_event_handler(void *arg, esp_event_base_t event_base,
                             int32_t event_id, void *event_data)
{
    ip_event_got_ip_t *evt = (ip_event_got_ip_t *)event_data;
    if (event_id == IP_EVENT_ETH_GOT_IP) {
        record_ip_info(&evt->ip_info);
        send_link_event(UBCP_EVT_IP_ACQUIRED, &evt->ip_info.ip);
    } else if (event_id == IP_EVENT_ETH_LOST_IP) {
        send_link_event(UBCP_EVT_IP_LOST, 0);
    }
}
```

---

## 6.4 模块划分与源文件

### 6.4.1 文件清单

| 文件 | 说明 | 命令码范围 |
|:---|:---|:---|
| `modules/mod_network.h` | 网络基础配置 (NET_CONFIG, NET_STATUS, NET_DNS, LINK_EVENT) | 0x40-0x4F |
| `modules/mod_network.c` | 网络配置实现 (~350 行) | |
| `modules/mod_tcp.h` | TCP Server/Client 实现声明 | 0x50-0x5F |
| `modules/mod_tcp.c` | TCP 协议实现 (~800 行) | |
| `modules/mod_udp.h` | UDP Server/Client 实现声明 | 0x60-0x6F |
| `modules/mod_udp.c` | UDP 协议实现 (~450 行) | |
| `modules/mod_ws.h` | WebSocket Server/Client 实现声明 | 0x70-0x7F |
| `modules/mod_ws.c` | WebSocket 协议实现 (~600 行) | |
| `core/eth_init.h` | LAN8720 初始化接口 | — |
| `core/eth_init.c` | LAN8720 PHY 复位 + esp_eth 驱动安装 (~200 行) | — |

### 6.4.2 模块注册 (main.c)

```c
// 以太网初始化 (必须在模块 init 之前完成，确保 netif 可用)
eth_hw_init();

// 注册网络模块
msg_bus_register_module(&hex_mod_network);   // 0x40-0x4F
msg_bus_register_module(&hex_mod_tcp);       // 0x50-0x5F
msg_bus_register_module(&hex_mod_udp);       // 0x60-0x6F
msg_bus_register_module(&hex_mod_ws);        // 0x70-0x7F
```

---

## 6.5 网络基础配置模块 (mod_network, 0x40-0x4F)

### 6.5.1 命令实现清单

| 命令码 | 名称 | 方向 | 状态 |
|:---|:---|:---|:---|
| `0x40` | NET_CONFIG | 请求-响应 | 设计阶段 |
| `0x41` | NET_STATUS | 请求-响应 | 设计阶段 |
| `0x42` | NET_DNS | 请求-响应 | 设计阶段 |
| `0x43` | NET_LINK_EVENT | 事件上报 | 设计阶段 |
| `0x44` | NET_LIST_CONNS | 请求-响应 | 设计阶段 |

### 6.5.2 NET_CONFIG (0x40) — 网络配置

**请求**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | InterfaceIndex | u8 | 固定为 `0x00` (ETH0) |
| 1 | ConfigType | u8 | `0x00`=DHCP, `0x01`=静态 IP |
| 2-5 | IpAddr | u32 | 仅在 ConfigType=0x01 时有效 |
| 6-9 | SubnetMask | u32 | 仅在 ConfigType=0x01 时有效 |
| 10-13 | Gateway | u32 | 仅在 ConfigType=0x01 时有效 |
| 14-17 | DNS1 | u32 | 仅在 ConfigType=0x01 时有效 |
| 18-21 | DNS2 | u32 | 仅在 ConfigType=0x01 时有效 |

**响应**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | `0x00`=成功, `0x06`=不支持 |
| 1-4 | ActualIP | u32 | 实际 IP (DHCP 模式时), 或配置的静态 IP |
| 5-8 | ActualMask | u32 | 实际子网掩码 |
| 9-12 | ActualGW | u32 | 实际网关 |
| 13-16 | ActualDNS | u32 | 实际 DNS 服务器 |

**实现要点**:
- 静态 IP 模式: 通过 `esp_netif_dhcpc_stop()` 停止 DHCP, 调用 `esp_netif_set_ip_info()` 设置静态 IP, 通过 `esp_netif_dns_info_t` 配置 DNS
- DHCP 模式: `esp_netif_dhcpc_start()` 重新启用 DHCP
- 配置写入 NVS, 掉电/复位不丢失
- 首次未获取到 IP 时 (DHCP 进行中), `ActualIP` 返回 `0x00000000`

### 6.5.3 NET_STATUS (0x41) — 网络状态查询

**请求**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | InterfaceIndex | u8 | `0x00`=ETH0, `0xFF`=所有接口 |

**响应**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | `0x00`=成功 |
| 1 | IntfCount | u8 | 接口数量 (N), 当前固定 `0x01` |
| 2-18 | Interface[0] | u8[17] | 以太网接口状态 (17 字节) |

**每个接口的状态结构 (17 字节)**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | IntfIndex | u8 | `0x00`=ETH0 |
| 1 | LinkState | u8 | `0x00`=Down, `0x01`=Up |
| 2 | ConnState | u8 | `0x00`=未连接, `0x01`=已连接, `0x02`=获取IP中 |
| 3-6 | IpAddr | u32 | IP 地址 (big-endian) |
| 7-10 | SubnetMask | u32 | 子网掩码 (big-endian) |
| 11-16 | MacAddr | u8[6] | MAC 地址 |

**实现要点**:
- `LinkState` 通过 `esp_eth_ioctl(eth_handle, ETH_CMD_G_PHY_ADDR, ...)` 读取 PHY 链路状态
- `ConnState` 通过 `esp_netif_is_netif_up()` 和 `esp_netif_get_ip_info()` 检查 IP 是否有效
- MAC 地址通过 `esp_read_mac(mac_addr, ESP_MAC_ETH)`
- `LinkState` + `ConnState` = `0x00`+`0x00` 表示网线未插入, `0x01`+`0x02` 表示链路 UP 但 DHCP 未完成

### 6.5.4 NET_DNS (0x42) — DNS 域名解析

**请求**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | NameLen | u8 | 域名长度 (L), 最大 253 |
| 1...(1+L-1) | Hostname | str(L) | 域名字符串 |

**响应**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | `0x00`=成功, `0x46`=DNS失败, `0x47`=无IP |
| 1 | AddrCount | u8 | 解析到的 IP 地址数量 (N, 最多 4) |
| 2...(2+4N-1) | Addresses | u32[N] | IP 地址列表 |

**实现要点**:
- 使用 lwIP `dns_gethostbyname()` API
- 需要 IP 地址已获取, 否则返回 `ERR_NET_NO_IP (0x47)`
- 阻塞等待 DNS 解析结果, 超时 5 秒后返回 `ERR_NET_DNS_FAIL (0x46)`
- 使用 FreeRTOS 信号量实现非阻塞等待

### 6.5.5 NET_LINK_EVENT (0x43) — 链路状态事件上报

当网线插拔或 DHCP 地址变化时, 由硬件事件回调触发 UBCP 事件帧上报。

**上报载荷**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | IntfIndex | u8 | `0x00`=ETH0 |
| 1 | EventType | u8 | 事件类型 (见下表) |
| 2-5 | IpAddr | u32 | 事件关联 IP (没有时为 `0x00000000`) |

**EventType 定义**:

| 值 | 名称 | 触发条件 |
|:---|:---|:---|
| `0x00` | LINK_DOWN | `ETHERNET_EVENT_DISCONNECTED` 回调 |
| `0x01` | LINK_UP | `ETHERNET_EVENT_CONNECTED` 回调 |
| `0x02` | IP_ACQUIRED | `IP_EVENT_ETH_GOT_IP` 回调 |
| `0x03` | IP_LOST | `IP_EVENT_ETH_LOST_IP` 回调 |
| `0x04` | IP_CHANGED | DHCP 续期后 IP 与之前不同 |

**实现要点**:
- 事件回调在 Event 任务上下文中执行
- 通过 `msg_bus_send_event(CMD_NET_LINK_EVENT, payload)` 构建事件帧
- 链路状态变更时同时更新 `ConnState` 内部缓存, 供 `NET_STATUS (0x41)` 查询
- 上电初始化完成后, 自动发送首次 LINK_UP / LINK_DOWN 状态 (取决于网线是否插入)

### 6.5.6 NET_LIST_CONNS (0x44) — 查询所有活跃网络连接

**请求**: 无载荷 (空请求体)

**响应**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | Status | u8 | `0x00`=成功 |
| 1 | ConnCount | u8 | 连接总数 (N) |
| 2...(2+N*10-1) | Entries | — | N 个连接条目 (每个 10 字节) |

**每个连接条目 (10 字节)**:

| 偏移 | 字段 | 类型 | 说明 |
|:---|:---|:---|:---|
| 0 | ConnType | u8 | `0x00`=TCP_SERVER, `0x01`=TCP_CONN, `0x02`=UDP_SERVER, `0x03`=UDP_CLIENT, `0x04`=WS_SERVER, `0x05`=WS_CONN |
| 1-2 | Handle | u16 | 连接/服务器句柄 |
| 3-4 | ParentHandle | u16 | 所属服务器句柄 |
| 5-6 | LocalPort | u16 | 本地端口号 |
| 7-10 | RemoteIP | u32 | 对端 IP (Server 模式为 `0x00000000`) |

**实现要点**:
- 遍历 `mod_tcp` + `mod_udp` + `mod_ws` 各自的连接管理表
- 通过 msg_bus 跨模块查询 API 或直接调用各模块的导出查询函数
- 各模块需要导出 `_get_conn_list()` 类函数供 `NET_LIST_CONNS` 汇总
- 单个条目 10 字节, 最坏情况 (4 TCP Server × 4 连接 + 4 UDP + 8 UDP Client + 4 WS Server × 5 连接 + 其他) ≈ 60 条目 = 600 字节载荷, 在 UBCP 最大帧 1500 字节限制内

---

## 6.6 TCP 模块 (mod_tcp, 0x50-0x5F)

### 6.6.1 架构设计

TCP 模块基于 lwIP Socket API 实现, 采用 **select() 多路复用事件循环** 统一管理所有 TCP 连接。

```
┌─────────────────────────────────────────────────────────┐
│                    tcp_event_task                        │
│  select() 监听所有 socket_fd → 可读/可写/异常事件          │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │ server_sock │ │ client_sock#1│ │ client_sock#2│ ... │
│  │ (监听 accept)│ │ (recv 数据)  │ │ (recv 数据)  │     │
│  └──────┬──────┘ └──────┬───────┘ └──────┬───────┘     │
│         │               │                │              │
│         v               v                v              │
│   接受新连接        读取数据           读取数据            │
│   分配 ClientHandle 填充 ConnHandle    填充 ConnHandle    │
│   发送 TCP_ACCEPT   发送 TCP_RECV      发送 TCP_RECV     │
│   事件帧            事件帧              事件帧             │
└─────────────────────────────────────────────────────────┘
```

### 6.6.2 句柄管理

| 范围 | 用途 | 说明 |
|:---|:---|:---|
| `0x0001-0x7FFF` | Server 句柄 | 设备分配, 自增, 循环使用 |
| `0x8001-0xFFFE` | Client/连接 句柄 | 设备分配, 自增, 循环使用 |
| `0x0000` | 无效句柄 | 表示错误 |
| `0x8000` | 广播句柄 | 发送到 Server 所有已连接 Client |
| `0xFFFF` | 保留 | — |

**句柄分配算法**:
```c
static uint16_t s_next_server_handle = 0x0001;
static uint16_t s_next_client_handle = 0x8001;

uint16_t tcp_alloc_server_handle(void) {
    uint16_t h = s_next_server_handle++;
    if (s_next_server_handle >= 0x8000) s_next_server_handle = 0x0001;
    return h;
}
```

### 6.6.3 内部数据结构

```c
#define TCP_MAX_SERVERS   4
#define TCP_MAX_CONNS    16

typedef struct {
    uint16_t server_handle;
    int      listen_fd;
    uint16_t port;
    uint8_t  max_conn;
    uint8_t  accept_mode;   // 0=manual, 1=auto
    uint8_t  keepalive_sec;
    bool     active;
} tcp_server_t;

typedef struct {
    uint16_t conn_handle;
    uint16_t server_handle;  // 0=client模式
    int      socket_fd;
    uint32_t remote_ip;
    uint16_t remote_port;
    uint32_t local_ip;
    uint16_t local_port;
    uint8_t  keepalive_sec;
    bool     is_server_child; // true=accept产生, false=client connect产生
    bool     active;
    uint32_t connect_time_sec; // 连接建立时刻 (boot秒数)
    uint32_t tx_bytes;         // 累计发送字节数
    uint32_t rx_bytes;         // 累计接收字节数
    uint8_t  conn_state;       // 0=ESTABLISHED, 1=CLOSING, 2=CLOSED
} tcp_conn_t;
```

### 6.6.4 命令实现清单

| 命令码 | 名称 | 方向 | 状态 |
|:---|:---|:---|:---|
| `0x50` | TCP_SERVER_OPEN | 请求-响应 | 设计阶段 |
| `0x51` | TCP_SERVER_CLOSE | 请求-响应 | 设计阶段 |
| `0x52` | TCP_CLIENT_CONNECT | 请求-响应 | 设计阶段 |
| `0x53` | TCP_CLIENT_DISCONNECT | 请求-响应 | 设计阶段 |
| `0x54` | TCP_SEND | 请求-响应 | 设计阶段 |
| `0x55` | TCP_RECV | 事件上报 | 设计阶段 |
| `0x56` | TCP_ACCEPT | 事件上报/请求 | 设计阶段 |
| `0x57` | TCP_CLOSE | 请求-响应 | 设计阶段 |
| `0x58` | TCP_DISCONNECT_EVENT | 事件上报 | 设计阶段 |
| `0x59` | TCP_LIST_CLIENTS | 请求-响应 | 设计阶段 |
| `0x5A` | TCP_KICK_CLIENT | 请求-响应 | 设计阶段 |
| `0x5B` | TCP_CONN_STATUS | 请求-响应 | 设计阶段 |

### 6.6.5 TCP_SERVER_OPEN (0x50) — 创建 TCP Server

**实现流程**:
```
1. 句柄分配: server_handle = tcp_alloc_server_handle()
2. 创建 Socket: socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
3. 设置 SO_REUSEADDR
4. bind() 到指定端口
5. listen(sockfd, max_conn)
6. 注册 server_sock 到 select() fd_set
7. 返回实际绑定端口 (0 端口时由 OS 分配)
```

**错误路径**:
| 场景 | 错误码 |
|:---|:---|
| 已达最大 Server 数 (4) | `ERR_NET_MAX_CONN (0x48)` |
| `bind()` 失败 (端口被占用) | `ERR_NET_PORT_IN_USE (0x45)` |
| 网卡未获取 IP | `ERR_NET_NO_IP (0x47)` |

### 6.6.6 TCP_SERVER_CLOSE (0x51) — 关闭 TCP Server

**实现流程**:
```
1. 查表找到 server_handle 对应的 server 结构体
2. ForceClose=0: 遍历所有 is_server_child 的 conn, shutdown(SHUT_RD)
             等待客户端主动断开 (或超时 5s 后 force)
3. ForceClose=1: 遍历所有 is_server_child 的 conn, close(socket_fd)
4. close(listen_fd), 清理 Server 结构体
5. 对每个被关闭的子连接, 发送 TCP_DISCONNECT_EVENT (0x58)
```

### 6.6.7 TCP_CLIENT_CONNECT (0x52) — TCP Client 连接

**实现流程**:
```
1. 创建 Socket: socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
2. 设置为非阻塞: fcntl(sockfd, F_SETFL, O_NONBLOCK)
3. connect() — 非阻塞调用
4. 将 socket_fd 加入 select() 监听写入事件
5. select() 超时检测: TimeoutSec 默认 5s
     - 连接成功: 分配 conn_handle, 记录 connect_time_sec, 返回本地 IP/Port
     - 连接失败: close(sockfd), 返回 ERR_NET_CONN_REFUSED (0x41)
     - 超时: close(sockfd), 返回 ERR_NET_TIMEOUT (0x42)
6. 如果 KeepAlive != 0, 设置 SO_KEEPALIVE + 自定义 keepalive 间隔
```

### 6.6.8 TCP_SEND (0x54) — 发送 TCP 数据

**实现流程**:
```
1. 查表找到 conn_handle → socket_fd
2. send(sockfd, data, len, MSG_DONTWAIT)
3. 返回值 ≤ 0: 检查 errno
     - ENOTCONN / EPIPE: 发送 TCP_DISCONNECT_EVENT, 返回 ERR_NET_DISCONNECTED (0x40)
     - EAGAIN / EWOULDBLOCK: 返回 ERR_NET_BUFFER_FULL (0x44)
4. 成功: conn->tx_bytes += ActualLen, 返回 ActualLen
```

### 6.6.9 TCP_RECV (0x55) — 接收数据事件

由 `tcp_event_task` 中 `select()` 检测到 `socket_fd` 可读时触发:
```
1. recv(sockfd, buf, sizeof(buf), MSG_DONTWAIT)
2. 返回值 == 0: 远端正常关闭 → 发送 TCP_DISCONNECT_EVENT
   返回值 < 0, errno!=EAGAIN: 连接错误 → 发送 TCP_DISCONNECT_EVENT
3. 构建 TCP_RECV 事件帧: ConnHandle + DataLen + Data
4. msg_bus_send_event(CMD_TCP_RECV, payload)
```

### 6.6.10 TCP_ACCEPT (0x56) — 新客户端连接事件

由 `tcp_event_task` 中 `select()` 检测到 `listen_fd` 可读时触发:
```
1. client_fd = accept(listen_fd, &addr, &addr_len)
2. 分配 conn_handle = tcp_alloc_client_handle()
3. 注册新连接结构体 (server_handle 指向父 Server)
4. 记录 connect_time_sec = esp_timer_get_time() / 1000000
5. 将 client_fd 加入 select() fd_set
6. AcceptMode == AUTO (0x01): 直接构建 TCP_ACCEPT 事件帧上报
7. AcceptMode == MANUAL (0x00): 构建帧上报, 等待主机通过 TCP_ACCEPT 命令确认

### 6.6.11 TCP_CLOSE (0x57) — 通用关闭

统一接口, 通过 `HandleType` 区分关闭类型:
- `HandleType=0`: 关闭单个连接 (等价 TCP_CLIENT_DISCONNECT)
- `HandleType=1`: 关闭 Server (等价 TCP_SERVER_CLOSE)
- `ForceFlag=1`: 强制关闭 (RST)

### 6.6.12 TCP_DISCONNECT_EVENT (0x58) — 断开事件

以下场景自动上报:
1. 远端发送 FIN (socket 可读, recv 返回 0)
2. 远端发送 RST (socket 异常, recv 返回 -1)
3. send() 返回 ENOTCONN / EPIPE
4. select() 超时检测 (长时间无数据交互)

### 6.6.13 TCP_LIST_CLIENTS (0x59) — 查询已连接客户端

**请求**: ServerHandle (u16)

**实现流程**:
```
1. 查表找到 server_handle 对应的 tcp_server_t
2. 遍历 tcp_conn_t[] 数组, 筛选 server_handle 匹配且 active=true 的条目
3. 对每个匹配条目, 构造客户端信息 (10 字节):
     ClientHandle + ClientIP + ClientPort + ConnectTime(u16)
4. ConnectTime = esp_timer_get_time()/1000000 - conn->connect_time_sec
5. 组装响应: Status + ClientCount + ClientEntries[]
```

### 6.6.14 TCP_KICK_CLIENT (0x5A) — 强制断开指定客户端

**请求**: ClientHandle (u16) + ForceFlag (u8)

**实现流程**:
```
1. 查表找到 client_handle 对应的 tcp_conn_t
2. ForceFlag=0: shutdown(sockfd, SHUT_RDWR), 等待对端 FIN, 超时 3s 后 close()
3. ForceFlag=1: struct linger l={.l_onoff=1, .l_linger=0};
                  setsockopt(SO_LINGER); close(sockfd);  // 发送 RST
4. 清理 conn 结构体, 标记 active=false
5. 自动发送 TCP_DISCONNECT_EVENT(0x58) 事件帧通知主机
6. 返回状态
```

**错误路径**:
| 场景 | 错误码 |
|:---|:---|
| ClientHandle 无效或已断开 | `ERR_NET_HANDLE_INVALID (0x43)` |

### 6.6.15 TCP_CONN_STATUS (0x5B) — 查询单个连接状态

**请求**: ConnHandle (u16)

**实现流程**:
```
1. 查表找到 conn_handle 对应的 tcp_conn_t
2. 组装响应: ConnState + TxBytes(u32) + RxBytes(u32) + RemoteIP + RemotePort + LocalPort + ConnectTime(u32)
3. ConnectTime = esp_timer_get_time()/1000000 - conn->connect_time_sec
4. 返回状态
```

---

## 6.7 UDP 模块 (mod_udp, 0x60-0x6F)

### 6.7.1 命令实现清单

| 命令码 | 名称 | 方向 | 状态 |
|:---|:---|:---|:---|
| `0x60` | UDP_SERVER_OPEN | 请求-响应 | 设计阶段 |
| `0x61` | UDP_SERVER_CLOSE | 请求-响应 | 设计阶段 |
| `0x62` | UDP_CLIENT_CREATE | 请求-响应 | 设计阶段 |
| `0x63` | UDP_CLIENT_DELETE | 请求-响应 | 设计阶段 |
| `0x64` | UDP_SERVER_SEND | 请求-响应 | 设计阶段 |
| `0x65` | UDP_RECV | 事件上报 | 设计阶段 |
| `0x66` | UDP_CLIENT_SEND | 请求-响应 | 设计阶段 |

### 6.7.2 内部数据结构

```c
#define UDP_MAX_SERVERS   4
#define UDP_MAX_CLIENTS   8

typedef struct {
    uint16_t handle;
    int      socket_fd;
    uint16_t port;
    bool     broadcast_en;
    uint32_t multicast_addr;  // 0 = 不使用多播
    bool     active;
} udp_server_t;

typedef struct {
    uint16_t handle;
    int      socket_fd;
    uint32_t default_dest_ip;
    uint16_t default_dest_port;
    uint16_t local_port;
    bool     active;
} udp_client_t;
```

### 6.7.3 UDP_SERVER_OPEN (0x60) — 创建 UDP Server

与 TCP 不同, UDP Server 创建后就持续监听, 收到数据即通过 `UDP_RECV (0x65)` 事件帧上报。多播模式下需额外调用 `setsockopt(IP_ADD_MEMBERSHIP)`。

### 6.7.4 UDP_CLIENT_CREATE (0x62) — 创建 UDP Client

Client 创建时保存 `DefaultDestIP` + `DefaultDestPort`, 后续 `UDP_CLIENT_SEND (0x66)` 可通过 `AddrMode=0x00` 省去地址字段。

### 6.7.5 UDP_SERVER_SEND (0x64) / UDP_CLIENT_SEND (0x66)

两者均通过 `sendto()` 发送数据。区别:
- `UDP_SERVER_SEND`: 必须在载荷中指定 DestIP 和 DestPort
- `UDP_CLIENT_SEND`: 支持 `AddrMode=0x00` (使用默认地址) 和 `AddrMode=0x01` (使用指定地址)

---

## 6.8 WebSocket 模块 (mod_ws, 0x70-0x7F)

### 6.8.1 架构设计

WebSocket 模块基于 lwIP TCP Socket 之上实现 RFC 6455 WebSocket 协议栈, 包括:

```
┌────────────────────────────────────────────────────┐
│               UBCP WS 命令处理层                      │
│  WS_SERVER_OPEN / WS_CLIENT_CONNECT / WS_SEND ...   │
├────────────────────────────────────────────────────┤
│               WebSocket 协议编解码                    │
│  - 握手帧 (HTTP Upgrade: websocket)                  │
│  - 数据帧 (opcode: TEXT / BINARY / PING / PONG)      │
│  - 掩码编解码 (客户端帧必须掩码, 服务器帧不掩码)        │
│  - 关闭帧 (Close Code + Reason)                      │
├────────────────────────────────────────────────────┤
│               lwIP TCP Socket                        │
│  (复用 TCP 模块的 select() 管理, 或独立 select loop)  │
└────────────────────────────────────────────────────┘
```

### 6.8.2 WebSocket 帧格式 (RFC 6455 Base Framing)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |           (16/64)             |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+-------------------------------+
|     Masking-key (0 or 4 bytes)  |  Payload Data ...           |
+---------------------------------+------------------------------+
```

**WebSocket opcode 定义**:

| Opcode | 类型 | 说明 |
|:---|:---|:---|
| `0x01` | Text | 文本帧 |
| `0x02` | Binary | 二进制帧 |
| `0x08` | Close | 关闭帧 |
| `0x09` | Ping | 心跳请求 |
| `0x0A` | Pong | 心跳应答 |

### 6.8.3 HTTP Upgrade 握手实现

```
1. Client 连接后, TCP 层收到 HTTP 请求:
   GET /path HTTP/1.1
   Host: xxx
   Upgrade: websocket
   Connection: Upgrade
   Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
   Sec-WebSocket-Version: 13

2. WebSocket 模块检测 Upgrade 头部

3. 构建响应:
   HTTP/1.1 101 Switching Protocols
   Upgrade: websocket
   Connection: Upgrade
   Sec-WebSocket-Accept: <base64(sha1(key + GUID))>

4. 握手完成后, 帧解析器接管 TCP 字节流

5. 发送 WS_ACCEPT (0x76) 事件帧上报新连接
```

### 6.8.4 命令实现清单

| 命令码 | 名称 | 方向 | 状态 |
|:---|:---|:---|:---|
| `0x70` | WS_SERVER_OPEN | 请求-响应 | 设计阶段 |
| `0x71` | WS_SERVER_CLOSE | 请求-响应 | 设计阶段 |
| `0x72` | WS_CLIENT_CONNECT | 请求-响应 | 设计阶段 |
| `0x73` | WS_CLIENT_DISCONNECT | 请求-响应 | 设计阶段 |
| `0x74` | WS_SEND | 请求-响应 | 设计阶段 |
| `0x75` | WS_RECV | 事件上报 | 设计阶段 |
| `0x76` | WS_ACCEPT | 事件上报 | 设计阶段 |
| `0x77` | WS_DISCONNECT_EVENT | 事件上报 | 设计阶段 |
| `0x78` | WS_LIST_CLIENTS | 请求-响应 | 设计阶段 |
| `0x79` | WS_KICK_CLIENT | 请求-响应 | 设计阶段 |

### 6.8.5 WS_SEND (0x74) 帧编码流程

```
输入: ConnHandle, MsgType, DataLen, Data
输出: 通过 TCP Socket 发送编码后的 WebSocket 帧

编码流程:
1. 构建 FIN=1, Opcode=MsgType
2. 编码 Payload Length (7-bit / 16-bit / 64-bit)
3. 服务器→客户端: MASK=0, 直接写入 Payload Data
4. 写入 TCP Socket
```

### 6.8.6 WS_RECV (0x75) 帧解码流程

```
从 TCP Socket 接收到字节流后, 在线解码:
1. 解析 FIN + Opcode
2. 解析 Payload Length
3. 客户端→服务器: MASK=1, 读取 4 字节 Masking-Key
4. 掩码解码: payload[i] ^= masking_key[i % 4]
5. 组装 UBCP 事件帧上报
6. 如果是 Close 帧 (Opcode=0x08): 发送 WS_DISCONNECT_EVENT (0x77)
```

### 6.8.7 WS 连接结构体

```c
#define WS_MAX_SERVERS   4
#define WS_MAX_CONNS    16

typedef struct {
    uint16_t conn_handle;
    uint16_t server_handle;
    int      socket_fd;
    uint32_t client_ip;
    uint16_t client_port;
    uint8_t  subproto_index;
    uint8_t  path_len;
    char     path[64];
    uint32_t connect_time_sec; // 连接建立时刻 (boot秒数)
    bool     active;
} ws_conn_t;
```

### 6.8.8 WS_LIST_CLIENTS (0x78) — 查询已连接客户端

**请求**: ServerHandle (u16)

**实现流程**:
```
1. 查表找到 server_handle 对应的 WS 服务器
2. 遍历 ws_conn_t[] 数组, 筛选 server_handle 匹配且 active=true 的条目
3. 对每个匹配条目, 构造客户端信息 (12 字节):
     ClientHandle + ClientIP + ClientPort + SubProtoIndex + PathLen + ConnectTime(u16)
4. ConnectTime = esp_timer_get_time()/1000000 - conn->connect_time_sec
5. 组装响应: Status + ClientCount + ClientEntries[]
```

### 6.8.9 WS_KICK_CLIENT (0x79) — 强制断开指定客户端

**请求**: ClientHandle (u16) + ForceFlag (u8)

**实现流程**:
```
1. 查表找到 client_handle 对应的 ws_conn_t
2. ForceFlag=0: 构建 WS Close 帧 (CloseCode=1000), 发送到 TCP Socket
                 等待对端 Close 帧或超时 3s
3. ForceFlag=1: 直接 shutdown(sockfd, SHUT_RDWR), close(sockfd)
4. 清理 conn 结构体, 标记 active=false
5. 自动发送 WS_DISCONNECT_EVENT(0x77) 事件帧通知主机
6. 返回状态
```

**错误路径**:
| 场景 | 错误码 |
|:---|:---|
| ClientHandle 无效或已断开 | `ERR_NET_HANDLE_INVALID (0x43)` |

---

## 6.9 FreeRTOS 任务分配

| 任务名称 | 栈大小 | 优先级 | 所属模块 | 职责 |
|:---|:---|:---|:---|:---|
| `mcp_recv` | 4096 | 10 | MCP 传输层 | UART1 接收 → 帧解析 → 分发 |
| `eth_event` | 3072 | 8 | 以太网驱动 | ESP-IDF 内部 Event 任务 (处理 ETHERNET/IP 事件回调) |
| `tcp_select` | 6144 | 7 | mod_tcp | select() 多路复用 TCP 连接事件循环 |
| `udp_select` | 4096 | 7 | mod_udp | select() 多路复用 UDP 接收事件循环 |
| `ws_task` | 5120 | 7 | mod_ws | WebSocket 握手 + 帧解析任务 |
| `dns_task` | 3072 | 6 | mod_network | DNS 解析阻塞任务 (按需运行) |

> **优先级说明**: 网络 I/O 任务优先级低于 MCP 接收任务, 确保 UBCP 协议帧不被网络延迟阻塞。
> TCP 和 UDP 的 select() 使用独立的 FreeRTOS 任务, 各自管理事件循环, 互不干扰。

---

## 6.10 内存预算

| 项目 | 大小 | 说明 |
|:---|:---|:---|
| lwIP 协议栈 | ~40 KB | ESP-IDF 默认配置 (TCP_MSS=1460, TCP_SND_BUF=5744, TCP_WND=5744) |
| lwIP PBUF 池 | ~16 KB | 默认 16 个 PBUF (MEMP_NUM_PBUF=16) |
| TCP Socket 缓冲区 | ~44 KB | 4 路 Server × 4 连接 × SND_BUF(5744) + WND(5744) |
| UDP Socket 缓冲区 | ~16 KB | 4 Server + 8 Client × 默认 1024 B |
| WS 帧缓冲区 | ~8 KB | 最大帧 4096 B + 解码缓冲区 |
| select() fd_set | ~1 KB | FD_SETSIZE 默认 64 |
| 连接管理表 | ~3 KB | tcp_server_t[] + tcp_conn_t[] (含新增 tx/rx/connect_time 字段) + udp_server_t[] + udp_client_t[] + ws_conn_t[] |
| **总计** | ~128 KB | ESP32 可用堆 ~300KB, 留有充足余量 |

> **注意**: TCP Socket 缓冲区总量依赖同时活跃的连接数 (4×4=16), 实际使用中可通过 `TCP_MAX_CONNS` 调整。

---

## 6.11 错误处理策略

### 6.11.1 网络断开时的模块行为

| 场景 | 行为 |
|:---|:---|
| 网线拔出 | `ETHERNET_EVENT_DISCONNECTED` → 发送 `NET_LINK_EVENT(LINK_DOWN)` |
| DHCP 租约过期 | `IP_EVENT_ETH_LOST_IP` → 发送 `NET_LINK_EVENT(IP_LOST)` |
| 网线拔出时 TCP 连接 | select() 检测 socket 错误 → 发送 `TCP_DISCONNECT_EVENT` 逐个上报 |
| 网线拔出时 UDP 接收 | recvfrom() 返回 -1 → 静默等待链路恢复 |
| 链路恢复 | `ETHERNET_EVENT_CONNECTED` → `IP_EVENT_ETH_GOT_IP` → 正常恢复 |

### 6.11.2 句柄生命周期

```
TCP_ACCEPT / TCP_CLIENT_CONNECT 创建句柄
      │
      ▼
TCP_SEND / TCP_RECV 活动状态
      │
      ├─── TCP_CLIENT_DISCONNECT / TCP_CLOSE / TCP_SERVER_CLOSE
      │    主机主动关闭, 释放句柄
      │
      ├─── TCP_DISCONNECT_EVENT (远端断开)
      │    远端主动断开, 设备自动释放句柄并上报
      │
      └─── select() 检测到 socket 异常 (超时 / 错误)
           设备自动关闭 socket, 上报 TCP_DISCONNECT_EVENT, 释放句柄
```

---

## 6.12 源文件

| 文件 | 说明 |
|:---|:---|
| `core/eth_init.h` | LAN8720 初始化接口声明 |
| `core/eth_init.c` | PHY 复位时序 + esp_eth 驱动安装 (~200 行) |
| `modules/mod_network.h` | 网络配置模块接口声明 |
| `modules/mod_network.c` | NET_CONFIG / NET_STATUS / NET_DNS / NET_LINK_EVENT / NET_LIST_CONNS (~450 行) |
| `modules/mod_tcp.h` | TCP 模块接口声明 | |
| `modules/mod_tcp.c` | TCP Server/Client + select 事件循环 + LIST_CLIENTS / KICK_CLIENT / CONN_STATUS (~950 行) |
| `modules/mod_udp.h` | UDP 模块接口声明 | |
| `modules/mod_udp.c` | UDP Server/Client + select 事件循环 (~450 行) |
| `modules/mod_ws.h` | WebSocket 模块接口声明 | |
| `modules/mod_ws.c` | WebSocket 握手 + 帧编解码 + LIST_CLIENTS / KICK_CLIENT (~700 行) |
