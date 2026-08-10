# HEX-Bridge

**English** | [中文](./README_zh.md)

**ESP32-based multi-interface bridge device — gives AI agents hardware I/O capability over a unified serial protocol.**

Host-side MCP Server communicates with this firmware via UBCP (Unified Binary Communication Protocol) v2.0 over UART. The bridge exposes CAN FD, SPI, I2C, UART, GPIO, Ethernet (TCP/UDP/WebSocket), OTA, and bulk transfer — turning an AI coding agent from a software-only tool into one that can interact with physical targets directly.

---

## Build Environment

| Item | Version / Info |
|:---|:---|
| **IDE** | 点线面 Code |
| **SDK** | ESP-IDF v6.0.1 |
| **Toolchain** | xtensa-esp-elf 15.2.0 (20251204) |
| **Python** | 3.11 (ESP-IDF Python env) |
| **Build System** | CMake 4.0 + Ninja 1.12 |
| **RTOS** | FreeRTOS (pre-installed with ESP-IDF) |
| **C Standard** | C11 (with picoLIBC, no newlib dependency) |

---

## Hardware

### Chip

| Item | Spec |
|:---|:---|
| **MCU** | Espressif ESP32 (Xtensa 32-bit LX6 dual-core) |
| **CPU Clock** | up to 240 MHz |
| **SRAM** | 520 KB internal + 8 MB external PSRAM |
| **Flash** | 16 MB (SPI) |
| **FreeRTOS Heap** | ~300 KB available |

### Pinout

| Peripheral | Pins | Notes |
|:---|:---|:---|
| CAN FD (MCP2518FD) | SCK=14, MOSI=13, MISO=36, CS=15, INT=39 | SPI-attached, CS on strapping pin (10 kΩ pull-up) |
| I2C (EEPROM 24C02) | SCL=12, SDA=33 | GPIO12=MTDI, 4.7 kΩ pull-up required for boot |
| Ethernet (LAN8720) | RMII fixed pins, PHY_RST=5 | SMI=GPIO23/18, PHY addr=1, MDIO needs 4.7kΩ pull-up |
| UART1 (MCP) | TX=4, RX=34 | RX is GPI only, external 10 kΩ pull-up |
| UART2 (ext) | TX=32, RX=35 | RX is GPI only, external 10 kΩ pull-up |
| UART0 (debug) | TX=1, RX=3 | Default ESP32 debug UART |

---

## Architecture

```
┌──────────────┐     UBCP v2.0      ┌──────────────┐
│  MCP Server  │◄────(UART 115200)──►│  HEX-Bridge  │──┬─── CAN FD (MCP2518FD)
│  (Host PC)   │                    │   (ESP32)    │  ├─── SPI
└──────────────┘                    └──────────────┘  ├─── I2C
                                                       ├─── UART ×2 (ext + debug)
                                                       ├─── GPIO
                                                       └─── Ethernet (100M)
```

- **UART1** — MCP communication, 115200 bps (GPIO4 TX / GPIO34 RX)
- **UART2** — extension port (GPIO32 TX / GPIO35 RX)
- **UART0** — debug console, 115200 bps (GPIO1 TX / GPIO3 RX)

Firmware runs on FreeRTOS with a message-bus + modular-task architecture. Each peripheral module registers itself as `hex_module_t` with a command-code range. Incoming frames are parsed, CRC-checked, and dispatched by command code to the target module — no hard-coded routing.

---

## Planned Capabilities

| Module | Cmd Range | Description |
|:---|:---|:---|
| **System** | `0x00-0x0F` | PING, device info, config read/write, reset, flow control, topology query, boot event |
| **CAN / CAN FD** | `0x10-0x1F` | Open/close channel, configure bitrate (arbitration + FD data), send/receive frames (≤64 B), filter setup, bus status |
| **SPI** | `0x20-0x2F` | Open/close device, configure mode/clock/bit-order, full-duplex transfer, half-duplex write/read, manual CS control |
| **I2C** | `0x30-0x3F` | Open/close bus, speed config (100k/400k/1M), 7/10-bit write/read, combined write-read (repeated start), bus scan |
| **Network Config** | `0x40-0x4F` | DHCP/static IP, status query, DNS resolution, link event reporting, global connection list |
| **TCP** | `0x50-0x5F` | Server open/close (4 max), client connect/disconnect (16 max), send/recv/accept events, list/kick/conn-status |
| **UDP** | `0x60-0x6F` | Server open/close (4 max), client create/delete (8 max), send via server/client, recv event |
| **WebSocket** | `0x70-0x7F` | Server open/close (4 max, 16 conns), client connect/disconnect, send (text/binary), recv/accept/ping-pong events, list/kick |
| **GPIO** | `0x80-0x8F` | Pin direction, output/input, pull-up/down, interrupt enable with trigger config, mask write, full read |
| **Bulk Transfer** | `0x90-0x9F` | Start/stop bulk session, data frames with sliding-window ACK/NACK and retransmission |
| **UART Extension** | `0xA0-0xAF` | Open/close port, config (baud/data/parity/flow), data send, 4 receive modes, break, flush, status |
| **OTA** | `0xB0-0xBF` | Begin (SHA-256), data blocks with CRC chunk verification, end & verify, progress query, rollback |

---

## Protocol

