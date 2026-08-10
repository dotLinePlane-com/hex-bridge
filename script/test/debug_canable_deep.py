"""Deep probe canable2 command protocol."""
import sys, time
import serial

def try_cmd(s, label, cmd, delay=0.2):
    s.reset_input_buffer()
    s.write(cmd)
    time.sleep(delay)
    data = s.read(300)
    print(f"{label}: {cmd!r} -> {data!r}")
    return data

s = serial.Serial(port='COM6', baudrate=115200, timeout=0.3)
time.sleep(0.3)

# Basic commands, various terminations
try_cmd(s, "V+CR", b'V\r')
try_cmd(s, "V+LF", b'V\n')
try_cmd(s, "v+CR", b'v\r')

# status / version variants
try_cmd(s, "I+CR", b'I\r')   # candleLight 'I' = info?
try_cmd(s, "F+CR", b'F\r')
try_cmd(s, "help", b'help\r')

# bitrate: S6 vs s6, with/without CR
try_cmd(s, "S6+CR", b'S6\r')
try_cmd(s, "s6+CR", b's6\r')
try_cmd(s, "S6 noCR", b'S6')
try_cmd(s, "S06+CR", b'S06\r')

# open/close variants
try_cmd(s, "O+CR", b'O\r')
try_cmd(s, "o+CR", b'o\r')

# Check any unsolicited data
s.reset_input_buffer()
time.sleep(0.5)
d = s.read(300)
print("unsolicited:", repr(d))

s.close()
