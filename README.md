# HEX-Bridge

**English** | [中文](./README_zh.md)

**ESP32-based multi-interface bridge device — gives AI agents hardware I/O capability over a unified serial protocol.**

Host-side MCP Server communicates with this firmware via UBCP (Unified Binary Communication Protocol) v2.0 over UART. The bridge exposes CAN FD, SPI, I2C, UART, GPIO, Ethernet (TCP/UDP/WebSocket), OTA, and bulk transfer — turning an AI coding agent from a software-only tool into one that can interact with physical targets directly.

---

## Architecture

```
┌──────────────┐     UBCP v2.0      ┌──────────────┐
│  MCP Server  │◄────(UART 921600)──►│  HEX-Bridge  │──┬─── CAN FD (MCP2518FD)
│  (Host PC)   │                    │   (ESP32)    │  ├─── SPI
└──────────────┘                    └──────────────┘  ├─── I2C
                                                       ├─── UART ×2 (ext + debug)
                                                       ├─── GPIO
                                                       └─── Ethernet (100M)
```

- **UART1** — MCP communication, 921600 bps (GPIO4 TX / GPIO34 RX)
- **UART2** — extension port (GPIO32 TX / GPIO35 RX)
- **UART0** — debug console, 115200 bps (GPIO1 TX / GPIO3 RX)

Firmware runs on FreeRTOS with a message-bus + modular-task architecture. Each peripheral module registers itself as `hex_module_t` with a command-code range. Incoming frames are parsed, CRC-checked, and dispatched by command code to the target module — no hard-coded routing.

---

## Planned Capabilities

| Module | Cmd Range | Description |
|:---|:---|:---|
| **System** | `0x00-0x0F` | PING, device info, config read/write, reset, flow control |
| **CAN / CAN FD** | `0x10-0x1F` | Open/close channel, configure bitrate (arbitration + FD data), send/receive frames (≤64 B), filter setup, bus status |
| **SPI** | `0x20-0x2F` | Open/close device, configure mode/clock/bit-order, full-duplex transfer, half-duplex write/read, manual CS control |
| **I2C** | `0x30-0x3F` | Open/close bus, speed config (100k/400k/1M), 7/10-bit write/read, combined write-read (repeated start), bus scan |
| **Network Config** | `0x40-0x4F` | Static IP / DHCP, status query, DNS resolution, link-state event reporting |
| **TCP** | `0x50-0x5F` | Server open/close, client connect/disconnect, data send, receive/accept/disconnect events |
| **UDP** | `0x60-0x6F` | Server open/close, client create/delete, send via server or client, receive event |
| **WebSocket** | `0x70-0x7F` | Server open/close, client connect/disconnect, send (text/binary/ping/pong), receive/disconnect events |
| **GPIO** | `0x80-0x8F` | Pin direction, output/input, pull-up/down, interrupt enable with trigger config, mask write, full read (rate-limited at 50 Hz/pin) |
| **Bulk Transfer** | `0x90-0x9F` | Start/stop bulk session, data frames with sliding-window ACK/NACK and retransmission |
| **UART Extension** | `0xA0-0xAF` | Open/close port, config (baud/data/parity/flow), data send, 4 receive modes (passive/line/fixed-length/timeout), break, flush, status |
| **OTA** | `0xB0-0xBF` | Begin (SHA-256), data blocks with CRC chunk verification, end & verify, progress query, rollback, dual-partition info |

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
| **Transport (MCP)** | ✅ Done | UART1 921600 bps RX/TX with frame assembly |
| **System (0x00-0x0F)** | ✅ Base | PING, GET_INFO implemented |
| **UART Extension (0xA0-0xAF)** | ✅ Complete | All 8 commands, 57 test cases — 173 pass / 0 fail / 2 skip |
| **CAN FD** | ☐ Planned | MCP2518FD via SPI, pinout assigned |
| **SPI** | ☐ Planned | — |
| **I2C** | ☐ Planned | 24C02 EEPROM, pinout assigned |
| **Network / TCP / UDP / WS** | ☐ Planned | LAN8720 RMII PHY, pinout assigned |
| **GPIO** | ☐ Planned | — |
| **Bulk Transfer** | ☐ Planned | — |
| **OTA** | ☐ Planned | Dual-partition with SHA-256 verification |

---

## Hardware

| Peripheral | Pins | Notes |
|:---|:---|:---|
| CAN FD (MCP2518FD) | SCK=14, MOSI=13, MISO=36, CS=15, INT=39 | SPI-attached, CS on strapping pin (10 kΩ pull-up) |
| I2C (EEPROM 24C02) | SCL=12, SDA=33 | GPIO12=MTDI, 4.7 kΩ pull-up required for boot |
| Ethernet (LAN8720) | RMII fixed pins, PHY_RST=5 | MDC=23, MDIO=18 |
| UART1 (MCP) | TX=4, RX=34 | RX is GPI only, external 10 kΩ pull-up |
| UART2 (ext) | TX=32, RX=35 | RX is GPI only, external 10 kΩ pull-up |
| UART0 (debug) | TX=1, RX=3 | Default ESP32 debug UART |

---

## Build & Flash

```bash
# Build
idf.py build

# Flash (replace COMx with actual port)
idf.py -p COM35 flash

# Monitor debug output
idf.py -p COM34 monitor
```

FW version `0.1.0`, model ID `HXB1`, target `esp32`.
