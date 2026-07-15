#!/usr/bin/env node
/**
 * hex-bridge-uart-cli.js — HEX-Bridge UART 扩展口 CLI 工具
 *
 * 通过 MCP 通信口 (UART1, 默认 COM35 @ 921600 bps) 发送 UBCP v2.0 协议命令，
 * 控制 ESP32 上的 UART2 扩展口 (GPIO32/GPIO35)，实现远程串口收发。
 *
 * ============================================================================
 * 使用示例 (Usage Examples)
 * ============================================================================
 *
 * # 1. 安装依赖
 *    npm install serialport
 *
 * # 2. 打开 UART 通道 (被动上报模式)
 *    node hex-bridge-uart-cli.js --port COM35 open --rxmode passive
 *
 * # 3. 配置扩展口波特率为 115200 8N1
 *    node hex-bridge-uart-cli.js --port COM35 config --baud 115200
 *
 * # 4. 发送 hex 数据
 *    node hex-bridge-uart-cli.js --port COM35 send --hex "48 65 6C 6C 6F"
 *
 * # 5. 发送字符串
 *    node hex-bridge-uart-cli.js --port COM35 send --text "Hello World\r\n"
 *
 * # 6. 持续接收数据 (默认 10 秒)
 *    node hex-bridge-uart-cli.js --port COM35 recv --timeout 10
 *
 * # 7. 查看 UART 状态
 *    node hex-bridge-uart-cli.js --port COM35 status
 *
 * # 8. 发送 Break 信号 100ms
 *    node hex-bridge-uart-cli.js --port COM35 break --duration 100
 *
 * # 9. 清空 RX 缓冲区
 *    node hex-bridge-uart-cli.js --port COM35 flush --type rx
 *
 * # 10. 发送数据后等待回显
 *     node hex-bridge-uart-cli.js --port COM35 sendrecv --text "AT\r\n" --timeout 3
 *
 * # 11. 一键完整流程 (打开→配置→收发→关闭)
 *     node hex-bridge-uart-cli.js --port COM35 quick --text "ping\r\n" --timeout 3
 *
 * # 12. 使用自定义 channel 和序列号起始值
 *     node hex-bridge-uart-cli.js --port COM35 --channel 1 --seq 100 open --rxmode line
 *
 * # 13. 交互模式
 *     node hex-bridge-uart-cli.js --port COM35 interactive
 *
 * ============================================================================
 * 硬件连接说明
 * ============================================================================
 *
 *   上位机                    ESP32 HEX-Bridge
 *   ┌──────┐                  ┌──────────────┐
 *   │ COM35├──────────────────┤UART1(MCP通信) │  GPIO4(TX), GPIO34(RX)
 *   │      │   921600 8N1     │              │
 *   │      │                  │  UART2(扩展口) │  GPIO32(TX), GPIO35(RX)
 *   │      │                  └──────┬───────┘
 *   └──────┘                         │
 *                              ┌─────┴─────┐
 *                              │  目标设备   │
 *                              └───────────┘
 *
 * ============================================================================
 * RxMode 说明
 * ============================================================================
 *
 *   passive (0x00) — 被动模式：收到数据立即上报
 *   line    (0x01) — 行模式：  缓冲到 \n 或 \r\n 后上报
 *   fixed   (0x02) — 定长模式：累积到指定字节数后上报 (需配合 --threshold)
 *   timeout (0x03) — 超时模式：首字节后空闲超时即上报 (需配合 --rx-timeout)
 */

'use strict';

/* ========================================================================
 * CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF)
 * ======================================================================== */

const CRC16_TABLE = [
  0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
  0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
  0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
  0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
  0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
  0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
  0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
  0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
  0x4864, 0x5845, 0x6826, 0x7807, 0x08E0, 0x18C1, 0x28A2, 0x38A3,
  0xC94C, 0xD96D, 0xE90E, 0xF92F, 0x89C8, 0x99E9, 0xA98A, 0xB9AB,
  0x5A75, 0x4A54, 0x7A37, 0x6A16, 0x1AF1, 0x0AD0, 0x3AB3, 0x2A92,
  0xDB7D, 0xCB5C, 0xFB3F, 0xEB1E, 0x9BF9, 0x8BD8, 0xBBBB, 0xAB9A,
  0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
  0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
  0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
  0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
  0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
  0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
  0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
  0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
  0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
  0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
  0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
  0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
  0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
  0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
  0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBBAA,
  0x4A45, 0x5A64, 0x6A07, 0x7A26, 0x0AC1, 0x1AE0, 0x2A83, 0x3AA2,
  0xFD3E, 0xED1F, 0xDD7C, 0xCD5D, 0xBDBA, 0xAD9B, 0x9DF8, 0x8DD9,
  0x7C36, 0x6C17, 0x5C74, 0x4C55, 0x3CB2, 0x2C93, 0x1CF0, 0x0CD1,
  0xEF0F, 0xFF2E, 0xCF4D, 0xDF6C, 0xAF8B, 0xBFAA, 0x8FC9, 0x9FE8,
  0x6E07, 0x7E26, 0x4E45, 0x5E64, 0x2E83, 0x3EA2, 0x0EC1, 0x1EE0,
];

function crc16_update(crc, byte) {
  return ((crc << 8) & 0xFFFF) ^ CRC16_TABLE[((crc >> 8) ^ byte) & 0xFF];
}

function crc16_calc(data) {
  let crc = 0xFFFF;
  for (let i = 0; i < data.length; i++) {
    crc = crc16_update(crc, data[i]);
  }
  return crc;
}

/* ========================================================================
 * UBCP v2.0 协议常量
 * ======================================================================== */

const SOF_0   = 0xAA;
const SOF_1   = 0x55;
const EOF_B   = 0x7E;
const ESC     = 0x7D;
const ESC_EOF = 0x5E;
const ESC_ESC = 0x5D;

