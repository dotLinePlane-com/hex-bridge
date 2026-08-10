"""
Test PCAN 500k->250k baud switch reliability with different delays.
"""
import sys, time, struct
sys.path.insert(0, ".")
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

def pcan_init_baud(baud):
    m = {'500k': PcanBaudrate.PCAN_BD_500K, '250k': PcanBaudrate.PCAN_BD_250K}
    ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=m[baud])
    s = ch.initialize()
    return ch, s

print("=== PCAN 500k -> 250k switch reliability ===")

# Init at 500k
pcan, s = pcan_init_baud('500k')
print(f"PCAN 500k init: 0x{s:X}")

# Write a 500k frame to make it active
pcan.write(PcanMessage(id=0x100, data=b'hello'))
time.sleep(0.2)

for delay in [0.05, 0.1, 0.3, 0.5, 1.0]:
    # Uninit 500k
    pcan.uninitialize()
    time.sleep(delay)
    # Init 250k
    pcan250, s = pcan_init_baud('250k')
    # Check: write a frame, read back if PCAN receives its own... can't self-receive.
    # Instead check if the bitrate took effect by reading PCAN status after a write attempt.
    # With no other node, a write at correct baud -> no immediate error.
    st = pcan250.write(PcanMessage(id=0x200, data=b'world'))
    time.sleep(0.1)
    status = pcan250.get_status()
    # PCAN_STATUS: check for bus errors
    print(f"delay={delay}s: init=0x{s:X} write=0x{st:X} status=0x{status:X}")
    pcan250.uninitialize()

pcan.uninitialize()
print("Done")