UBCP v2.0 frame format:

```
SOF(AA 55) | Ver | Flags | SeqNum(2B) | CmdCode | ChannelID | PayloadLen(2B) | [Timestamp 4B] | Payload(≤2048B) | CRC16(2B) | EOF(7E)
```

- Fixed 10-byte header + variable payload
- CRC-16/CCITT-FALSE (poly `0x1021`, init `0xFFFF`)
- Byte-stuffing: `0x7E`→`0x7D 0x5E`, `0x7D`→`0x7D 0x5D`
- All multi-byte fields are big-endian
- Async events (`DIR=1, EVT=1`) for unsolicited data (CAN frames, UART RX, GPIO interrupts)

Streaming byte-level parser with single-buffer online CRC. Filters spurious SOF without resetting the receive buffer. No double-buffering — memory budget ~22 KB for protocol state against ~300 KB ESP32 heap.

---

## Development Progress

| Module | Status | Notes |
|:---|:---|:---|
| **Protocol Layer** | ✅ Done | Frame parsing, CRC, byte-stuffing, escape handling |
| **Message Bus** | ✅ Done | Command-code routing dispatch |
| **Transport (MCP)** | ✅ Done | UART1 115200 bps RX/TX with frame assembly |
| **System (0x00-0x0F)** | ✅ Base | PING, GET_INFO, GET/SET_CONFIG, RESET, FLOW_CONTROL, SYS_BOOT_EVENT, TOPOLOGY |
| **UART Extension (0xA0-0xAF)** | ✅ Complete | All 8 commands, 57 test cases — 57/57 PASS |
| **Network (0x40-0x7F)** | ✅ Complete | **LAN8720 Ethernet 100M, DHCP, DNS** — tested to 70 PASS / 0 FAIL |
| 　 ├─ Network Config (0x40-0x4F) | ✅ | NET_CONFIG, NET_STATUS, NET_DNS, NET_LINK_EVENT, NET_LIST_CONNS |
| 　 ├─ TCP (0x50-0x5F) | ✅ | 12 commands: Server/Client, select() event loop, list/kick/conn-status |
| 　 ├─ UDP (0x60-0x6F) | ✅ | 7 commands: Server/Client, select() event loop |
| 　 └─ WebSocket (0x70-0x7F) | ✅ | 10 commands: WS frame en/decode, SHA-1 handshake, list/kick |
| **CAN / CAN FD** | ✅ Complete | MCP2518FD (SPI, 20 MHz xtal), 12 commands — PCAN 104/0/23, CANable 98/0/1, Manual 43/0/0 |
| **SPI** | ☐ Planned | — |
| **I2C** | ☐ Planned | 24C02 EEPROM, pinout assigned |
| **GPIO** | ☐ Planned | — |
| **Bulk Transfer** | ☐ Planned | — |
| **OTA** | ☐ Planned | Dual-partition with SHA-256 verification |

---

## CAN / CAN FD Module

### Implementation

MCP2518FD CAN FD controller driven over SPI (10 MHz, Mode 0), with an external 20 MHz crystal (system clock 20 MHz, PLL disabled). Full command coverage per protocol `files/design/protocol/04-CAN.md`:

| Command | Code | Description |
|:---|:---|:---|
| CAN_OPEN | `0x10` | Open channel (Normal / Listen-Only / Loopback) |
| CAN_CLOSE | `0x11` | Close channel (drains TX first) |
| CAN_CONFIG | `0x12` | Bitrate config: 10k–1M arbitration, FD data 1M–5M, custom Mode-B timing |
| CAN_SEND | `0x13` | Send classic / CAN FD / BRS / RTR frames (≤64 B) |
| CAN_RECV | `0x14` | Receive event (async) with RxFlags + timestamp |
| CAN_FILTER | `0x15` | Single filter (std / ext / both) |
| CAN_STATUS | `0x16` | Bus state, TEC/REC, queue usage, error counters |
| CAN_BUS_EVENT | `0x17` | Bus state change event (Error Active/Passive/Bus-Off) |
| CAN_ERROR_EVENT | `0x18` | Error frame detail (CRC/Form/ACK/Bit/Stuff) — 500 ms throttle |
| CAN_SLEEP | `0x19` | Enter sleep |
| CAN_WAKEUP | `0x1A` | Wake and restore mode |
| CAN_FILTER_BATCH | `0x1B` | Batch configure filters |

### Test Coverage

| Suite | Result | Notes |
|:---|:---|:---|
| PCAN-USB (`test_can.py --phase 0`) | **104 PASS / 0 FAIL / 23 SKIP** | 94 cases (Phase 1: 12 + Phase 2: 82); SKIPs are FD (classic PCAN) & manual-intervention cases |
| CANable 2.0 (`test_canable.py`) | **98 PASS / 0 FAIL / 1 SKIP** | Classic + CAN FD (64 B, BRS, DLC map); SKIP = canable2 slcan does not forward FD+BRS RX |
| Manual, bus disconnected (`test_can.py --phase 3`) | **43 PASS / 0 FAIL / 0 SKIP** | Error events, TX queue full, OneShot, Sleep/Wakeup, Listen-Only reject |

Test reports: `files/design/test-report/CAN-Test-Report.md`

---

FW version `0.1.0`, model ID `HXB1`, target `esp32`.
