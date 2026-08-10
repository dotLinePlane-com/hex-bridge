"""
Debug: Find minimum delay needed for baud switch 500k->250k.
"""
import sys, time, struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_STATUS=0x16
CAN_CHANNEL=3; ERR_SUCCESS=0x00

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()

for delay_s in [0.05, 0.1, 0.2, 0.3, 0.5, 0.8]:
    transport.flush_input()
    pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
    pcan.initialize()
    pcan.read_all(timeout_ms=50)
    
    seq = 100
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
    transport.recv_frame(timeout=2); transport.flush_input(); seq += 1
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
    transport.recv_response(seq_num=seq, timeout=3); seq += 1
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
        struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)))
    transport.recv_response(seq_num=seq, timeout=3); seq += 1
    time.sleep(0.1)
    
    # Verify 500k
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
        struct.pack('>IB', 0x100, 3) + b'\x01\x02\x03'))
    transport.recv_response(seq_num=seq, timeout=3); seq += 1
    pcan.read(timeout_ms=500)  # drain
    
    # Switch to 250k
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
        struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)))
    transport.recv_response(seq_num=seq, timeout=5); seq += 1
    time.sleep(delay_s)
    
    # Switch PCAN
    pcan.uninitialize()
    time.sleep(0.1)
    pcan2 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
    pcan2.initialize()
    pcan2.read_all(timeout_ms=50)
    
    # Send
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
        struct.pack('>IB', 0x200, 5) + b'World'))
    transport.recv_response(seq_num=seq, timeout=3)
    time.sleep(0.15)
    rx = pcan2.read(timeout_ms=500)
    
    transport.send(UBCPBuilder.build_request(seq+1, CMD_CAN_STATUS, CAN_CHANNEL, b''))
    f = transport.recv_response(seq_num=seq+1, timeout=3)
    tec = f.payload[2] if f else 255
    
    result = "OK" if rx else f"FAIL(TEC={tec})"
    print(f"delay={delay_s:.2f}s: {result} {'ID=0x%X' % rx.id if rx else ''}")
    
    transport.send(UBCPBuilder.build_request(seq+2, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
    transport.recv_frame(timeout=1)
    pcan2.uninitialize()
    time.sleep(0.2)

transport.close()
print("Done")
