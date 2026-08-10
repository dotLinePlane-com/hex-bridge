"""Test canable slcan bitrate/open/transmit."""
import sys, time
import serial

def crlf_resp(s):
    time.sleep(0.15)
    return s.read(200)

s = serial.Serial(port='COM6', baudrate=115200, timeout=0.3)
time.sleep(0.3)
s.reset_input_buffer()

# Set 500k
s.write(b'S6\r')
print("S6 ->", repr(crlf_resp(s)))

# Open
s.write(b'O\r')
print("O  ->", repr(crlf_resp(s)))

# Transmit standard frame ID=0x123 data=01 02 03
# slcan: t<III><L><DD...>
s.write(b't1233010203\r')
print("tx ->", repr(crlf_resp(s)))

# Try extended frame ID=0x00000123 data=AA BB
# slcan: T<IIIIIIII><L><DD...>
s.write(b'T000001234AABB\r')
print("txX->", repr(crlf_resp(s)))

# Status
s.write(b'F\r')
print("F  ->", repr(crlf_resp(s)))

# Close
s.write(b'C\r')
print("C  ->", repr(crlf_resp(s)))

s.close()
print("done")
