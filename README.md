# HEX-Bridge

**English** | [中文](./README_zh.md)

HEX-Bridge is firmware for a classic ESP32 board. It bridges host-side tools to hardware interfaces over UBCP v2.0 and provides a separate CMSIS-DAP over TCP probe for SWD debugging.

The firmware supports an external SPI master, classic CAN and CAN FD through an MCP2518FD, UART2, Wi-Fi networking, and the HEX-Bridge network debug probe. Device profile v2 lets the external SPI device and MCP2518FD select SPI2 or SPI3 independently; their defaults remain SPI2 and SPI3.

## Current capabilities

Device profiles configure feature switches and peripheral pins over UBCP. UART1 control (GPIO4/34) and UART0 programming (GPIO1/3) have fixed assignments. The shared Python CLI and Tkinter tool support export, validation, staging, a reboot trial and confirmation. Profiles retain UART1 or Wi-Fi STA plus TCP 9500 and saved usable network settings. Ordinary TCP services do not provide profile management. WIFI_FORGET is rejected if either the active or confirmed rollback profile relies on Wi-Fi-only management; confirmation waits for required driver initialization and validates the control session and required entry point. See the [device profile protocol and partition upgrade instructions](files/design/protocol/17-Device-Profile.md).

| Feature | Interface | Status |
|:---|:---|:---|
| UBCP control | UART1 or one Wi-Fi TCP client on port `9500` | TCP takes over the UBCP session while connected. After Wi-Fi loss, UART1 resumes control if enabled. |
| CAN / CAN FD | MCP2518FD over SPI | Implemented. UBCP commands cover channel control, timing, transmit/receive, filters, status, and bus events. |
| External UART | UART2 (channel 1), optional UART1 (channel 2) | Profile v4 lets you turn off UART1 control and enable ordinary serial I/O on GPIO4/34. Use Wi-Fi TCP 9500 for management. Each data channel has independent serial settings, send/receive, status, flush and break control. |
| Wi-Fi STA | ESP32 2.4 GHz radio | Implemented. IPv4 DHCP/static configuration, DNS, provisioning through UBCP, and reconnect handling. TCP, UDP, and WebSocket services are managed through UBCP. |
| DAPLink | CMSIS-DAP over TCP `4441` | Implemented for SWD. This is the ESP32 probe, not the Nucleo board's ST-LINK and not USB HID DAPLink. |
| External SPI master | Selectable SPI2 / SPI3 | Profile v3 supports two independently opened devices (channels 4 and 5). Both hosts can run ordinary SPI with CAN FD disabled. Each device may use CS or occupy a host exclusively without CS. Devices sharing a host use separate automatic chip selects. |
| SPI slave | SPI2 (channel 6), SPI3 (channel 7) | Profile v5 selects master or slave independently per controller. In slave mode, preload 1–64 bytes, let the external master clock one Mode 0 transaction, then fetch the received bytes and actual bit count. |
| I2C, GPIO, bulk transfer, OTA | Reserved command ranges | Host-accessible modules are pending. |

See the [firmware design index](files/design/firmware/README.md), [Wi-Fi design](files/design/firmware/06-WiFi-STA.md), and [DAPLink design and test record](files/design/firmware/08-DAPLink.md) for implementation details and limitations.

## Planned optional peripherals

Stage 1 extends the existing drivers with profile v2; host verification and remaining board checks are recorded in the [Stage 1 delivery evidence](files/design/test-report/Stage1-Peripheral-Delivery.md). Each build will advertise the instances, channels and pin assignments it supports. Every profile must retain UART1 control or the Wi-Fi UBCP management service on TCP port 9500.

| Stage | Planned support |
|---|---|
| 1 · Existing interfaces | Preserve UART1 control, UART2, Wi-Fi, DAP/SWD and MCP2518FD operation. Make SPI2 and SPI3 independently selectable and configurable. Let users attach the external SPI function and the MCP2518FD to either host; SPI3 remains the CAN FD default. |
| 2 · Digital I/O and buses | Optional digital GPIO, two independent I2C controllers (I2C0/I2C1), and native classic CAN (TWAI) with an external transceiver. TWAI and MCP2518FD CAN FD have separate enable switches. |
| 3 · Waveforms and counting | Up to 16 individually selectable LEDC PWM channels, motor PWM (MCPWM), and eight individually selectable pulse-counter units (PCNT). Concurrent use depends on available pins and shared hardware resources. |
| 4 · Wired networking | Optional Ethernet MAC on board variants with a compatible PHY, clock and RMII routing. |

