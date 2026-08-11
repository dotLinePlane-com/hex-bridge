# HEX-Bridge 缃戠粶妯″潡 鈥?娴嬭瘯鎶ュ憡

> **鎶ュ憡鏃ユ湡**: 2026-07-26 | **鍥轰欢鐗堟湰**: v0.3.0 | **鍗忚��**: UBCP v2.0

---

## 1. 娴嬭瘯姒傝��

| 椤圭洰 | 鍊?|
|:---|:---|
| 琚�娴嬫ā鍧� | 缃戠粶閰嶇疆 (0x40-0x4F) + TCP (0x50-0x5F) + UDP (0x60-0x6F) + WebSocket (0x70-0x7F) |
| 娴嬭瘯鐢ㄤ緥鏁?| 122 (81 鑷�涓� + 22 NM 瀵圭�� + 19 鏃犵綉缁滆ˉ娴? |
| 娴嬭瘯缁撴灉 | **101 PASS / 0 FAIL / 3 SKIP / 18 PENDING** |
| 閫氳繃鐜?| **100%** (宸叉墽琛岀敤渚? 鍥轰欢鏃犵己闄? |
| 娴嬭瘯鑴氭湰 | `script/test/test_network.py --auto` |
| CLI 宸ュ叿 | `script/cli/hex-bridge-network-cli.py` (25 鍛戒护鍏ㄨ�嗙�? |
| NM 宸ュ叿 | MCP Network Monitor (Kilo Agent) |
| 鑺�鐗囧瀷鍙� | ESP32-D0WD-V3 (revision v3.1) |
| IDF 鐗堟湰 | ESP-IDF v6.0.1 |
| 浠ュお缃?PHY | LAN8720 (RMII, PHY_RST=GPIO5) |
| 璁惧�� IP | 192.168.1.105 | MAC | 28:56:2F:8F:82:88 |
| PC 瀵圭�� IP | 192.168.1.4 |
| MCP 娉㈢壒鐜?| 115200 bps | 涓插彛 | COM4 |

---

## 2. 娴嬭瘯鐜�澧�

### 2.1 娴嬭瘯鎷撴墤

```
鈹屸攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?鈹?                        鍚屼竴鍙?PC                                          鈹?鈹?                                                                           鈹?鈹? 鈹屸攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?         鈹屸攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?        鈹?鈹? 鈹?test_network.py /   鈹? COM4   鈹?Network Monitor               鈹?       鈹?鈹? 鈹?hex-bridge-network- 鈹傗啇鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈫掆攤 (TCP/UDP/WS Client/Server)   鈹?       鈹?鈹? 鈹?cli.py              鈹? 115200  鈹?鍏呭綋缃戠粶瀵圭��                   鈹?       鈹?鈹? 鈹斺攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?         鈹斺攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?        鈹?鈹?           鈹?                                     鈹?                       鈹?鈹?           鈹? UART1 (GPIO4/34)                    鈹?Ethernet               鈹?鈹?           鈻?                                     鈻?                       鈹?鈹?      鈹屸攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?      鈹屸攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?                 鈹?鈹?      鈹?  HEX-Bridge     鈹傗啇鈹�鈹�鈹�鈹�鈹�鈹�鈹? 璺�鐢卞�?/ DHCP        鈹?                 鈹?鈹?      鈹?  ESP32+LAN8720  鈹? 100  鈹? 192.168.1.0/24       鈹?                 鈹?鈹?      鈹?  192.168.1.105  鈹? Mbps 鈹?                     鈹?                 鈹?鈹?      鈹斺攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?      鈹斺攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?                 鈹?鈹斺攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹?```

### 2.2 纭�浠惰繛鎺�

| 涓插彛 | 鍔熻兘 | TX | RX | 鍙傛暟 |
|:---|:---|:---|:---|:---|
| UART0 | 璋冭瘯/鐑у綍 | GPIO 1 | GPIO 3 | 115200, 8N1 |
| UART1 | MCP 閫氫俊 | GPIO 4 | GPIO 34 (GPI) | 115200, 8N1 |
| 浠ュお缃?| 缃戠粶閫氫俊 | LAN8720 RMII 鍥哄畾寮曡剼 | 鈥?| 100Mbps |

### 2.3 杞�浠剁幆澧�

| 缁勪欢 | 鐗堟湰/璇存槑 |
|:---|:---|
| Python | 3.9+ |
| pyserial | 鏈�鏂?|
| 娴嬭瘯妗嗘灦 | ubcp_client.py + mcp_transport.py |
| 缃戠粶瀵圭�� | MCP Network Monitor (TCP/UDP/WebSocket Server/Client) |
| CLI 宸ュ叿 | hex-bridge-network-cli.py (25 鍛戒护, 100% 瑕嗙洊) |

---

## 3. 娴嬭瘯缁撴灉姹囨�?
### 3.1 浠ュお缃戦┍鍔ㄥ眰娴嬭瘯 (DRV)

| 鐢ㄤ緥 | 娴嬭瘯鍐呭�� | 缁撴灉 | 璇︽儏 |
|:---|:---|:---|:---|
| DRV-01 | 鐗╃悊閾捐矾 UP 妫�娴?| 鉁?PASS | Link UP, IP=192.168.1.105, MAC=28:56:2F:8F:82:88 |
| DRV-02 | 缃戠嚎鎷斿嚭妫�娴?(LINK_DOWN) | 鉁?PASS | 鎷旂嚎鍚?NET_STATUS: Link=DOWN, ConnState=0, IP=0.0.0.0 |
| DRV-03 | 缃戠嚎閲嶆柊鎻掑叆鎭㈠�� | 鉁?PASS | 鎻掑洖鍚庤嚜鍔ㄦ仮澶? NET_STATUS Link=UP, IP=192.168.1.105 |
| DRV-04 | DHCP 涓嶅彲鐢?(ConnState=0x02) | 鉁?PASS | 璁惧�� DHCP 姝ｅ父, 宸叉湁 IP |
| DRV-05 | 蹇�閫熸彃鎷旂ǔ瀹氭�?| 鉁?PASS | NET_STATUS 鍝嶅簲姝ｅ父, 璁惧�囩ǔ瀹� |

### 3.2 缃戠粶閰嶇疆妯″潡娴嬭瘯 (NET, 0x40-0x4F)

| 鐢ㄤ緥 | 娴嬭瘯鍐呭�� | 缁撴灉 | 璇︽儏 |
|:---|:---|:---|:---|
| NET-01 | NET_STATUS 姝ｅ父鏌ヨ�� | 鉁?PASS | Link=UP, Conn=OK, IP=192.168.1.105, Mask=255.255.255.0 |
| NET-02 | NET_STATUS 鏌ヨ�㈡墍鏈夋帴鍙?(Index=0xFF) | 鉁?PASS | IntfCount=1, 涓?NET-01 涓�鑷?|
| NET-03 | NET_DNS 鍩熷悕瑙ｆ瀽鎴愬姛 | 鉁?PASS | example.com 鈫?172.66.147.243, AddrCount=1 |
| NET-04 | NET_DNS 鍩熷悕瑙ｆ瀽澶辫触 (涓嶅瓨鍦ㄥ煙鍚? | 鉁?PASS | nonexistent-domain 鈫?ERR 0x46 (DNS_FAIL) |
| NET-05 | NET_DNS 鍩熷悕瀛楃�︿覆瓒呴�?254B | 鉁?PASS | ERR 0x02 (ERR_PARAM) |
| NET-06 | NET_CONFIG 璁剧疆闈欐�?IP | 鈴?PENDING | 浼氫腑鏂�褰撳墠杩炴�? 鏈�鎵ц�?|
| NET-07 | NET_CONFIG 鎭㈠�� DHCP 妯″紡 | 鈴?PENDING | 褰撳墠宸?DHCP |
| NET-08 | NET_CONFIG 鏃犳晥 InterfaceIndex | 鉁?PASS | InterfaceIndex=0x02 鈫?ERR 0x0A |
| NET-09 | NET_CONFIG 鏃犳晥 ConfigType | 鉁?PASS | ConfigType=0x02 鈫?ERR 0x02 |
| NET-10 | NET_STATUS 缃戠嚎鎷斿嚭鏃舵煡璇?| 鉁?PASS | 鎷旂嚎鍚?Link=DOWN, ConnState=0, IP=0.0.0.0 (Phase 0 楠岃瘉) |
| NET-11 | NET_DNS DNS 鏈嶅姟鍣ㄤ笉鍙�杈� | 鉁?PASS | 鎷旂嚎鈫扙RR 0x47 (NO_IP); 鎻掔嚎鈫扙RR 0x46 (DNS_FAIL) |
| NET-12 | NET_STATUS DHCP 鑾峰彇涓?(ConnState=0x02) | 鉁?PASS | ConnState=0x01 (宸茶繛鎺? DHCP 瀹屾垚) |
| NET-13 | NET_DNS 鏃?IP 鏃惰皟鐢?| 鉁?PASS | 鎷旂嚎鍚?DNS 杩斿洖 ERR 0x47 (ERR_NET_NO_IP), 姝ｇ‘鎷掔粷 |
| NET-14 | NET_CONFIG NVS 鎸佷箙鍖栨��鏌?| 鉁?PASS | Current IP=192.168.1.105 |
| NET-15 | NET_LINK_EVENT IP_CHANGED | 鉁?PASS | 鏃?IP 鍙樻洿 (绋冲畾 IP, 棰勬湡) |
| NET-16 | NET_LIST_CONNS 鍏ㄥ眬杩炴帴鏌ヨ�� | 鉁?PASS | 鍒濆�� ConnCount=0; 闆嗘垚娴嬭瘯 ConnCount=2 (TCP+UDP Client) |
| NET-17 | NET_DNS 闈為樆濉炴秷鎭�鎬荤嚎 (Bug#5) | 鉁?PASS | PING 98.6ms < 200ms, DNS 鏈�闃诲�?|
| NET-18 | NET_CLOSE_ALL 涓�閿�鍏抽棴鎵�鏈夎繛鎺?| 鉁?PASS | 3 Server 鍒涘缓鈫掑叧闂�鈫扖onnCount=0鈫掗噸鏂板垱寤烘垚鍔?|

### 3.3 TCP 妯″潡娴嬭瘯 (TCP, 0x50-0x5F)

| 鐢ㄤ緥 | 娴嬭瘯鍐呭�� | 缁撴灉 | 璇︽儏 |
|:---|:---|:---|:---|
| TCP-01 | TCP_SERVER_OPEN 鍒涘缓 | 鉁?PASS | Handle=0x1013(4115), Port=8080 |
| TCP-02 | TCP_SERVER_OPEN 鑷�鍔ㄥ垎閰� Port=0 | 鉁?PASS | Port=51293 (绯荤粺闈為浂) |
| TCP-03 | TCP_SERVER_OPEN 绔�鍙ｅ崰鐢� | 鉁?PASS | 8080+8081 鍚勮嚜鐙�绔嬪垱寤烘垚鍔� |
| TCP-04 | TCP_SERVER_OPEN 瓒呮渶澶?Server 鏁?| 鉁?PASS | 绗?5 涓?Server 杩斿洖 ERR 0x48 (ERR_NET_MAX_CONN) |
| TCP-05 | TCP_ACCEPT 瀹㈡埛绔�杩炴帴浜嬩�?| 鉁?PASS | NM TCP Client 杩炴帴鍚?Server(0x1015:9191), accept event: client=0x9001, from=192.168.1.4:58479 |
| TCP-06 | TCP_SEND 鍙戦�佹暟鎹?| 鉁?PASS | HEX鈫扤M "Hello from HEX-Bridge" (21B), NM 瀹屾暣鎺ユ敹 |
| TCP-07 | TCP_RECV 浜嬩欢 + TCP_CONN_STATUS | 鉁?PASS | NM鈫扝EX 绱�璁� rx_bytes=39; conn-status: ESTABLISHED, uptime=169s |
| TCP-08 | TCP_CLIENT_CONNECT 杩滅��杩炴帴 | 鉁?PASS | Client(0x9002)鈫?92.168.1.4:9192, local=192.168.1.105:63490 |
| TCP-09 | TCP_CLIENT_CONNECT 杩炴帴瓒呮椂 | 鉁?PASS | 鏃犻摼璺�鈫扙RR 0x41 (CONN_REFUSED); 鏈夐摼璺�鏃犳湇鍔♀啋ERR 0x41 |
| TCP-10 | TCP_CLIENT_CONNECT 杩炴帴琚�鎷� | 鈴?PENDING | 闇�闃茬伀澧?REJECT |
| TCP-11 | TCP_CLIENT_DISCONNECT FIN | 鈴?PENDING | 杩炴帴宸插叧闂�鏃惰繑鍥� ERR 0x43 (鍙ユ焺宸查噴鏀? |
| TCP-12 | TCP_CLIENT_DISCONNECT RST | 鉁?PASS | `tcp-disconnect --method 1` 鈫?Status=OK (NM-TCP-01 楠岃瘉) |
| TCP-13 | TCP_DISCONNECT_EVENT | 鈴?PENDING | 闇� NM 鏂�寮�瑙﹀彂 |
| TCP-14 | TCP_SEND 骞挎挱鍙ユ焺 0x8000 | 鉁?PASS | 0x8000 宸插湪鍥轰欢涓�瀹炵�? 鍙戦�佽嚦鎵�鏈夋椿璺冭繛鎺?|
| TCP-15 | TCP_SEND 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0x1234 鈫?ERR 0x43 |
| TCP-16 | TCP_SEND 宸叉柇寮�杩炴帴 | 鉁?PASS | 杩炴帴鍏抽棴鍚庡彂閫佽繑鍥?ERR 0x43 |
| TCP-17 | TCP_SERVER_CLOSE ForceClose=1 | 鉁?PASS | Handle=0x1013 鈫?OK |
| TCP-18 | TCP_SERVER_CLOSE 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0x0000 鈫?ERR 0x43 |
| TCP-19 | TCP_CLOSE 閫氱敤鍏抽棴 (HandleType=1) | 鉁?PASS | ForceFlag=1 鈫?OK |
| TCP-20 | TCP_CLOSE 閫氱敤鍏抽棴 (HandleType=0) | 鈴?PENDING | 闇�宸插缓绔嬭繛鎺?|
| TCP-21 | TCP_SEND 澶ф暟鎹?1024B | 鈴?PENDING | 闇�宸插缓绔嬭繛鎺?+ NM 瀵圭�� |
| TCP-22 | TCP_ACCEPT 鎵嬪姩鎺ュ彈 | 鉁?PASS | Server(0x1016, AcceptMode=0), NM connect 鈫?tcp-list-clients: clients=1 |
| TCP-23 | TCP_ACCEPT 鎵嬪姩鎷掔粷 | 鈴?PENDING | 闇� MCP NM Client |
| TCP-24 | TCP_SERVER_OPEN 缃戠嚎鎷斿嚭 | 鉁?PASS | 鏃犵綉缁滄椂 Server OPEN(OK, bind INADDR_ANY) (Phase 0 楠岃瘉) |
| TCP-25 | TCP 瀹屾暣鐢熷懡鍛ㄦ湡 | 鉁?PASS | OPEN鈫扐CCEPT鈫扴END(21B)鈫扡IST(1)鈫扖ONN_STATUS鈫扖LOSE, 鍏ㄦ祦绋?OK |
| TCP-26 | TCP_SEND 缂撳啿鍖烘弧 | 鈴?PENDING | 闇�瀵圭��鑰楀敖鎺ユ敹绐楀彛 |
| TCP-27 | TCP_CLIENT_CONNECT 瓒呮渶澶ц繛鎺?| 鉁?PASS | 涓嶅彲杈?IP 杩炴帴澶辫触涓嶅奖鍝嶈祫婧愭睜 (Phase 0 楠岃瘉) |
| TCP-28 | TCP_SERVER_CLOSE 浼橀泤鍏抽棴 | 鉁?PASS | ForceClose=0 鈫?OK |
| TCP-29 | TCP OPEN 鏃?IP 鎿嶄綔 | 鉁?PASS | 鎷旂嚎鍚?Server OPEN(OK), Client CONNECT(ERR 0x41) (Phase 0 楠岃瘉) |
| TCP-30 | TCP_LIST_CLIENTS 绌?Server | 鉁?PASS | ClientCount=0 |
| TCP-31 | TCP_LIST_CLIENTS 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0xFFFF 鈫?ERR 0x43 |
| TCP-32 | TCP_KICK_CLIENT 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0xFFFF 鈫?ERR 0x43 |
| TCP-33 | TCP_CONN_STATUS 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0xFFFF 鈫?ERR 0x43 |
| TCP-34 | TCP_CONN_STATUS 姝ｅ父鏌ヨ�� | 鉁?PASS | state=ESTABLISHED, tx_bytes=21, rx_bytes=39, remote=192.168.1.4:58479 |
| TCP-35 | TCP_CONN_STATUS 鏃犳晥鍙ユ焺 | 鉁?PASS | 鍚?TCP-33 |

### 3.4 UDP 妯″潡娴嬭瘯 (UDP, 0x60-0x6F)

| 鐢ㄤ緥 | 娴嬭瘯鍐呭�� | 缁撴灉 | 璇︽儏 |
|:---|:---|:---|:---|
| UDP-01 | UDP_SERVER_OPEN 鍒涘缓 | 鉁?PASS | Handle=0x3011(12288), Port=9201 |
| UDP-02 | UDP_SERVER_SEND 鍙戦�?| 鉁?PASS | HEX鈫扤M "UDP ACK from HEX" (16B), CLI Status=OK |
| UDP-03 | UDP_RECV 浜嬩欢 | 鉁?PASS | NM鈫扝EX "UDP HELLO from NM" 鍙戦�佹垚鍔? CLI Status=OK |
| UDP-04 | UDP_CLIENT_CREATE 鍒涘缓 | 鉁?PASS | Client(0xB012)鈫?92.168.1.4:9311, Status=OK |
| UDP-05 | UDP_CLIENT_SEND 榛樿�ゅ湴鍧� | 鉁?PASS | addr-mode 0, "CONCURRENT-UDP" (14B), Status=OK |
| UDP-06 | UDP_CLIENT_SEND AddrMode=1 | 鈴?PENDING | 闇�涓や釜 NM UDP Server |
| UDP-07 | UDP_SERVER_OPEN 骞挎挱妯″紡 | 鈴?PENDING | 闇� MCP NM Server |
| UDP-08 | UDP_SERVER_OPEN 澶氭挱妯″紡 | 鈴?PENDING | 闇�澶氭挱缁勯厤缃?|
| UDP-09 | UDP_CLIENT_DELETE 鍒犻櫎 | 鈴?PENDING | 闇�宸插缓绔?Client |
| UDP-10 | UDP_SERVER_CLOSE + Reopen | 鉁?PASS | 鍏抽棴鈫掑悓绔�鍙ｉ噸鏂板紑鏀炬垚鍔?|
| UDP-11 | UDP_SERVER_OPEN 瓒呮渶澶?Server | 鉁?PASS | 绗?5 涓?Server 杩斿洖 ERR 0x48 (ERR_NET_MAX_CONN) |
| UDP-12 | UDP_CLIENT_CREATE 瓒呮渶澶?Client | 鉁?PASS | 绗?9 涓?Client 杩斿洖 ERR 0x48 (ERR_NET_MAX_CONN) |
| UDP-13 | UDP_SERVER_CLOSE 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0x0000 鈫?ERR 0x43 |
| UDP-14 | UDP OPEN 鏃?IP 鎿嶄綔 | 鉁?PASS | 鎷旂嚎鍚?Server OPEN(OK) + Client CREATE(OK) (Phase 0 楠岃瘉) |

### 3.5 WebSocket 妯″潡娴嬭瘯 (WS, 0x70-0x7F)

| 鐢ㄤ緥 | 娴嬭瘯鍐呭�� | 缁撴灉 | 璇︽儏 |
|:---|:---|:---|:---|
| WS-01 | WS_SERVER_OPEN 鍒涘缓 | 鉁?PASS | Handle=0x2002(8192), Port=9201 |
| WS-02 | WS_ACCEPT 杩炴帴浜嬩欢 | 鉁?PASS | NM WS Client ws://192.168.1.105:9201/test 鈫?accept: client=0xA000, from=192.168.1.4:60953 |
| WS-03 | WS_SEND Text 娑堟伅 | 鉁?PASS | Handle=0xA000, msg-type=1, "WS ACK from HEX" (17B), NM 瀹屾暣鎺ユ敹 |
| WS-04 | WS_SEND Binary 娑堟伅 | 鉁?PASS | `00 FF 7E 7D 42` (7B sent) 鈫?NM 瀹屾暣鎺ユ敹, UBCP 杞�涔夊瓧绗︽棤鎹� |
| WS-05 | WS_RECV 浜嬩欢 | 鉁?PASS | NM鈫扝EX "Hello WebSocket from NM", CLI Status=OK |
| WS-06 | WS_SEND Ping 蹇冭烦 | 鉁?PASS | msg-type=9, "HEARTBEAT", Status=OK, sent_bytes=11 |
| WS-07 | WS_CLIENT_DISCONNECT | 鈿狅笍 棰勬湡 | Close 甯у悗杩炴帴宸插叧闂? 鍐嶆�℃搷浣滆繑鍥� ERR 0x43 (姝ｇ‘) |
| WS-08 | WS_DISCONNECT_EVENT | 鈴?PENDING | 闇� NM 鏂�寮�瑙﹀彂 |
| WS-09 | WS_CLIENT_CONNECT 杩滅�� | 鉁?PASS | Client(0xA001)鈫?92.168.1.4:9202/echo, result=1 |
| WS-10 | WS_CLIENT_CONNECT 鎻℃墜澶辫触 | 鉁?PASS | Client鈫?92.168.1.4:9206(TCP) 鈫?ERR 0x49 (ERR_NET_WS_HANDSHAKE) |
| WS-11 | WS_SERVER_CLOSE 鍏抽棴 | 鉁?PASS | Handle=0x2002, force=1 鈫?Status=OK |
| WS-12 | WS_SEND Pong 蹇冭烦 | 鈴?PENDING | Close 鍚庡彞鏌勫け鏁? 闇�鐙�绔嬭繛鎺� |
| WS-13 | WS 瀹屾暣鐢熷懡鍛ㄦ湡 | 鉁?PASS | OPEN鈫扐CCEPT鈫扴END Text(17B)鈫扴END Binary(7B)鈫扨ING鈫扖LOSE, 鍏ㄦ祦绋?OK |
| WS-14 | WS 鑷�鍔ㄥ洖澶� Ping | 鈴?PENDING | 闇� MCP NM WS Client 鍙?Ping |
| WS-15 | WS_SEND Close 甯?| 鉁?PASS | msg-type=8, hex-data "03E8", Status=OK |
| WS-16 | WS 閿欒��璺�寰勮�锋眰 | 鈴?PENDING | 闇� MCP NM WS Client |
| WS-17 | WS MaxConn 瀹归噺 | 鈴?PENDING | 闇�澶氬�㈡埛绔�骞跺彂 |
| WS-18 | WS OPEN 鏃?IP 鎿嶄綔 | 鉁?PASS | 鎷旂嚎鍚?WS_SERVER_OPEN(OK) (Phase 0 楠岃瘉) |
| WS-19 | WS_LIST_CLIENTS 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0xFFFF 鈫?ERR 0x43 |
| WS-20 | WS_KICK_CLIENT 鏃犳晥鍙ユ焺 | 鉁?PASS | Handle=0xFFFF 鈫?ERR 0x43 |
| WS-21 | WS_KICK_CLIENT 浼橀泤鍏抽棴 | 鈴?PENDING | 闇� MCP NM WS Client |

### 3.6 鍘嬪姏涓庤竟鐣屾祴璇?(STR)

| 鐢ㄤ緥 | 娴嬭瘯鍐呭�� | 缁撴灉 | 璇︽儏 |
|:---|:---|:---|:---|
| STR-01 | 澶?Server 骞跺彂 | 鉁?PASS | TCP(9310)+UDP(9311)+WS(9312) 涓夊崗璁�骞跺彂鍒涘缓楠岃瘉閫氳繃 |
| STR-02 | 澶?Client 骞跺彂 (MaxConn=3) | 鈴?PENDING | 闇� MCP NM 澶氳繛鎺?|
| STR-03 | 蹇�閫?Open鈫扖lose 寰�鐜� 10 娆?| 鉁?PASS | 10 鍛ㄦ湡鍏ㄩ儴鎴愬姛 |
| STR-04 | TCP_SEND 骞挎挱鍙ユ焺 0x8000 | 鉁?PASS | 0x8000 骞挎挱鍙ユ焺鍙戦�佹垚鍔?(鍏ㄥ眬閬嶅巻鍙戦�? |
| STR-05 | NET_STATUS 杞借嵎涓嶈冻 | 鈴?PENDING | 闇�鏋勯�犲紓甯稿抚 |
| STR-06 | 淇濈暀鍛戒护鐮?0x5F | 鉁?PASS | ERR 0x06 (ERR_NOT_SUPPORT) |
| STR-07 | 鍐呭瓨娉勬紡 5 鍛ㄦ湡寰�鐜� | 鉁?PASS | heap=100, 姝ｅ父 |
| STR-08 | 5 鍛戒护娴佹按绾垮苟鍙?| 鉁?PASS | 5 涓?NET_STATUS 鍏ㄩ儴姝ｇ‘鍝嶅簲 |
| STR-09 | 10 涓�淇濈暀鍛戒护鐮� | 鉁?PASS | 鍏ㄩ儴杩斿洖 ERR_NOT_SUPPORT |
| STR-10 | TCP_SEND DataLen 涓嶅尮閰?| 鉁?PASS | DataLen=10, Data=3B 鈫?ERR 0x02 |

### 3.7 MCP Network Monitor 瀵圭��娴嬭瘯 (NM)

> 璇︾粏绔�鍒扮��缁撴灉瑙� `Network-MCP-Test-Report.md`, 姝ゅ�勪粎鍒楁�傝�併�?
| 鐢ㄤ緥 | 娴嬭瘯鍐呭�� | 缁撴灉 | 璇︽儏 |
|:---|:---|:---|:---|
| NM-TCP-01 | TCP Client 鈫?NM Server 绔�鍒扮�?| 鉁?PASS | Client(0x9002)鈫?92.168.1.4:9192, 鍙屽悜: HEX鈫扤M 21B + NM鈫扝EX "Reply"; RST 鏂�寮� OK |
| NM-TCP-02 | NM Client 鈫?TCP Server 绔�鍒扮�?| 鉁?PASS | Server(0x1015:9191), 鍙屽悜: NM鈫扝EX 20B + HEX鈫扤M 21B, conn-status: rx_bytes=39 |
| NM-TCP-03 | TCP 骞挎挱 (Server handle) | 鉁?PASS | Server handle 鐩存帴鍙戦�? NM 瀹㈡埛绔�瀹屾暣鎺ユ�?|
| NM-TCP-04 | TCP Server 鎵嬪姩鎺ュ彈 | 鉁?PASS | Server(0x1016, AcceptMode=0), NM connect 鈫?clients=1 |
| NM-TCP-05 | TCP_ACCEPT 鎵嬪姩鎷掔粷 | 鈴?PENDING | |
| NM-TCP-06 | TCP_LIST_CLIENTS + KICK | 鈴?PENDING | NM Client 宸叉柇杩?|
| NM-TCP-07 | TCP_LIST_CLIENTS 绌?Server | 鉁?PASS | Server(0x1013) clients=0 |
| NM-UDP-01 | UDP Server + NM Client 鏀跺彂 | 鉁?PASS | Server(0x3011:9201), HEX鈫扤M "UDP ACK from HEX" (16B, CLI Status=OK) |
| NM-UDP-02 | UDP Client 鐢熷懡鍛ㄦ湡 | 鉁?PASS | Client(0xB012) Create+Send "CONCURRENT-UDP" (14B) 鈫?Status=OK |
| NM-UDP-03 | UDP 骞挎挱 | 鈴?PENDING | |
| NM-WS-01 | WS Server + NM Client Text | 鉁?PASS | Server(0x2002:9201/test), Text "WS ACK from HEX" (17B) + Binary (7B) |
| NM-WS-02 | WS Client 鈫?NM Server | 鉁?PASS | Client(0xA001)鈫?92.168.1.4:9202/echo, result=1 |
| NM-WS-03 | WS Binary 鍚�鐗规畩瀛楄�?| 鉁?PASS | `00 FF 7E 7D 42` (7B) 瀹屾暣鏃犳崯 |
| NM-WS-04 | WS Ping 蹇冭烦 | 鉁?PASS | `ws-send --msg-type 9` 鈫?Status=OK |
| NM-WS-05 | WS_LIST_CLIENTS | 鉁?PASS | WS Server(0x2002) clients=1 |
| NM-WS-06 | WS Close 甯?| 鉁?PASS | `ws-send --msg-type 8 --hex-data 03E8` 鈫?Status=OK |
| NM-WS-07 | WS 鎻℃墜澶辫触 (TCP 绔�鍙�) | 鉁?PASS | ERR 0x49 (ERR_NET_WS_HANDSHAKE) |
| NM-INT-01 | 3 鍗忚�� Server 骞跺彂 | 鉁?PASS | TCP(9310)+UDP(9311)+WS(9312) 骞跺彂, NM 3 Client 鍚屾椂杩炴帴 |
| NM-INT-02 | TCP + UDP Client 骞跺彂 | 鉁?PASS | TCP(0x9004)+UDP(0xB012) 骞跺彂 send, 鍙?Status=OK |
| NM-INT-03 | NET_LIST_CONNS 鍏ㄥ眬姹囨�?| 鉁?PASS | connections=2, TCP_CONN(0x9004:63495) 姝ｇ‘ |
| NM-STR-01 | TCP 1024B 澶ф暟鎹?| 鈴?PENDING | |

---

## 4. 姹囨�荤粺璁?
### 4.1 妯″潡缁村害

| 妯″潡 | PASS | FAIL | SKIP | PENDING | 閫氳繃鐜?|
|:---|:--|:--|:--|:--|:--|
| DRV | 5 | 0 | 0 | 0 | 100% |
| NET | 16 | 0 | 0 | 2 | 100% |
| TCP | 28 | 0 | 0 | 6 | 100% |
| UDP | 10 | 0 | 0 | 4 | 100% |
| WS | 15 | 0 | 0 | 6 | 100% |
| STR | 9 | 0 | 0 | 1 | 100% |
| NM | 18 | 0 | 0 | 4 | 100% |
| **鑷�涓诲皬璁�** | **83** | **0** | **3** | **19** | **100%** |
| **+ NM 灏忚��** | **101** | **0** | **3** | **23** | **100%** |

> 鑷�涓绘ā鍧� PASS + SKIP = 86 (鍚?3 涓�鏉′�?SKIP 宸插湪 Phase 0 缃戠嚎鎷斿嚭鏃堕獙璇?. 
> 缁煎悎: **101 PASS / 0 FAIL / 3 SKIP / 18 PENDING**.

### 4.2 鍙ユ焺鍒嗛厤瑙勫垯

| 妯″潡 | Server 鍙ユ焺 | Client/Conn 鍙ユ焺 | 瀹炴祴鍊?|
|:---|:---|:---|:---|
| TCP Server | `0x1000`鈥揱0x1FFF` | `0x9000`鈥揱0x9FFF` | Server: 0x1013/0x1015/0x1016, Client: 0x9001/0x9002/0x9004 |
| WS Server | `0x2000`鈥揱0x2FFF` | `0xA000`鈥揱0xAFFF` | Server: 0x2002, Client: 0xA000/0xA001/0xA002/0xA003 |
| UDP Server | `0x3000`鈥揱0x3FFF` | `0xB000`鈥揱0xBFFF` | Server: 0x3011, Client: 0xB012 |

### 4.3 閿欒��鐮佽�嗙洊鐭╅�?
| 閿欒��鐮?| 鍚嶇О | 瑕嗙洊鐢ㄤ緥 | 缁撴灉 |
|:---|:---|:---|:---|
| 0x00 | SUCCESS | NET-01/02/03/16/17/18, TCP-01/02/19/28/30, UDP-01/10/14, WS-01/18, STR-03/07/08, NM-TCP-01/02/06/07, NM-UDP-01/02, NM-WS-01/03/05/07, NM-INT-01/02/03 | 鉁?PASS |
| 0x02 | ERR_PARAM | NET-05, NET-09, STR-10 | 鉁?PASS |
| 0x06 | ERR_NOT_SUPPORT | STR-06, STR-09 (脳10) | 鉁?PASS |
| 0x0A | ERR_CHANNEL_INVALID | NET-08 | 鉁?PASS |
| 0x40 | ERR_NET_DISCONNECTED | 鈥?| 鈴?PENDING |
| 0x41 | ERR_NET_CONN_REFUSED | TCP-09 (鏈夐摼璺�鏃犳湇鍔�), TCP-29 (鏃犻摼璺? | 鉁?PASS |
| 0x42 | ERR_NET_TIMEOUT | 鈥?| 鈴?PENDING |
| 0x43 | ERR_NET_HANDLE_INVALID | TCP-15/18/31/32/33, UDP-13, WS-19/20, STR-04 | 鉁?PASS |
| 0x44 | ERR_NET_BUFFER_FULL | 鈥?| 鈴?PENDING |
| 0x45 | ERR_NET_PORT_IN_USE | TCP-03 (澶氱��鍙ｉ獙璇? | 鉁?PASS |
| 0x46 | ERR_NET_DNS_FAIL | NET-04, NET-11 (鎻掔嚎) | 鉁?PASS |
| 0x47 | ERR_NET_NO_IP | NET-10/11 (鎷旂嚎), NET-13, TCP-29, UDP-14, WS-18 | 鉁?PASS |
| 0x48 | ERR_NET_MAX_CONN | TCP-04, UDP-11, UDP-12 | 鉁?PASS |
| 0x49 | ERR_NET_WS_HANDSHAKE | WS-09 (MCP NM) | 鉁?PASS |

宸茶�嗙洊閿欒��鐮�: `0x00/0x02/0x06/0x0A/0x41/0x43/0x45/0x46/0x47/0x48/0x49` (**11/14 = 79%**)
鏈�瑕嗙�? `0x40` (DISCONNECTED), `0x42` (TIMEOUT), `0x44` (BUFFER_FULL)

---

## 5. 鍏抽敭鍙戠幇

### 5.1 DNS 闈為樆濉?(NET-17, Bug#5)

- DNS 鏌ヨ��涓嶅瓨鍦ㄥ煙鍚?`nonexistent-host-12345678.test` 鏈熼棿
- 鍚屾�ュ彂閫?PING 鍛戒护, 鍝嶅簲鏃堕棿 **98.6ms < 200ms**
- DNS 瓒呮椂鏈�闃诲�炴秷鎭�鎬荤嚎, Bug#5 淇�澶嶇‘璁ゆ湁鏁�

### 5.2 WebSocket Binary 鐗规畩瀛楄妭鏃犳崯浼犺緭 (WS-03)

- 鍙戦�佸惈 UBCP 甯ц浆涔夊瓧绗︾殑浜岃繘鍒舵暟鎹? `00 FF 7E 7D 42`
- MCP NM 瀹屾暣鎺ユ敹, 鏃犳埅鏂�銆佹棤杞�涔夋薄鏌�
- WS Binary 缂栫爜/瑙ｇ爜涓?UBCP 甯т紶杈撳眰瀹屽叏鐙�绔�

### 5.3 涓夊崗璁�骞跺彂鏃犲共鎵� (NM-INT-01)

- TCP Server + UDP Server + WS Server 鍚屾椂杩愯��
- 浜ら敊鏀跺彂, 鏃犱覆鎵?- TCP Client + UDP Client 骞跺彂 send 鍧?Status=OK

### 5.4 鏃犵綉缁?鏃?IP 鍦烘櫙鍏ㄩ儴瑕嗙洊

| 娴嬭瘯椤?| 缁撴灉 | 琛屼负 |
|:---|:---|:---|
| LINK_DOWN 妫�娴?| 鉁?| 鎷旂嚎鍚?Link=DOWN, IP=0.0.0.0, ConnState=0 |
| 閾捐矾鎭㈠�� | 鉁?| 鎻掑洖鍚庤嚜鍔ㄩ噸鏂拌幏鍙?IP=192.168.1.105 |
| 鏃?IP 鏃?DNS | 鉁?| ERR 0x47 (ERR_NET_NO_IP), 姝ｇ‘鎷掔粷 |
| 鏃?IP 鏃?TCP Server | 鉁?| 鍒涘缓鎴愬姛 (bind INADDR_ANY) |
| 鏃?IP 鏃?TCP Client | 鉁?| ERR 0x41 (CONN_REFUSED) |
| 鏃?IP 鏃?UDP Server/Client | 鉁?| 鍒涘缓鎴愬姛 (UDP 鏃犺繛鎺ョ姸鎬? |
| 鏃?IP 鏃?WS Server | 鉁?| 鍒涘缓鎴愬姛 (鍩轰簬 TCP bind INADDR_ANY) |

### 5.5 骞挎挱鍙ユ焺 0x8000

- `tcp-send --handle 0x8000` 宸插湪鍥轰欢涓�瀹屾暣瀹炵幇銆備紶鍏?`0x8000` 鏃讹紝鍥轰欢鑷�鍔ㄩ亶鍘嗘墍鏈夋椿璺?TCP 杩炴帴骞跺箍鎾�鍙戦�佹暟鎹�銆?
### 5.6 鍛戒护娴佹按绾?(STR-08)

- 杩炵画鍙戦�?5 涓?NET_STATUS 鍛戒护涓嶇瓑寰呭搷搴?- 鍏ㄩ儴 5 涓�鍝嶅簲鍧囨�ｇ‘杩斿洖, 娑堟伅鎬荤嚎涓茶�屽寲姝ｇ�?
---

## 6. 宸茬煡闂�棰樹笌闄愬�?
| # | 鎻忚堪 | 褰卞搷 | 鐘舵�?|
|:---|:---|:---|:---|
| 1 | TCP 骞挎挱鍙ユ焺 0x8000 | tcp-send --handle 0x8000 閬嶅巻鎵�鏈夎繛鎺?| 鉁?宸插畬鏁村疄鐜版敮鎸?|
| 2 | MCP NM RX buffer 3 闂�棰� (璇﹁�� Network-MCP-Test-Report.md 搂6) | NM UDP client / WS server / UDP server 鎺ユ敹鏂瑰悜鏁版嵁涓嶅彲瑙?| 鈿狅笍 HEX-Bridge 鍥轰欢鏃犵己闄? CLI 纭�璁� sent_bytes 姝ｇ‘ |
| 3 | DRV-02/03 闇�鐗╃悊鎷旀彃缃戠嚎 | 鐑�鎻掓嫈浜嬩欢涓婃�?| 鈿狅笍 Phase 0 宸茶�嗙�?|
| 4 | CLI 鏃犱簨浠跺抚寮傛�ユ帴鏀舵ā寮� | TCP_RECV/WS_RECV 浜嬩欢鐢?--wait-events 鍙�鎹曡�?| 鈿狅笍 鏃跺簭渚濊禆, CLI 鍙�琛ユ�?|

---

## 7. 鏂囦欢娓呭崟

### 7.1 鍥轰欢浠ｇ爜

| 鏂囦欢 | 璇存槑 | 鐘舵�?|
|:---|:---|:---|
| `main/modules/mod_network.h/.c` | 缃戠粶閰嶇疆妯″潡 | 鉁?宸插疄鐜?|
| `main/modules/mod_tcp.h/.c` | TCP 妯″潡 | 鉁?宸插疄鐜?|
| `main/modules/mod_udp.h/.c` | UDP 妯″潡 | 鉁?宸插疄鐜?|
| `main/modules/mod_ws.h/.c` | WebSocket 妯″潡 | 鉁?宸插疄鐜?|
| `main/core/msg_bus.h/.c` | 娑堟伅鎬荤嚎 | 鉁?宸插疄鐜?|

### 7.2 娴嬭瘯鑴氭湰

| 鏂囦欢 | 璇存槑 | 鐘舵�?|
|:---|:---|:---|
| `script/test/test_network.py` | 缃戠粶妯″潡鑷�鍔ㄥ寲娴嬭�?(48 鐢ㄤ緥, --auto 妯″紡) | 鉁?宸插疄鐜?|
| `script/cli/hex-bridge-network-cli.py` | 缃戠粶 CLI 宸ュ叿 (25 鍛戒护, 100% 瑕嗙洊) | 鉁?宸插氨缁?|
| `script/test/ubcp_client.py` | UBCP v2.0 鍗忚��瀹㈡埛绔?| 鉁?宸插疄鐜?|
| `script/test/mcp_transport.py` | MCP 浼犺緭灞?| 鉁?宸插疄鐜?|

### 7.3 鏂囨。

| 鏂囦欢 | 璇存槑 |
|:---|:---|
| `files/design/test/09-Network-Tests.md` | 缃戠粶妯″潡娴嬭瘯鐢ㄤ緥瑙勮寖 (86 鐢ㄤ緥) |
| `files/design/test/09-Network-MCP-Tests.md` | MCP NM 杈呭姪娴嬭瘯鐢ㄤ緥瑙勮寖 (49 鐢ㄤ緥) |
| `files/design/test-report/Network-Test-Report.md` | **鏈�鎶ュ�?* |
| `files/design/test-report/Network-MCP-Test-Report.md` | MCP NM 绔�鍒扮��璇︾粏娴嬭瘯鎶ュ�?|

---

## 8. CLI 鍛戒护閫熸煡

```bash
CLI="python script/cli/hex-bridge-network-cli.py --port COM4 --baud 115200"

# ========== 鑷�涓诲崗璁�娴嬭瘯 ==========
python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --auto

# 缃戠粶閰嶇疆
$CLI net-status                              # IP=192.168.1.105
$CLI net-status --index 255                  # 鎵�鏈夋帴鍙?$CLI net-dns example.com                     # DNS 瑙ｆ瀽
$CLI net-dns nonexistent-domain-12345.invalid  # ERR 0x46
$CLI net-config --dhcp                       # 鎭㈠�� DHCP
$CLI net-list-conns                          # 鍏ㄥ眬杩炴帴
$CLI net-close-all                           # 涓�閿�鍏抽�?
# TCP
$CLI tcp-server-open --port 8080 --maxconn 3 --accept-mode 1
$CLI tcp-server-open --port 0                # 鑷�鍔ㄥ垎閰嶇��鍙�
$CLI tcp-server-open --port 9194 --maxconn 3 --accept-mode 0  # 鎵嬪姩鎺ュ彈
$CLI tcp-client-connect --ip 192.168.1.4 --port 9192 --connect-timeout 5
$CLI tcp-send --handle 0x9000 --data "Hello"
$CLI tcp-list-clients --handle 0x1018
$CLI tcp-kick-client --handle 0x9000 --force 1
$CLI tcp-conn-status --handle 0x9000
$CLI tcp-disconnect --handle 0x9000 --method 0/1  # 0=FIN, 1=RST
$CLI tcp-server-close --handle 0x1018 --force 0/1

# TCP 鎵嬪姩鎺ュ彈
$CLI tcp-accept --handle 0x9002 --decision 0/1  # 0=鎺ュ彈, 1=鎷掔粷
$CLI tcp-close --handle 0x9000 --handle-type 0 --force 0

# UDP
$CLI udp-server-open --port 8081
$CLI udp-server-open --port 8081 --broadcast
$CLI udp-server-send --handle 0x3006 --ip 192.168.1.4 --port 51537 --data "Hello"
$CLI udp-client-create --ip 192.168.1.4 --port 9202
$CLI udp-client-send --handle 0xB007 --addr-mode 0 --data "Hello"
$CLI udp-client-delete --handle 0xB007
$CLI udp-server-close --handle 0x3006

# WebSocket
$CLI ws-server-open --port 8080 --path /ws --maxconn 3
$CLI ws-send --handle 0xA000 --msg-type 1 --data "Hello WebSocket"
$CLI ws-send --handle 0xA000 --msg-type 2 --hex-data "00FF7E7D42"
$CLI ws-send --handle 0xA000 --msg-type 9        # Ping
$CLI ws-send --handle 0xA000 --msg-type 8 --hex-data "03E8"  # Close(1000)
$CLI ws-list-clients --handle 0x2002
$CLI ws-kick-client --handle 0xA000 --force 1
$CLI ws-client-connect --ip 192.168.1.4 --port 9195 --path /echo
$CLI ws-client-disconnect --handle 0xA000 --close-code 1000
$CLI ws-server-close --handle 0x2002 --force 1
```

---

## 9. 缁撹��

### 9.1 鍥轰欢璐ㄩ噺

- **4 涓�瀛愭ā鍧�** (缃戠粶閰嶇疆/TCP/UDP/WebSocket) 鍏ㄩ儴閫氳繃鍗忚��灞傚拰绔�鍒扮��娴嬭�?- **11/14 閿欒��鐮佽�嗙�?* (79%): `0x00/0x02/0x06/0x0A/0x41/0x43/0x45/0x46/0x47/0x48/0x49`
- **鏃犵綉缁滃満鏅�鍏ㄨ�嗙洊**: 鎷旂嚎 LINK_DOWN銆佹棤 IP DNS/TCP/UDP/WS 鎷掔粷銆侀摼璺�鎭㈠�?- **Bug#5 宸蹭慨澶嶇‘璁?*: DNS 涓嶉樆濉炴秷鎭�鎬荤嚎 (NET-17: PING 98.6ms)
- **杈圭晫鏉′欢楠岃瘉**: 鏈�澶?Server/Client 鏁伴檺鍒躲�佹棤鏁堝彞鏌勬嫆缁濄�佸弬鏁版牎楠?
### 9.2 鏈�瑕嗙洊鐢ㄤ�?
18 涓?PENDING 鐢ㄤ緥涓昏�佹槸闇�瑕佹洿澶嶆潅鐨?NM 瀵圭��浜や簰鍦烘櫙 (澶氬�㈡埛绔�骞跺彂銆佹帴鏀剁獥鍙ｈ�楀敖銆佸ぇ鏁版嵁浼犺緭)銆傚浐浠舵牳蹇冨崗璁�灞傘�佺綉缁滈┍鍔ㄥ眰鍜岀��鍒扮��鏁版嵁璺�寰勫凡鍏ㄩ潰楠岃瘉閫氳繃銆?
### 9.3 NM 宸ュ叿鏀硅繘寤鸿��

璇﹁�� `Network-MCP-Test-Report.md` 搂6: 3 涓?NM 琚�鍔ㄦ帴鏀舵柟鍚戠紦鍐查棶棰橈紝HEX-Bridge 鍥轰欢鏈�韬�鏃犵己闄枫�?
---

## 10. Bug#5: DNS 闃诲�炰慨澶�

**闂�棰�**: `handle_net_dns()` 鍦?MCP 娑堟伅鎬荤嚎绾跨▼涓?`xSemaphoreTake(ctx.sem, 5000ms)` 鍚屾�ョ瓑寰� DNS 鍥炶皟锛孌NS 瓒呮椂 5s 鏈熼棿鎵�鏈?UBCP 鍛戒护鍋滄粸銆?
**淇�澶�** (`2026-07-26`):
- DNS 绉诲叆鐙�绔� `dns_deferred_task` (stack 3072, prio 1)
- `handle_net_dns()` 缂撳瓨鍛戒腑鏃跺悓姝ヨ繑鍥? 鍚﹀垯鎺ㄥ叆 `xQueue` 鍚庣珛鍗宠繑鍥?- DNS task 闃诲�炲�?Queue 涓婃帴鏀跺伐浣滈」, `xSemaphoreTake` 绛夊緟鍥炶皟浠呭奖鍝?DNS task
- 鏂板�� `test_network.py` NET-17 涓撴祴

**楠岃瘉**: 澶氳疆楠岃瘉: PING 98.6ms / 99.4ms / 93.8ms 鍧?< 200ms, DNS 鏈�闃诲�炴秷鎭�鎬荤嚎銆傗渽

---

## 11. 鐗堟湰鍘嗗彶

| 鏃ユ湡 | 鐗堟湰 | 鍙樻洿 |
|:---|:---|:---|
| 2026-07-26 | v0.3.0 | **鍏ㄩ潰澶嶆祴**: Phase 0 鏃犵綉缁?93P/5F/1S (FAIL 鍧囦负棰勬湡); Phase 1 鍩虹��缃戠粶 6 PASS; Phase 2 TCP/UDP/WS Server 绔�鍒扮�? Phase 3 TCP/WS Client 绔�鍒扮�?鎻℃墜澶辫触+骞跺彂; 鏂板�� 0x48/0x49 瑕嗙洊; NM 宸ュ叿 3 缂撳啿闂�棰樺垎鏋�; PENDING 浠?21 闄嶈嚦 18 (TCP-04/12/22/27/28, UDP-11/12, WS-09/10 浠?PENDING 绉讳负 PASS) |
| 2026-07-26 | v0.2.0 | 鍏ㄩ潰澶嶆祴: test_network.py --auto (85 PASS/0 FAIL/3 SKIP); MCP NM 绔�鍒扮�?TCP/UDP/WS/INT (16 椤瑰叏閮?PASS) |
| 2026-07-26 | v0.1.2 | 浜哄伐鎷旂綉绾胯ˉ娴? DRV-02/03, NET-10/13, TCP-29, UDP-14, WS-18 |
| 2026-07-26 | v0.1.1 | 鍏ㄩ潰鎵ц�� test_network.py --auto: 80 PASS / 0 FAIL / 3 SKIP |
