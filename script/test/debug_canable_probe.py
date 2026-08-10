"""Quick canable slcan probe on COM6."""
import sys, time
import serial

def probe(port, baud):
    try:
        s = serial.Serial(port=port, baudrate=baud, timeout=0.3)
    except Exception as e:
        print(f"  open {port}@{baud}: {e}")
        return
    time.sleep(0.2)
    # flush
    s.reset_input_buffer()
    # Version
    s.write(b'V\r')
    time.sleep(0.1)
    data = s.read(100)
    print(f"  {port}@{baud}: V -> {data!r}")
    # Serial number
    s.write(b'N\r')
    time.sleep(0.1)
    data = s.read(100)
    print(f"  {port}@{baud}: N -> {data!r}")
    # Status
    s.write(b'F\r')
    time.sleep(0.1)
    data = s.read(100)
    print(f"  {port}@{baud}: F -> {data!r}")
    s.close()

print("=== canable probe ===")
for baud in [115200, 921600, 57600]:
    probe('COM6', baud)