const VERSION = 0x02;
const FLAG_DIR = 0x80;
const FLAG_ACK = 0x40;
const FLAG_TS  = 0x20;
const FLAG_EVT = 0x10;
const FLAG_FRAG = 0x08;

const UBCP_MAX_PAYLOAD_LEN = 2048;

const CMD_PING        = 0x00;
const CMD_GET_INFO    = 0x01;
const CMD_FLOW_CTRL   = 0x05;
const CMD_UART_OPEN   = 0xA0;
const CMD_UART_CLOSE  = 0xA1;
const CMD_UART_CONFIG = 0xA2;
const CMD_UART_SEND   = 0xA3;
const CMD_UART_RECV   = 0xA4;
const CMD_UART_BREAK  = 0xA5;
const CMD_UART_STATUS = 0xA6;
const CMD_UART_FLUSH  = 0xA7;

const RXMODE_PASSIVE = 0x00;
const RXMODE_LINE    = 0x01;
const RXMODE_FIXED   = 0x02;
const RXMODE_TIMEOUT = 0x03;

const FLUSH_RX    = 0x00;
const FLUSH_TX    = 0x01;
const FLUSH_ALL   = 0x02;
const FLUSH_DRAIN = 0x03;

const ERR_SUCCESS   = 0x00;
const ERR_NOT_OPEN  = 0x05;
const ERR_BUSY      = 0x04;

const ERROR_NAMES = {
  0x00: 'SUCCESS', 0x01: 'ERR_UNKNOWN', 0x02: 'ERR_PARAM',
  0x03: 'ERR_TIMEOUT', 0x04: 'ERR_BUSY', 0x05: 'ERR_NOT_OPEN',
  0x06: 'ERR_NOT_SUPPORT', 0x07: 'ERR_BUFFER_FULL', 0x08: 'ERR_CRC',
  0x09: 'ERR_FRAME', 0x0A: 'ERR_CHANNEL_INVALID', 0x0B: 'ERR_ALREADY_OPEN',
  0x0C: 'ERR_PERMISSION', 0x0D: 'ERR_OVERFLOW', 0x0E: 'ERR_SEQ_MISMATCH',
  0x0F: 'ERR_VERSION', 0xA0: 'ERR_UART_PARITY', 0xA1: 'ERR_UART_FRAME',
  0xA2: 'ERR_UART_OVERFLOW', 0xA3: 'ERR_UART_BAUD', 0xA4: 'ERR_UART_BREAK',
};

/* ========================================================================
 * UBCP Frame Builder
 * ======================================================================== */

function build_request(seqNum, cmdCode, channelId, payload) {
  return _build(FLAG_ACK, seqNum, cmdCode, channelId, payload);
}

function _build(flags, seqNum, cmdCode, channelId, payload) {
  const header = Buffer.from([
    VERSION,
    flags,
    (seqNum >> 8) & 0xFF,
    seqNum & 0xFF,
    cmdCode,
    channelId,
    (payload.length >> 8) & 0xFF,
    payload.length & 0xFF,
  ]);
  const raw = Buffer.concat([header, payload]);
  const crc = crc16_calc(raw);
  const crcBytes = Buffer.from([(crc >> 8) & 0xFF, crc & 0xFF]);

  const parts = [Buffer.from([SOF_0, SOF_1])];
  parts.push(_write_escaped(Buffer.concat([raw, crcBytes])));
  parts.push(Buffer.from([EOF_B]));
  return Buffer.concat(parts);
}

function _write_escaped(data) {
  const chunks = [];
  let start = 0;
  for (let i = 0; i < data.length; i++) {
    const b = data[i];
    if (b === EOF_B || b === ESC) {
      if (i > start) chunks.push(data.slice(start, i));
      if (b === EOF_B) chunks.push(Buffer.from([ESC, ESC_EOF]));
      else chunks.push(Buffer.from([ESC, ESC_ESC]));
      start = i + 1;
    }
  }
  if (start < data.length) chunks.push(data.slice(start));
  return Buffer.concat(chunks);
}

/* ========================================================================
 * UBCP Frame Parser (streaming state machine)
 * ======================================================================== */

const STATE_WAIT_SOF_0 = 0;
const STATE_WAIT_SOF_1 = 1;
const STATE_RECEIVING  = 2;

class UBCPParser {
  constructor() {
    this.reset();
  }

  reset() {
    this._state = STATE_WAIT_SOF_0;
    this._escaped = false;
    this._crc = 0xFFFF;
    this._buf = [];
  }

  feed(byte) {
    if (this._state === STATE_WAIT_SOF_0) {
      if (byte === SOF_0) this._state = STATE_WAIT_SOF_1;
      return null;
    }

    if (this._state === STATE_WAIT_SOF_1) {
      if (byte === SOF_1) {
        this._state = STATE_RECEIVING;
        this._escaped = false;
        this._crc = 0xFFFF;
        this._buf = [];
      } else if (byte !== SOF_0) {
        this._state = STATE_WAIT_SOF_0;
      }
      return null;
    }

    if (!this._escaped && byte === EOF_B) {
      if (this._buf.length < 10) { this.reset(); return null; }
      if (this._crc !== 0x0000) { this.reset(); return null; }
      this._state = STATE_WAIT_SOF_0;
      return this._extractFrame();
    }

    if (this._escaped) {
      this._escaped = false;
      if (byte === ESC_EOF) byte = EOF_B;
      else if (byte === ESC_ESC) byte = ESC;
      else { this.reset(); return null; }
    } else if (byte === ESC) {
      this._escaped = true;
      return null;
    }

    this._buf.push(byte);
    this._crc = crc16_update(this._crc, byte);
    return null;
  }