Legacy v1 reports nine configurable HXB1 GPIOs; v2 reports 15, including the former fixed SPI2 pins. A single-width enabled bus reserves SCLK/MOSI/MISO; Quad reserves IO0-IO3 as bidirectional data pins. The configured maximum width determines reservation even during a single-line transfer. With default wiring and the original nine signals enabled, external single-width SPI uses 13 pins (GPIO22/23 free), Quad uses 15, and disabling external SPI plus its unused host restores nine occupied pins. Enabled hosts reserve their bus pins even without attached devices. Old records preserve the external SPI2 Quad route and CAN settings; v1 writes that would discard v2 fields are rejected. See the [peripheral and profile design](files/design/function/08-device-profile.md) and [default board wiring](files/sch/esp32-pinout-design.md).

## Architecture

```text
Host MCP client ── UBCP over UART1 (115200) ──────┐
              └── UBCP over Wi-Fi TCP (9500) ────┤
                                                  ▼
                                              HEX-Bridge
                                              ESP32 firmware
                                                ├─ MCP2518FD CAN FD
                                                ├─ External UART2
                                                ├─ Wi-Fi TCP / UDP / WebSocket services
                                                └─ CMSIS-DAP over TCP (4441)
                                                       │ SWD
                                                       └─ Target MCU
```

UBCP uses UART1 by default. When a TCP client takes the UBCP session on port `9500`, that client becomes the active host; only one active UBCP transport is allowed at a time. The independent DAP service listens on port `4441` after Wi-Fi has a usable IP address and allows one active debug client.

## Hardware connections

| Function | ESP32 pins | Notes |
|:---|:---|:---|
| UBCP UART1 | TX GPIO4, RX GPIO34 | 115200 bps by default; GPIO34 is input-only and requires the board's RX biasing. |
| External UART2 | TX GPIO32, RX GPIO35 | 115200 bps by default; GPIO35 is input-only. |
| MCP2518FD SPI | SCK GPIO14, MOSI GPIO13, MISO GPIO36, CS GPIO15, INT GPIO39 | SPI is used by the CAN module. Observe ESP32 strapping-pin requirements. |
| DAPLink SWD | SWCLK GPIO25, SWDIO GPIO26 | Connect to a 3.3 V target and share ground. GPIO27 reset is disabled by default. |
| Wi-Fi | Integrated ESP32 radio | 2.4 GHz station mode. |

## DAPLink

The probe speaks CMSIS-DAP over the HEX-Bridge TCP framing protocol on port `4441`. It declares SWD support only; JTAG, SWO, USB HID/Bulk, and a hardware reset line are not provided. The GPIO SWD clock defaults to about 100 kHz and accepts requests up to 250 kHz; actual GPIO timing can be slower.

On 2026-11-20, the probe was tested with OpenOCD `v0.12.0-esp32-20260424` against a NUCLEO-F103RB (MB1136 C-04, STM32F103RBT6) connected directly to CN7: target DP IDCODE `0x1BA01477`, target examination, halt, PC/SP register reads, resume, and download plus verify of `demo-firmware/demo.bin` succeeded. The 560-byte image took 2.728 seconds for the OpenOCD program-and-verify command at a requested 250 kHz SWD clock (about 205 B/s including flash erase and verification). This is a result for that setup and tool version, not a general compatibility guarantee or raw TCP throughput measurement.

The Nucleo's onboard ST-LINK is a separate probe. For HEX-Bridge direct SWD, connect GPIO25 to CN7 pin 15 (PA14/SWCLK), GPIO26 to CN7 pin 13 (PA13/SWDIO), and ground to CN7 pin 8. The DAPLink design record lists additional unverified behavior and test evidence.

## Build

Build for the classic ESP32 with ESP-IDF 6.0.x (the project workbench currently uses v6.0.2):

```sh
idf.py set-target esp32
idf.py build
```

The default output directory is `build/`; the application image is `build/hex-bridge.bin`. Use the ESP-IDF export/setup step for your host before invoking `idf.py`.

## Firmware and protocol versions

- UBCP protocol: v2.0.
- Application firmware version reported by the System module: `0.1.0`.
- DAP `Info` firmware field: `2.0.0` (separate from the application firmware version).
- Target: classic ESP32 (`esp32`).

## Tests and documentation

- [Stage 1 peripheral delivery evidence](files/design/test-report/Stage1-Peripheral-Delivery.md)
- [DAPLink implementation and real-board test record](files/design/firmware/08-DAPLink.md)
- [Wi-Fi STA design](files/design/firmware/06-WiFi-STA.md)
- [CAN FD protocol](files/design/protocol/04-CAN.md)
- [CAN test plan and reports](files/design/test/05-CAN-Tests.md)
- [Firmware design index](files/design/firmware/README.md)
