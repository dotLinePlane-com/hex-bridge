"""
Test different PCAN 500k->250k switch methods.
MCP is opened directly at 250k (known working).
Then try various PCAN switch approaches and verify each.
"""
import sys, time, struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import (PcanChannel, PcanBaudrate, PcanHandle, PcanStatus,
                        PcanMessage, PcanParameter)

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_STATUS=0x16; CMD_CAN_RECV=0x14
CAN_CHANNEL=3

# Open MCP at 250k directly
transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

def sc(t, seq, cmd, payload=b''):
    t.send(UBCPBuilder.build_request(seq, cmd, CAN_CHANNEL, payload))
    return t.recv_response(seq_num=seq, timeout=5)

seq = 600
sc(transport, seq, CMD_CAN_CLOSE)
transport.recv_frame(timeout=2); transport.flush_input(); seq += 1
sc(transport, seq, CMD_CAN_OPEN, bytes([0])); seq += 1
sc(transport, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)); seq += 1
time.sleep(0.3)
print("MCP opened at 250k")

def test_switch(method):
    """method: how to create PCAN at 250k. Returns (channel, ok)."""
    pcan250 = None
    try:
        if method == 'direct':
            pcan250 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1,
                                  baudrate=PcanBaudrate.PCAN_BD_250K)
            pcan250.initialize()
        elif method == 'adapting_off':
            pcan250 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1,
                                  baudrate=PcanBaudrate.PCAN_BD_250K)
            pcan250.initialize()
            pcan250.set_value(PcanParameter.PCAN_BITRATE_ADAPTING, 0)
        elif method == 'long_delay':
            time.sleep(1.0)
            pcan250 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1,
                                  baudrate=PcanBaudrate.PCAN_BD_250K)
            pcan250.initialize()
        elif method == 'reset_first':
            pcan500 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1,
                                  baudrate=PcanBaudrate.PCAN_BD_500K)
            pcan500.initialize()
            pcan500.uninitialize()
            time.sleep(0.5)
            pcan250 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1,
                                  baudrate=PcanBaudrate.PCAN_BD_250K)
            pcan250.initialize()

        pcan250.read_all(timeout_ms=100)
        time.sleep(0.2)
        # PCAN -> MCP
        transport.flush_input()
        pcan250.write(PcanMessage(id=0x100, data=b'test'))
        f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
        if f:
            ok1 = True
        else:
            ok1 = False
        # MCP -> PCAN
        sc(transport, seq, CMD_CAN_SEND, struct.pack('>IB', 0x200, 5) + b'hello')
        time.sleep(0.3)
        rx = pcan250.read(timeout_ms=800)
        ok2 = rx is not None
        return pcan250, ok1, ok2
    except Exception as e:
        return pcan250, False, False

methods = ['direct', 'adapting_off', 'long_delay', 'reset_first']
results = {}
for m in methods:
    # uninit any existing channel first
    try:
        # try to uninit via a fresh handle to release
        tmp = PcanChannel(channel=PcanHandle.PCAN_USBBUS1,
                          baudrate=PcanBaudrate.PCAN_BD_500K)
        tmp.uninitialize()
    except Exception:
        pass
    time.sleep(0.3)
    pcan250, ok1, ok2 = test_switch(m)
    print(f"method={m}: PCAN->MCP={ok1}, MCP->PCAN={ok2}")
    results[m] = (ok1, ok2)
    if pcan250 is not None:
        try:
            pcan250.uninitialize()
        except Exception:
            pass
    time.sleep(0.3)

sc(transport, seq+1, CMD_CAN_CLOSE)
transport.recv_frame(timeout=2)
transport.close()
print("Done")