  _extractFrame() {
    const b = this._buf;
    const frame = {
      version:    b[0],
      flags:      b[1],
      seqNum:     (b[2] << 8) | b[3],
      cmdCode:    b[4],
      channelId:  b[5],
      payloadLen: (b[6] << 8) | b[7],
      timestamp:  0,
      hasTimestamp: !!(b[1] & FLAG_TS),
      payload:    null,
    };

    const plStart = frame.hasTimestamp ? 12 : 8;
    if (frame.hasTimestamp) {
      frame.timestamp = (b[8] << 24) | (b[9] << 16) | (b[10] << 8) | b[11];
    }
    frame.payload = Buffer.from(b.slice(plStart, b.length - 2));
    frame.isResponse = !!(frame.flags & FLAG_DIR);
    frame.isEvent = !!(frame.flags & FLAG_EVT);
    return frame;
  }
}

/* ========================================================================
 * Serial Transport
 * ======================================================================== */

class HexBridgeTransport {
  constructor(port, baudRate) {
    this.port = port;
    this.baudRate = baudRate;
    this.parser = new UBCPParser();
    this.serial = null;
    this._pending = null;
    this._eventPending = null;
  }

  async open() {
    const { SerialPort } = require('serialport');
    this.serial = new SerialPort({
      path: this.port,
      baudRate: this.baudRate,
      dataBits: 8,
      parity: 'none',
      stopBits: 1,
    });
    this.parser.reset();

    await new Promise((resolve, reject) => {
      this.serial.on('open', resolve);
      this.serial.on('error', reject);
      if (this.serial.isOpen) resolve();
    });

    this.serial.on('data', (buf) => {
      for (let i = 0; i < buf.length; i++) {
        const frame = this.parser.feed(buf[i]);
        if (!frame) continue;
        if (frame.isEvent && this._eventPending) {
          const cmdMatch = this._eventPending.cmdCode === null
            || frame.cmdCode === this._eventPending.cmdCode;
          if (cmdMatch) {
            const ep = this._eventPending;
            this._eventPending = null;
            clearTimeout(ep._timer);
            ep.resolve(frame);
          }
        }
        if (this._pending && !frame.isEvent) {
          const p = this._pending;
          this._pending = null;
          clearTimeout(p._timer);
          p.resolve(frame);
        }
      }
    });

    console.error(`[INFO] 已打开 ${this.port} @ ${this.baudRate} 8N1`);
  }

  close() {
    if (this.serial && this.serial.isOpen) {
      this.serial.close();
      console.error(`[INFO] 已关闭 ${this.port}`);
    }
    if (this._pending) {
      clearTimeout(this._pending._timer);
      this._pending.reject(new Error('Transport closed'));
      this._pending = null;
    }
    if (this._eventPending) {
      clearTimeout(this._eventPending._timer);
      this._eventPending.reject(new Error('Transport closed'));
      this._eventPending = null;
    }
  }

  sendSync(data) {
    this.serial.write(data);
    this.serial.drain();
  }

  sendReq(seqNum, cmdCode, channelId, payload) {
    const wire = build_request(seqNum, cmdCode, channelId, payload);
    this.sendSync(wire);
  }

  async recvFrame(timeoutMs) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._pending = null;
        resolve(null);
      }, timeoutMs);
      this._pending = { resolve, reject, _timer: timer };
    });
  }

  async recvEvent(cmdCode, timeoutMs) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._eventPending = null;
        resolve(null);
      }, timeoutMs);
      this._eventPending = { resolve, reject, _timer: timer, cmdCode };
    });
  }

  flushInput() {
    if (this.serial) this.serial.flush();
    this.parser.reset();
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/* ========================================================================
 * 命令实现
 * ======================================================================== */

async function cmdPing(transport, seq, channel) {
  transport.sendReq(seq, CMD_PING, channel, Buffer.alloc(0));
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('PING 超时无响应');
  if (!resp.isResponse) throw new Error('PING 响应方向错误');
  return resp;
}

async function cmdGetInfo(transport, seq, channel) {
  transport.sendReq(seq, CMD_GET_INFO, channel, Buffer.alloc(0));
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('GET_INFO 超时无响应');
  if (!resp.isResponse) throw new Error('GET_INFO 响应方向错误');
  return resp;
}

async function cmdUartOpen(transport, seq, channel, rxMode) {
  transport.sendReq(seq, CMD_UART_OPEN, channel, Buffer.from([rxMode]));
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('UART_OPEN 超时无响应');
  if (!resp.isResponse) throw new Error('UART_OPEN 响应方向错误');
  return resp;
}

async function cmdUartClose(transport, seq, channel) {
  transport.sendReq(seq, CMD_UART_CLOSE, channel, Buffer.alloc(0));
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('UART_CLOSE 超时无响应');
  if (!resp.isResponse) throw new Error('UART_CLOSE 响应方向错误');
  return resp;
}

async function cmdUartConfig(transport, seq, channel, opts) {
  const payload = Buffer.alloc(11);
  payload.writeUInt32BE(opts.baudRate, 0);
  payload[4] = opts.dataBits;
  payload[5] = opts.stopBits;
  payload[6] = opts.parity;
  payload[7] = opts.flowControl;
  payload.writeUInt16BE(opts.rxThreshold, 8);
  payload[10] = opts.rxTimeout;
  transport.sendReq(seq, CMD_UART_CONFIG, channel, payload);
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('UART_CONFIG 超时无响应');
  if (!resp.isResponse) throw new Error('UART_CONFIG 响应方向错误');
  return resp;
}

async function cmdUartSend(transport, seq, channel, data) {
  const payload = Buffer.alloc(2 + data.length);
  payload.writeUInt16BE(data.length, 0);
  data.copy(payload, 2);
  transport.sendReq(seq, CMD_UART_SEND, channel, payload);
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('UART_SEND 超时无响应');
  if (!resp.isResponse) throw new Error('UART_SEND 响应方向错误');
  return resp;
}

async function cmdUartRecv(transport, seq, channel, timeoutMs) {
  const frame = await transport.recvEvent(CMD_UART_RECV, timeoutMs);
  if (!frame) throw new Error('UART_RECV 超时未收到数据');
  return frame;
}

async function cmdUartStatus(transport, seq, channel) {
  transport.sendReq(seq, CMD_UART_STATUS, channel, Buffer.alloc(0));
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('UART_STATUS 超时无响应');
  if (!resp.isResponse) throw new Error('UART_STATUS 响应方向错误');
  return resp;
}

async function cmdUartBreak(transport, seq, channel, durationMs) {
  const payload = Buffer.alloc(2);
  payload.writeUInt16BE(durationMs, 0);
  transport.sendReq(seq, CMD_UART_BREAK, channel, payload);
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('UART_BREAK 超时无响应');
  if (!resp.isResponse) throw new Error('UART_BREAK 响应方向错误');
  return resp;
}

async function cmdUartFlush(transport, seq, channel, flushType) {
  transport.sendReq(seq, CMD_UART_FLUSH, channel, Buffer.from([flushType]));
  const resp = await transport.recvFrame(2000);
  if (!resp) throw new Error('UART_FLUSH 超时无响应');
  if (!resp.isResponse) throw new Error('UART_FLUSH 响应方向错误');
  return resp;
}

/* ========================================================================
 * 响应解析与格式化
 * ======================================================================== */

function fmtFrame(frame, label) {
  let s = label ? `[${label}] ` : '';
  const dir = frame.isResponse ? 'RSP' : 'REQ';
  const evt = frame.isEvent ? ' EVT' : '';
  s += `${dir}${evt} seq=${frame.seqNum.toString(16).padStart(4, '0').toUpperCase()} `;
  s += `cmd=${frame.cmdCode.toString(16).padStart(2, '0').toUpperCase()} `;
  s += `ch=${frame.channelId.toString(16).padStart(2, '0').toUpperCase()} `;
  s += `plen=${frame.payloadLen}`;
  return s;
}

function checkStatus(resp) {
  if (!resp || !resp.isResponse) return -1;
  const status = resp.payload[0];
  const name = ERROR_NAMES[status] || `0x${status.toString(16).padStart(2, '0').toUpperCase()}`;
  if (status !== ERR_SUCCESS) {
    console.error(`[FAIL] ${fmtFrame(resp, 'RSP')} status=${status} (${name})`);
  }
  return status;
}

function parseStatusOnly(resp) {
  return { status: resp.payload.length > 0 ? resp.payload[0] : -1 };
}

function parseUartStatus(resp) {
  const p = resp.payload;
  if (p.length < 19) return parseStatusOnly(resp);
  return {
    status:   p[0],
    baudRate: p.readUInt32BE(1),
    lineState: {
      txIdle:   !!(p[5] & 0x01),
      rxActive: !!(p[5] & 0x02),
    },
    txBufUsed:  p.readUInt16BE(6),
    rxBufUsed:  p.readUInt16BE(8),
    txTotal:    p.readUInt32BE(10),
    rxTotal:    p.readUInt32BE(14),
    errorCount: p[18],
  };
}

function parseUartOpen(resp) {
  const p = resp.payload;
  if (p.length < 5) return parseStatusOnly(resp);
  return {
    status:    p[0],
    rxBufSize: p.readUInt16BE(1),
    txBufSize: p.readUInt16BE(3),
  };
}

function parseUartConfig(resp) {
  const p = resp.payload;
  if (p.length < 5) return parseStatusOnly(resp);
  return {
    status:     p[0],
    actualBaud: p.readUInt32BE(1),
  };
}

function parseUartSend(resp) {
  const p = resp.payload;
  if (p.length < 3) return parseStatusOnly(resp);
  return {
    status:    p[0],
    actualLen: p.readUInt16BE(1),
  };
}

function parseUartRecv(frame) {
  const p = frame.payload;
  if (p.length < 3) return { dataLen: 0, data: Buffer.alloc(0), rxFlags: { bufferOverflow: false, parityError: false, frameError: false, breakDetect: false } };
  const rxFlags = p[0];
  const dataLen = (p[1] << 8) | p[2];
  const data = p.slice(3, 3 + dataLen);
  return {
    rxFlags: {
      bufferOverflow: !!(rxFlags & 0x01),
      parityError:    !!(rxFlags & 0x02),
      frameError:     !!(rxFlags & 0x04),
      breakDetect:    !!(rxFlags & 0x08),
    },
    dataLen,
    data,
  };
}

/* ========================================================================
 * CLI 参数解析 (简单 argv 解析，无外部依赖)
 * ======================================================================== */

function parseArgs(argv) {
  const args = argv.slice(2);
  const result = {
    port: 'COM35',
    mcpBaud: 921600,
    channel: 0,
    seqStart: 1,
    extBaud: 115200,
    dataBits: 8,
    stopBits: 1,
    parity: 0,
    flowControl: 0,
    rxMode: 'passive',
    rxThreshold: 0,
    rxTimeout: 50,
    command: null,
    cmdArgs: {},
    help: false,
  };

  let i = 0;
  while (i < args.length) {
    const arg = args[i];
    switch (arg) {
      case '--port':
        result.port = args[++i]; break;
      case '--mcp-baud':
        result.mcpBaud = parseInt(args[++i], 10); break;
      case '--channel':
        result.channel = parseInt(args[++i], 10); break;
      case '--seq':
        result.seqStart = parseInt(args[++i], 10); break;
      case '--ext-baud':
        result.extBaud = parseInt(args[++i], 10); break;
      case '--data-bits':
        result.dataBits = parseInt(args[++i], 10); break;
      case '--stop-bits':
        result.stopBits = parseFloat(args[++i]); break;
      case '--parity':
        result.parity = args[++i]; break;
      case '--rxmode':
      case '--rx-mode':
        result.rxMode = args[++i]; break;
      case '--threshold':
        result.rxThreshold = parseInt(args[++i], 10); break;
      case '--rx-timeout':
        result.rxTimeout = parseInt(args[++i], 10); break;
      case '--timeout':
        result.cmdArgs.timeout = parseFloat(args[++i]); break;
      case '--hex':
        result.cmdArgs.hexData = args[++i]; break;
      case '--text':
        result.cmdArgs.textData = args[++i]; break;
      case '--baud':
        result.cmdArgs.baud = parseInt(args[++i], 10); break;
      case '--duration':
        result.cmdArgs.duration = parseInt(args[++i], 10); break;
      case '--type':
        result.cmdArgs.flushType = args[++i]; break;
      case '--help':
      case '-h':
        result.help = true; break;
      default:
        if (arg.startsWith('-')) {
          console.error(`未知选项: ${arg}`);
          result.help = true;
        } else if (!result.command) {
          result.command = arg;
        } else {
          if (!result.cmdArgs.extra) result.cmdArgs.extra = [];
          result.cmdArgs.extra.push(arg);
        }
        break;
    }
    i++;
  }

  return result;
}

function parseRxMode(s) {
  const m = (s || '').toLowerCase();
  const map = { passive: 0, line: 1, fixed: 2, timeout: 3 };
  if (m in map) return map[m];
  return parseInt(m, 10);
}

function parseParity(s) {
  if (typeof s === 'number') return s;
  const map = { none: 0, odd: 1, even: 2 };
  if (s && s.toLowerCase() in map) return map[s.toLowerCase()];
  return 0;
}

function parseStopBits(s) {
  if (s === 1.5 || s === '1.5') return 2;
  if (s === 1) return 1;
  if (s === 2) return 3;
  return 1;
}

function parseFlushType(s) {
  const map = { rx: 0, tx: 1, all: 2, drain: 3 };
  if (s && s.toLowerCase() in map) return map[s.toLowerCase()];
  return parseInt(s, 10) || 0;
}

function parseHex(hexStr) {
  const cleaned = hexStr.replace(/[\s,;:]/g, '');
  if (cleaned.length % 2 !== 0) throw new Error(`hex 字符串长度需为偶数: "${hexStr}"`);
  return Buffer.from(cleaned, 'hex');
}

function bufferToPrintable(buf) {
  let s = '';
  for (let i = 0; i < buf.length; i++) {
    const b = buf[i];
    if (b >= 0x20 && b <= 0x7E) s += String.fromCharCode(b);
    else if (b === 0x0A) s += '\\n';
    else if (b === 0x0D) s += '\\r';
    else if (b === 0x09) s += '\\t';
  }
  return s;
}

/* ========================================================================
 * 使用说明
 * ======================================================================== */

function printHelp() {
  console.log(`
hex-bridge-uart-cli.js — HEX-Bridge UART 扩展口 CLI 工具

用法:
  node hex-bridge-uart-cli.js [全局选项] <命令> [命令选项]

全局选项:
  --port <COM>          MCP 通信串口 (默认: COM35)
  --mcp-baud <baud>     MCP 波特率 (默认: 921600)
  --channel <n>         通道号 (默认: 0)
  --seq <n>             起始序列号 (默认: 1)
  --ext-baud <baud>     扩展口默认波特率 (默认: 115200)
  --data-bits <5|6|7|8> 数据位 (默认: 8)
  --stop-bits <1|1.5|2> 停止位 (默认: 1)
  --parity <none|odd|even> 校验位 (默认: none)
  --rxmode <mode>       接收模式 (默认: passive)
                        可选: passive line fixed timeout
  --threshold <n>       定长模式阈值 (默认: 0)
  --rx-timeout <n>      超时模式超时 ms (默认: 50)
  -h, --help            显示帮助

命令:
  ping                  测试设备连通性
  info                  获取设备信息
  open                  打开 UART 通道
    --rxmode <mode>     接收模式, 覆盖全局设置
    --threshold <n>     定长阈值
    --rx-timeout <ms>   超时时间
  close                 关闭 UART 通道
  config                配置 UART 参数
    --baud <baud>       波特率
    --data-bits <n>     数据位
    --stop-bits <n>     停止位
    --parity <mode>     校验位
  send                  发送数据
    --hex <hex>         hex 数据 (如 "48 65 6C 6C 6F")
    --text <str>        文本数据
  recv                  接收数据
    --timeout <s>       超时秒数 (默认: 10)
  status                查看 UART 状态
  break                 发送 Break 信号
    --duration <ms>     持续时间 ms (默认: 10)
  flush                 清空缓冲区
    --type <rx|tx|all|drain> 清空类型
  sendrecv              发送数据后等待回显
    --hex <hex> / --text <str>
    --timeout <s>       等待回显超时 (默认: 5)
  quick                 一键完整流程 (打开→配置→收发→关闭)
    --hex <hex> / --text <str>
    --timeout <s>       等待回显超时 (默认: 3)
  interactive           交互模式
`);
}

/* ========================================================================
 * 主流程
 * ======================================================================== */

async function main() {
  const opts = parseArgs(process.argv);

  if (opts.help || !opts.command) {
    printHelp();
    process.exit(opts.help ? 0 : 1);
  }

  let transport;
  try {
    transport = new HexBridgeTransport(opts.port, opts.mcpBaud);
    await transport.open();

    let seq = opts.seqStart;
    const nextSeq = () => { const s = seq; seq = (seq + 1) & 0xFFFE || 1; return s; };

    switch (opts.command) {
      /* ---------- ping ---------- */
      case 'ping': {
        const resp = await cmdPing(transport, nextSeq(), opts.channel);
        const status = resp.payload[0];
        console.log(`PING ${fmtFrame(resp)} status=${status}`);
        process.exit(status === 0 ? 0 : 1);
      }

      /* ---------- info ---------- */
      case 'info': {
        const resp = await cmdGetInfo(transport, nextSeq(), opts.channel);
        const p = resp.payload;
        const model = p.slice(0, 16).toString('utf8').replace(/\0/g, '');
        const fwVer = `${p[16]}.${p[17]}.${p[18]}`;
        const protoVer = p[19];
        const maxPayload = p.readUInt16BE(20);
        const caps = p.readUInt32BE(22);
        const capsStr = [];
        if (caps & 0x0010) capsStr.push('UART');

        console.log('=== HEX-Bridge 设备信息 ===');
        console.log(`  型号:       ${model}`);
        console.log(`  固件版本:   ${fwVer}`);
        console.log(`  协议版本:   0x${protoVer.toString(16).padStart(2, '0')}`);
        console.log(`  最大载荷:   ${maxPayload} bytes`);
        console.log(`  能力:       ${capsStr.join(', ')} (0x${caps.toString(16).padStart(8, '0').toUpperCase()})`);
        console.log(`  MCP 串口:   ${opts.port} @ ${opts.mcpBaud}`);
        break;
      }

      /* ---------- open ---------- */
      case 'open': {
        const rxMode = opts.cmdArgs.rxMode
          ? parseRxMode(opts.cmdArgs.rxMode) : parseRxMode(opts.rxMode);
        const rxModeNames = ['passive', 'line', 'fixed', 'timeout'];

        const resp = await cmdUartOpen(transport, nextSeq(), opts.channel, rxMode);
        const info = parseUartOpen(resp);
        const name = ERROR_NAMES[info.status] || `0x${info.status.toString(16)}`;
        console.log(`UART_OPEN 模式=${rxModeNames[rxMode]} status=${info.status} (${name})`);
        console.log(`  RX Buffer: ${info.rxBufSize} bytes`);
        console.log(`  TX Buffer: ${info.txBufSize} bytes`);
        process.exit(info.status === ERR_SUCCESS ? 0 : 1);
      }

      /* ---------- close ---------- */
      case 'close': {
        const resp = await cmdUartClose(transport, nextSeq(), opts.channel);
        const status = checkStatus(resp);
        console.log('UART_CLOSE 通道已关闭');
        process.exit(status === ERR_SUCCESS ? 0 : 1);
      }

      /* ---------- config ---------- */
      case 'config': {
        const cfgBaud = opts.cmdArgs.baud || opts.extBaud;
        const cfgDataBits = opts.cmdArgs.dataBits || opts.dataBits;
        const cfgStopBits = opts.cmdArgs.stopBits || opts.stopBits;
        const cfgParity = opts.cmdArgs.parity || opts.parity;
        const cfgThreshold = opts.cmdArgs.threshold || opts.rxThreshold;
        const cfgRxTimeout = opts.cmdArgs.rxTimeout || opts.rxTimeout;

        const resp = await cmdUartConfig(transport, nextSeq(), opts.channel, {
          baudRate: cfgBaud,
          dataBits: cfgDataBits,
          stopBits: parseStopBits(cfgStopBits),
          parity: parseParity(cfgParity),
          flowControl: opts.flowControl,
          rxThreshold: cfgThreshold,
          rxTimeout: cfgRxTimeout,
        });
        const info = parseUartConfig(resp);
        const name = ERROR_NAMES[info.status] || `0x${info.status.toString(16)}`;
        console.log(`UART_CONFIG 请求=${cfgBaud} 实际=${info.actualBaud} status=${info.status} (${name})`);
        process.exit(info.status === ERR_SUCCESS ? 0 : 1);
      }

      /* ---------- send ---------- */
      case 'send': {
        let data;
        if (opts.cmdArgs.hexData) {
          data = parseHex(opts.cmdArgs.hexData);
        } else if (opts.cmdArgs.textData) {
          data = Buffer.from(opts.cmdArgs.textData, 'utf8');
        } else {
          console.error('错误: send 需要 --hex 或 --text 参数');
          process.exit(1);
        }

        const resp = await cmdUartSend(transport, nextSeq(), opts.channel, data);
        const info = parseUartSend(resp);
        const name = ERROR_NAMES[info.status] || `0x${info.status.toString(16)}`;
        const actualLen = (info.status === ERR_SUCCESS) ? info.actualLen : data.length;
        console.log(`UART_SEND 发送=${info.actualLen !== undefined ? `${info.actualLen}/${data.length}B` : `${data.length}B`} hex=${data.toString('hex').toUpperCase()}`);
        if (data.length <= 256) {
          console.log(`  可打印: ${bufferToPrintable(data)}`);
        }
        console.log(`  status=${info.status} (${name})`);
        process.exit(info.status === ERR_SUCCESS ? 0 : 1);
      }

      /* ---------- recv ---------- */
      case 'recv': {
        const timeout = (opts.cmdArgs.timeout || 10) * 1000;
        console.log(`UART_RECV 等待接收数据 (超时 ${timeout / 1000}s)...`);

        const frame = await cmdUartRecv(transport, nextSeq(), opts.channel, timeout);
        const info = parseUartRecv(frame);

        const flags = [];
        if (info.rxFlags.bufferOverflow) flags.push('overflow');
        if (info.rxFlags.parityError) flags.push('parity_err');
        if (info.rxFlags.frameError) flags.push('frame_err');
        if (info.rxFlags.breakDetect) flags.push('break');
        const flagsStr = flags.length > 0 ? ` [${flags.join(', ')}]` : '';

        console.log(`UART_RECV 长度=${info.dataLen}${flagsStr}`);
        console.log(`  HEX: ${info.data.toString('hex').toUpperCase()}`);
        console.log(`  可打印: ${bufferToPrintable(info.data)}`);
        break;
      }

      /* ---------- status ---------- */
      case 'status': {
        const resp = await cmdUartStatus(transport, nextSeq(), opts.channel);
        const s = parseUartStatus(resp);
        const name = ERROR_NAMES[s.status] || `0x${s.status.toString(16)}`;
        console.log('=== UART 状态 ===');
        console.log(`  status:      ${s.status} (${name})`);
        console.log(`  波特率:      ${s.baudRate}`);
        console.log(`  TX 空闲:     ${s.lineState.txIdle ? '是' : '否'}`);
        console.log(`  RX 活跃:     ${s.lineState.rxActive ? '是' : '否'}`);
        console.log(`  TX buf:      ${s.txBufUsed} / —`);
        console.log(`  RX buf:      ${s.rxBufUsed} / —`);
        console.log(`  TX 总字节:   ${s.txTotal}`);
        console.log(`  RX 总字节:   ${s.rxTotal}`);
        console.log(`  错误计数:    ${s.errorCount}`);
        break;
      }

      /* ---------- break ---------- */
      case 'break': {
        const duration = opts.cmdArgs.duration || 0;
        const resp = await cmdUartBreak(transport, nextSeq(), opts.channel, duration);
        const status = checkStatus(resp);
        console.log(`UART_BREAK duration=${duration || '10 (默认)'}ms status=${status}`);
        process.exit(status === ERR_SUCCESS ? 0 : 1);
      }

      /* ---------- flush ---------- */
      case 'flush': {
        const type = parseFlushType(opts.cmdArgs.flushType);
        const typeNames = ['RX', 'TX', 'ALL', 'DRAIN'];
        const resp = await cmdUartFlush(transport, nextSeq(), opts.channel, type);
        const status = checkStatus(resp);
        console.log(`UART_FLUSH type=${typeNames[type]} status=${status}`);
        process.exit(status === ERR_SUCCESS ? 0 : 1);
      }

      /* ---------- sendrecv ---------- */
      case 'sendrecv': {
        let data;
        if (opts.cmdArgs.hexData) {
          data = parseHex(opts.cmdArgs.hexData);
        } else if (opts.cmdArgs.textData) {
          data = Buffer.from(opts.cmdArgs.textData, 'utf8');
        } else {
          console.error('错误: sendrecv 需要 --hex 或 --text 参数');
          process.exit(1);
        }

        const timeout = (opts.cmdArgs.timeout || 5) * 1000;

        const sendResp = await cmdUartSend(transport, nextSeq(), opts.channel, data);
        const sendInfo = parseUartSend(sendResp);
        if (sendInfo.status !== ERR_SUCCESS) {
          const name = ERROR_NAMES[sendInfo.status] || 'UNKNOWN';
          console.error(`UART_SEND 失败: status=${sendInfo.status} (${name})`);
          process.exit(1);
        }
        console.log(`SEND ${data.length}B hex=${data.toString('hex').toUpperCase()}`);

        console.log(`等待回显 (超时 ${timeout / 1000}s)...`);
        const frame = await cmdUartRecv(transport, nextSeq(), opts.channel, timeout);
        const recvInfo = parseUartRecv(frame);
        console.log(`RECV ${recvInfo.dataLen}B hex=${recvInfo.data.toString('hex').toUpperCase()}`);
        console.log(`     可打印: ${bufferToPrintable(recvInfo.data)}`);
        break;
      }

      /* ---------- quick ---------- */
      case 'quick': {
        let data;
        if (opts.cmdArgs.hexData) {
          data = parseHex(opts.cmdArgs.hexData);
        } else if (opts.cmdArgs.textData) {
          data = Buffer.from(opts.cmdArgs.textData, 'utf8');
        } else {
          console.error('错误: quick 需要 --hex 或 --text 参数');
          process.exit(1);
        }

        const timeout = (opts.cmdArgs.timeout || 3) * 1000;
        const rxMode = parseRxMode(opts.rxMode);

        console.log(`>>> quick 模式: port=${opts.port} channel=${opts.channel} extBaud=${opts.extBaud}`);

        // 1. OPEN (must open before config)
        const openResp2 = await cmdUartOpen(transport, nextSeq(), opts.channel, rxMode);
        const openInfo2 = parseUartOpen(openResp2);
        if (openInfo2.status !== ERR_SUCCESS) {
          console.error(`  打开失败: ${ERROR_NAMES[openInfo2.status] || openInfo2.status}`);
          process.exit(1);
        }
        console.log(`  1. OPEN rxBuf=${openInfo2.rxBufSize} txBuf=${openInfo2.txBufSize}`);

        // 2. CONFIG
        const cfgResp = await cmdUartConfig(transport, nextSeq(), opts.channel, {
          baudRate: opts.extBaud,
          dataBits: opts.dataBits,
          stopBits: parseStopBits(opts.stopBits),
          parity: parseParity(opts.parity),
          flowControl: opts.flowControl,
          rxThreshold: opts.rxThreshold || 256,
          rxTimeout: opts.rxTimeout || 50,
        });
        const cfg = parseUartConfig(cfgResp);
        if (cfg.status !== ERR_SUCCESS) {
          console.error(`  配置失败: ${ERROR_NAMES[cfg.status] || cfg.status}`);
          process.exit(1);
        }
        console.log(`  2. CONFIG ${opts.extBaud}bps OK (实际=${cfg.actualBaud})`);

        // 3. SEND
        const sendResp = await cmdUartSend(transport, nextSeq(), opts.channel, data);
        const sendInfo = parseUartSend(sendResp);
        if (sendInfo.status !== ERR_SUCCESS) {
          console.error(`  发送失败: ${ERROR_NAMES[sendInfo.status] || sendInfo.status}`);
          process.exit(1);
        }
        console.log(`  3. SEND ${sendInfo.actualLen}B → ${data.toString('hex').toUpperCase()}`);

        // 4. RECV
        console.log(`  4. 等待回显 (${timeout / 1000}s)...`);
        const recvFrame = await cmdUartRecv(transport, nextSeq(), opts.channel, timeout);
        const recvInfo = parseUartRecv(recvFrame);
        console.log(`     RECV ${recvInfo.dataLen}B ← ${recvInfo.data.toString('hex').toUpperCase()}`);

        // 5. STATUS
        const statusResp = await cmdUartStatus(transport, nextSeq(), opts.channel);
        const st = parseUartStatus(statusResp);
        console.log(`  5. STATUS tx=${st.txTotal} rx=${st.rxTotal} err=${st.errorCount}`);

        // 6. CLOSE
        await cmdUartClose(transport, nextSeq(), opts.channel);
        console.log('  6. CLOSE OK');
        break;
      }

      /* ---------- interactive ---------- */
      case 'interactive': {
        console.log('=== HEX-Bridge UART 交互模式 ===');
        console.log('命令: open [rxmode] | close | config <baud> | send <hex/text>');
        console.log('      recv [s] | status | break [ms] | flush <type> | quit');
        console.log('');

        const readline = require('readline');
        const rl = readline.createInterface({
          input: process.stdin,
          output: process.stdout,
          prompt: '> ',
        });

        rl.prompt();

        rl.on('line', async (line) => {
          const parts = line.trim().split(/\s+/);
          const cmd = parts[0].toLowerCase();

          try {
            switch (cmd) {
              case '': break;
              case 'quit':
              case 'exit':
                rl.close();
                return;

              case 'open': {
                const mode = parts[1] ? parseRxMode(parts[1]) : parseRxMode(opts.rxMode);
                const modeNames = ['passive', 'line', 'fixed', 'timeout'];
                const resp = await cmdUartOpen(transport, nextSeq(), opts.channel, mode);
                const info = parseUartOpen(resp);
                console.log(`OPEN ${modeNames[mode]} → status=${info.status} rxBuf=${info.rxBufSize} txBuf=${info.txBufSize}`);
                break;
              }
              case 'close': {
                const resp = await cmdUartClose(transport, nextSeq(), opts.channel);
                console.log('CLOSE OK');
                break;
              }
              case 'config': {
                const baud = parseInt(parts[1], 10) || opts.extBaud;
                const resp = await cmdUartConfig(transport, nextSeq(), opts.channel, {
                  baudRate: baud,
                  dataBits: opts.dataBits,
                  stopBits: parseStopBits(opts.stopBits),
                  parity: parseParity(opts.parity),
                  flowControl: 0,
                  rxThreshold: opts.rxThreshold,
                  rxTimeout: opts.rxTimeout,
                });
                const info = parseUartConfig(resp);
                console.log(`CONFIG ${baud} → 实际=${info.actualBaud} status=${info.status}`);
                break;
              }
              case 'send': {
                let data;
                if (parts[1] === 'hex' && parts[2]) {
                  data = parseHex(parts.slice(2).join(' '));
                } else if (parts[1] === 'text') {
                  data = Buffer.from(parts.slice(2).join(' '), 'utf8');
                } else {
                  data = Buffer.from(parts.slice(1).join(' '), 'utf8');
                }
                const resp = await cmdUartSend(transport, nextSeq(), opts.channel, data);
                const info = parseUartSend(resp);
                console.log(`SEND ${info.actualLen}B → ${data.toString('hex').toUpperCase()} status=${info.status}`);
                break;
              }
              case 'recv': {
                const timeout = (parseFloat(parts[1]) || 10) * 1000;
                console.log(`等待数据 (${timeout / 1000}s)...`);
                const frame = await cmdUartRecv(transport, nextSeq(), opts.channel, timeout);
                const info = parseUartRecv(frame);
                console.log(`RECV ${info.dataLen}B ← ${info.data.toString('hex').toUpperCase()}`);
                console.log(`     可打印: ${bufferToPrintable(info.data)}`);
                break;
              }
              case 'status': {
                const resp = await cmdUartStatus(transport, nextSeq(), opts.channel);
                const s = parseUartStatus(resp);
                console.log(`STATUS ${s.baudRate}bps tx=${s.txTotal} rx=${s.rxTotal} err=${s.errorCount} txBuf=${s.txBufUsed} rxBuf=${s.rxBufUsed}`);
                break;
              }
              case 'break': {
                const dur = parseInt(parts[1], 10) || 0;
                const resp = await cmdUartBreak(transport, nextSeq(), opts.channel, dur);
                console.log(`BREAK ${dur || 10}ms → status=${resp.payload[0]}`);
                break;
              }
              case 'flush': {
                const type = parseFlushType(parts[1]);
                const names = ['RX', 'TX', 'ALL', 'DRAIN'];
                const resp = await cmdUartFlush(transport, nextSeq(), opts.channel, type);
                console.log(`FLUSH ${names[type]} → status=${resp.payload[0]}`);
                break;
              }
              case 'info': {
                const resp = await cmdGetInfo(transport, nextSeq(), opts.channel);
                const p = resp.payload;
                const model = p.slice(0, 16).toString('utf8').replace(/\0/g, '');
                console.log(`INFO ${model} fw=${p[16]}.${p[17]}.${p[18]} proto=0x${p[19].toString(16)}`);
                break;
              }
              case 'ping': {
                const resp = await cmdPing(transport, nextSeq(), opts.channel);
                console.log(`PING status=${resp.payload[0]}`);
                break;
              }
              case 'help':
                console.log('命令: open|close|config|send|recv|status|break|flush|info|ping|quit');
                break;
              default:
                console.log(`未知命令: ${cmd} (输入 help 查看帮助)`);
            }
          } catch (err) {
            console.error(`错误: ${err.message}`);
          }
          rl.prompt();
        });

        rl.on('close', () => {
          console.log('再见。');
          transport.close();
          process.exit(0);
        });
        return;
      }

      default:
        console.error(`未知命令: ${opts.command}`);
        printHelp();
        process.exit(1);
    }
  } catch (err) {
    console.error(`错误: ${err.message}`);
    if (err.code === 'ECONNREFUSED' || err.message.includes('serialport')) {
      console.error('\n请确保:');
      console.error('  1. 已安装 serialport: npm install serialport');
      console.error('  2. 设备已连接且串口号正确');
      console.error('  3. 串口未被其他程序占用');
    }
    process.exit(1);
  } finally {
    if (transport) transport.close();
  }
}

main();
