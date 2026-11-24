"""Stage 2 hardware acceptance; requires an already active test mapping.

Does not stage/apply/confirm profiles or change pullups. Root orchestrator owns
profile restoration. Drives the Nucleo fixture through its ST-Link VCP and HXB1
through UART or socket://host:9500. Every hardware case reports independently.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import time

import serial
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexbridge_profile import decode_mapping


class Board:
    def __init__(self, transport):
        self.transport = transport
        self.seq = 0
        self.replies = {}
        self.events = []
        self.snapshot = None
        self.i2c_wiring = {8: (18,19), 9: (21,22)}

    def read_profile(self):
        data = self.ok(8, 0, b"\x06\x01")
        assert len(data) in (129, 245), f"Invalid v6 snapshot length {len(data)}"
        phase, revision, candidate, confirmed = struct.unpack_from(">BIII", data)
        assert phase < 4 and revision and bool(candidate) == (phase != 0)
        assert len(data) == 13 + 116 * (2 if candidate else 1)
        self.snapshot = dict(revision=revision, phase=phase, candidate_id=candidate,
                             confirmed_id=confirmed, active=decode_mapping(data[13:129]))
        return self.snapshot

    def require_i2c(self, channel):
        assert self.snapshot, "v6 profile must be read before I2C output"
        row = self.snapshot["active"]["i2c"][str(channel-8)]
        expected = self.i2c_wiring
        assert channel in expected and row["enabled"]
        assert (row["scl"], row["sda"]) == expected[channel], f"Unsafe fixture mapping: {row}"

    def require_gpio_pair(self, output, input_pin):
        assert self.snapshot, "v6 profile must be read before GPIO output"
        assert (output,input_pin) in ((23,27),(32,35)), "Unknown fixture pair"
        lines = self.snapshot["active"]["gpio_lines"].values()
        for pin,mode in ((output,"output"),(input_pin,"input")):
            selected = [row for row in lines if row["enabled"] and row["pin"]==pin]
            assert len(selected)==1 and selected[0]["mode"]==mode, f"Unsafe GPIO{pin} mapping/direction: {selected}"

    def send(self, cmd, channel, payload=b""):
        self.seq = (self.seq + 1) & 0xFFFF
        self.transport.send(UBCPBuilder.build_request(self.seq, cmd, channel, payload))
        return self.seq

    def pump(self, timeout):
        frame = self.transport.recv_frame(timeout)
        if frame:
            if frame.is_event:
                self.events.append(frame)
            elif frame.is_response:
                self.replies[frame.seq_num] = (frame, time.monotonic())

    def receive(self, seq, timeout=4):
        end = time.monotonic() + timeout
        while seq not in self.replies and time.monotonic() < end:
            self.pump(min(.05, max(.001, end-time.monotonic())))
        assert seq in self.replies, f"No response for sequence {seq}"
        return self.replies.pop(seq)

    def raw(self, cmd, channel, payload=b""):
        seq = self.send(cmd, channel, payload)
        frame, _ = self.receive(seq)
        assert frame.cmd_code == cmd and frame.channel_id == channel, "Response route mismatch"
        assert frame.payload, "Empty response"
        return bytes(frame.payload)

    def ok(self, cmd, channel, payload=b""):
        reply = self.raw(cmd, channel, payload)
        assert reply[0] == 0, f"cmd={cmd:02x} ch={channel} status={reply.hex()}"
        return reply[1:]

    def collect(self, seconds):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            self.pump(min(.02, max(.001, end-time.monotonic())))
        events, self.events = self.events, []
        return events


class Fixture:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=.02)

    def cmd(self, command):
        self.ser.reset_input_buffer()
        self.ser.write(command.encode("ascii")+b"\n")
        end = time.monotonic()+2
        while time.monotonic() < end:
            line = self.ser.readline().decode("ascii", "replace").strip()
            if line.startswith(("OK", "STATUS")):
                return line
            if line.startswith("ERR"):
                raise AssertionError(line)
        raise TimeoutError(f"Fixture command {command} unanswered")


class Suite:
    def __init__(self):
        self.results = []

    def case(self, name, function):
        start = time.monotonic()
        try:
            detail = function()
            row = dict(case=name, status="PASS", detail=detail)
        except Exception as exc:
            row = dict(case=name, status="FAIL", detail=f"{type(exc).__name__}: {exc}")
        row["seconds"] = round(time.monotonic()-start, 4)
        self.results.append(row)
        print(f"{row['status']} {name}: {row['detail']}", flush=True)


def restart(board, channel, mode=0, speed=100000, timeout=200):
    board.require_i2c(channel)
    board.raw(0x31, channel)
    board.ok(0x30, channel, bytes([mode]))
    board.ok(0x32, channel, struct.pack(">IH", speed, timeout))


def read(board, channel, register=0, length=1, address=0x50, combined=False):
    if combined:
        payload = struct.pack(">HHH", address, 1, length)+bytes([register])
        data = board.ok(0x35, channel, payload)
    else:
        payload = struct.pack(">HB", address, 1)+bytes([register])+struct.pack(">H", length)
        data = board.ok(0x34, channel, payload)
    assert len(data) == length+2 and int.from_bytes(data[:2], "big") == length, data.hex()
    return data[2:]


def write(board, channel, register, data=b"", address=0x50):
    payload = struct.pack(">HB", address, 1)+bytes([register])+struct.pack(">H", len(data))+data
    result = board.ok(0x33, channel, payload)
    assert result == struct.pack(">H", len(data)), result.hex()


def identity(board, channel, expected):
    data = read(board, channel, 0, 4)
    fixture_index = {0xa1: 0, 0xb2: 1}[expected]
    assert data == bytes([expected, 1, fixture_index, 0]), data.hex()
    return data.hex()


def i2c_cases(suite, board, fixture):
    for channel, label, ident in ((8, "A", 0xA1), (9, "B", 0xB2)):
        for speed in (100000, 400000):
            def basic(ch=channel, tag=label, sig=ident, hz=speed):
                fixture.cmd(tag+"7")
                restart(board, ch, speed=hz)
                identity(board, ch, sig)
                pattern=bytes([sig, 0x00, 0x7d, 0x7e, 0xff, 0x55, 0xaa, 0x31])
                write(board, ch, 0x20, pattern)
                assert read(board, ch, 0x20, len(pattern)) == pattern
                assert read(board, ch, 0x20, len(pattern), combined=True) == pattern
                write(board, ch, 0x20)
                raw = board.ok(0x34, ch, struct.pack(">HBH", 0x50, 0, len(pattern)))
                assert raw == struct.pack(">H", len(pattern))+pattern, raw.hex()
                return f"id={sig:02x}, RAM/prefix/WRITE_READ/bare read at {hz}Hz"
            suite.case(f"i2c-{label}-{speed}", basic)

        def scan(ch=channel, tag=label):
            fixture.cmd(tag+"7"); restart(board,ch,timeout=1000)
            assert board.ok(0x36,ch,b"\x08\x77") == b"\x01\x50"
            return "Only address 0x50 found in 08..77"
        suite.case(f"i2c-{label}-scan",scan)

        def nack(ch=channel,tag=label,sig=ident):
            fixture.cmd(tag+"7"); restart(board,ch)
            p=struct.pack(">HBH",0x51,0,1)
            assert board.raw(0x34,ch,p) == b"\x30", "Missing target must return I2C_NACK=30"
            return "NACK=30 then identity="+identity(board,ch,sig)
        suite.case(f"i2c-{label}-nack-recovery",nack)

        def ten(ch=channel,tag=label,sig=ident):
            fixture.cmd(tag+"10")
            try:
                restart(board,ch,mode=1)
                assert read(board,ch,0,1,address=0x250) == bytes([sig])
                pattern=bytes([sig,0x25,0x00,0x7e])
                write(board,ch,0x30,pattern,address=0x250)
                assert read(board,ch,0x30,4,address=0x250,combined=True) == pattern
                return "10bit 0x250 identity + RAM write/read"
            finally:
                fixture.cmd(tag+"7"); restart(board,ch)
        suite.case(f"i2c-{label}-10bit",ten)

    def isolated_ram():
        for ch,tag in ((8,"A"),(9,"B")):
            fixture.cmd(tag+"7"); restart(board,ch)
        write(board,8,0x40,b"A-independent")
        write(board,9,0x40,b"B-independent")
        assert read(board,8,0x40,13)==b"A-independent"
        assert read(board,9,0x40,13)==b"B-independent"
        return "Same address + register retain different RAM values"
    suite.case("i2c-same-address-isolation",isolated_ram)

    for speed_a,speed_b in ((100000,400000),(400000,100000)):
        def parallel(a=speed_a,b=speed_b):
            fixture.cmd("A7"); fixture.cmd("B7")
            restart(board,8,speed=a); restart(board,9,speed=b)
            payload=struct.pack(">HHH",0x50,1,4)+b"\0"
            sa=board.send(0x35,8,payload); sb=board.send(0x35,9,payload)
            ra,_=board.receive(sa); rb,_=board.receive(sb)
            assert bytes(ra.payload)==b"\0\0\4\xa1\1\0\0",bytes(ra.payload).hex()
            assert bytes(rb.payload)==b"\0\0\4\xb2\1\1\0",bytes(rb.payload).hex()
            return f"Both combined reads queued: A={a}Hz B={b}Hz"
        suite.case(f"i2c-parallel-speed-{speed_a}-{speed_b}",parallel)

    def nack_peer():
        fixture.cmd("A7"); fixture.cmd("B7")
        restart(board,8); restart(board,9)
        sa=board.send(0x34,8,struct.pack(">HBH",0x51,0,1))
        sb=board.send(0x35,9,struct.pack(">HHH",0x50,1,1)+b"\0")
        rb,_=board.receive(sb); ra,_=board.receive(sa)
        assert bytes(ra.payload)==b"\x30",bytes(ra.payload).hex()
        assert bytes(rb.payload)==b"\0\0\1\xb2",bytes(rb.payload).hex()
        return "A absent target NACK while B returns B2 identity"
    suite.case("i2c-nack-peer-independent",nack_peer)

    for fault,other,tag,sig in ((8,9,"A",0xb2),(9,8,"B",0xa1)):
        def independence(ch=fault,peer=other,label=tag,expected=sig):
            fixture.cmd("A7"); fixture.cmd("B7")
            restart(board,ch,timeout=700); restart(board,peer,timeout=200)
            fixture.cmd(label+"F1500")
            try:
                a=board.send(0x34,ch,struct.pack(">HBH",0x50,0,1))
                time.sleep(.02)
                b=board.send(0x34,peer,struct.pack(">HB",0x50,1)+b"\0\0\1")
                br,bt=board.receive(b)
                ar,at=board.receive(a)
                assert bytes(br.payload)==b"\0\0\1"+bytes([expected]), bytes(br.payload).hex()
                assert bytes(ar.payload)==b"\x03", f"Expected TIMEOUT=03, got {bytes(ar.payload).hex()}"
                assert bt < at, f"Other bus completed after fault ({bt-at:.4f}s)"
            finally:
                time.sleep(1.55)  # fixture fault expires even when a preceding assertion fails
            return f"peer identity returned {at-bt:.4f}s before fault timeout; recovered="+identity(board,ch,0xa1 if ch==8 else 0xb2)
        suite.case(f"i2c-fault-{tag}-peer-independent",independence)


def gpio(board,cmd,pin,*values):
    return board.ok(cmd,10+pin//32,bytes([pin%32,*values]))


def setup_pair(board,out,inp):
    board.require_gpio_pair(out,inp)
    gpio(board,0x80,inp,0)
    gpio(board,0x84,inp,0,0)
    gpio(board,0x80,out,1)
    gpio(board,0x81,out,0)
    board.collect(.03)


def pin_events(events,pin):
    return [e for e in events if e.cmd_code==0x85 and e.channel_id==10+pin//32
            and len(e.payload)==3 and e.payload[0]==pin%32]


def gpio_cases(suite,board):
    for out,inp in ((23,27),(32,35)):
        def levels(o=out,i=inp):
            setup_pair(board,o,i)
            for value in (0,1,0,1,0):
                gpio(board,0x81,o,value)
                assert gpio(board,0x82,i)==bytes([value]), f"GPIO{o}->{i} does not follow {value}"
            return "low/high/readback through physical jumper"
        suite.case(f"gpio-{out}-{inp}-levels",levels)

        def masks(o=out,i=inp):
            setup_pair(board,o,i)
            ch=10+o//32; om=1<<(o%32); im=1<<(i%32)
            board.ok(0x86,ch,struct.pack(">II",om,om))
            data=board.ok(0x87,ch,struct.pack(">I",om|im))
            assert len(data)==8
            levels,dirs=struct.unpack(">II",data)
            assert levels&(om|im)==om|im and dirs&(om|im)==om,(levels,dirs)
            assert board.raw(0x86,ch,struct.pack(">II",om|im,0))==b"\x81"
            assert gpio(board,0x82,o)==b"\1", "Rejected mask partially changed output"
            board.ok(0x86,ch,struct.pack(">II",om,0))
            assert gpio(board,0x82,i)==b"\0"
            return "group masks and whole-request direction rejection"
        suite.case(f"gpio-{out}-{inp}-masks",masks)

        def edges(o=out,i=inp):
            setup_pair(board,o,i); gpio(board,0x84,i,3,10)
            try:
                gpio(board,0x81,o,1); first=pin_events(board.collect(.08),i)
                gpio(board,0x81,o,0); second=pin_events(board.collect(.08),i)
                assert len(first)==len(second)==1,(len(first),len(second))
                assert bytes(first[0].payload)==bytes([i%32,1,1])
                assert bytes(second[0].payload)==bytes([i%32,2,0])
                assert first[0].has_timestamp and second[0].has_timestamp
                assert (second[0].timestamp-first[0].timestamp)&0xffffffff > 0
                return "one rise + one fall, correct group/pin/timestamps"
            finally:
                gpio(board,0x84,i,0,0)
        suite.case(f"gpio-{out}-{inp}-edges",edges)

        def debounce(o=out,i=inp):
            setup_pair(board,o,i); gpio(board,0x84,i,1,150)
            try:
                gpio(board,0x81,o,1); gpio(board,0x81,o,0)
                assert not pin_events(board.collect(.22),i), "Short pulse passed debounce"
                gpio(board,0x81,o,1)
                events=pin_events(board.collect(.25),i)
                assert len(events)==1 and events[0].payload[1:]==b"\1\1",len(events)
                return "short pulse filtered; stable high emitted once (150ms)"
            finally:
                gpio(board,0x84,i,0,0); gpio(board,0x81,o,0)
        suite.case(f"gpio-{out}-{inp}-debounce",debounce)

        def level_irq(o=out,i=inp):
            setup_pair(board,o,i); gpio(board,0x84,i,4,10)
            try:
                gpio(board,0x81,o,1); e=pin_events(board.collect(.25),i)
                assert len(e)==1 and e[0].payload[1:]==b"\4\1",len(e)
                assert not pin_events(board.collect(.2),i), "Held high flooded events"
                gpio(board,0x81,o,0); board.collect(.05)
                gpio(board,0x81,o,1); e=pin_events(board.collect(.15),i)
                assert len(e)==1,len(e)
                return "held level emitted once, release rearmed interrupt"
            finally:
                gpio(board,0x84,i,0,0); gpio(board,0x81,o,0)
        suite.case(f"gpio-{out}-{inp}-level-interrupt",level_irq)

    def groups():
        board.require_gpio_pair(23,27)
        board.require_gpio_pair(32,35)
        for o,i in ((23,27),(32,35)):
            setup_pair(board,o,i); gpio(board,0x84,i,3,10)
        try:
            gpio(board,0x81,23,1); gpio(board,0x81,32,1)
            events=board.collect(.1)
            for i in (27,35):
                e=pin_events(events,i)
                assert len(e)==1 and e[0].payload[1:]==b"\1\1",f"GPIO{i}: {len(e)} events"
            gpio(board,0x81,23,0)
            assert gpio(board,0x82,35)==b"\1", "Low group altered high group"
            e=board.collect(.1)
            assert len(pin_events(e,27))==1 and not pin_events(e,35)
            return "both groups deliver events; writes remain isolated"
        finally:
            for o,i in ((23,27),(32,35)):
                gpio(board,0x84,i,0,0); gpio(board,0x81,o,0)
    suite.case("gpio-two-group-event-isolation",groups)


def partial_cases(suite,board,fixture):
    """A-only fault/recovery and scan/GPIO isolation; never references bus B."""
    def fault_recovery():
        board.require_i2c(8)
        fixture.cmd("A7"); restart(board,8,timeout=150)
        identity(board,8,0xa1)
        fixture.cmd("AF600")
        try:
            result=board.raw(0x34,8,struct.pack(">HBH",0x50,0,1))
            assert result==b"\x03",f"Expected timeout=03: {result.hex()}"
        finally:
            time.sleep(.65)
        return "Actual SDA-low timeout=03; released identity="+identity(board,8,0xa1)
    suite.case("partial-A-stuck-SDA-recovery",fault_recovery)

    def scan_gpio():
        board.require_i2c(8); board.require_gpio_pair(23,27)
        fixture.cmd("A7"); restart(board,8,timeout=300)
        identity(board,8,0xa1); setup_pair(board,23,27)
        fixture.cmd("AF700")
        try:
            scan_seq=board.send(0x36,8,b"\x08\x77")
            time.sleep(.01)
            start=time.monotonic()
            gpio(board,0x81,23,1)
            assert gpio(board,0x82,27)==b"\1", "GPIO loopback failed during A scan"
            ping_seq=board.send(0,0)
            ping,ping_time=board.receive(ping_seq)
            assert ping.payload[0]==0,bytes(ping.payload).hex()
            scan,scan_time=board.receive(scan_seq)
            assert bytes(scan.payload)==b"\x03",bytes(scan.payload).hex()
            assert ping_time < scan_time,"GPIO/ping stalled behind stuck-bus scan"
            latency=ping_time-start
        finally:
            time.sleep(.75)
            gpio(board,0x81,23,0)
        identity(board,8,0xa1)
        return f"GPIO loopback+PING completed in {latency:.4f}s before scan timeout, A recovered"
    suite.case("partial-A-stuck-scan-GPIO-ping-independent",scan_gpio)


def swapped_cases(suite,board,fixture):
    """I2C1 reaches working fixture A; I2C0 reaches known held-low path.

    Both controllers are exercised, but this is explicitly not dual successful
    slave communication: the B physical path is expected to time out.
    """
    for speed in (100000,400000):
        def seven(hz=speed):
            board.require_i2c(9)
            fixture.cmd("A7"); restart(board,9,speed=hz)
            signature=identity(board,9,0xa1)
            pattern=bytes([0xa1,0x09,0x7d,0x7e,0x00,0xff,0x55,0xaa])
            write(board,9,0x50,pattern)
            assert read(board,9,0x50,8)==pattern
            assert read(board,9,0x50,8,combined=True)==pattern
            write(board,9,0x50)
            bare=board.ok(0x34,9,struct.pack(">HBH",0x50,0,8))
            assert bare==b"\0\x08"+pattern,bare.hex()
            return f"I2C1 GPIO18/19 -> fixture A id={signature}; 7bit RAM/prefix/combined/bare reads at {hz}Hz"
        suite.case(f"swapped-I2C1-fixture-A-7bit-{speed}",seven)

        def ten(hz=speed):
            board.require_i2c(9)
            fixture.cmd("A10")
            try:
                restart(board,9,mode=1,speed=hz)
                signature=read(board,9,0,4,address=0x250)
                assert signature==b"\xa1\1\0\0",signature.hex()
                pattern=bytes([0xa1,0x10,0x25,0x09,0x7e,0x7d])
                write(board,9,0x60,pattern,address=0x250)
                assert read(board,9,0x60,6,address=0x250,combined=True)==pattern
                return f"I2C1 -> fixture A 10bit0x250 signature + RAM at {hz}Hz"
            finally:
                fixture.cmd("A7"); restart(board,9)
        suite.case(f"swapped-I2C1-fixture-A-10bit-{speed}",ten)

    def recovery():
        board.require_i2c(9)
        fixture.cmd("A7"); restart(board,9,timeout=150)
        identity(board,9,0xa1); fixture.cmd("AF600")
        try:
            result=board.raw(0x34,9,struct.pack(">HBH",0x50,0,1))
            assert result==b"\x03",f"Expected timeout03: {result.hex()}"
        finally:
            time.sleep(.65)
        return "I2C1 actual A-SDA-low timeout03; FIRST postrelease read="+identity(board,9,0xa1)
    suite.case("swapped-I2C1-fixture-A-fault-recovery",recovery)

    def held_path():
        board.require_i2c(8); board.require_i2c(9)
        pins=fixture.cmd("PINS")
        assert "PB10=0" in pins,"Held-low B path precondition missing: "+pins
        fixture.cmd("A7")
        restart(board,8,timeout=700); restart(board,9,timeout=200)
        identity(board,9,0xa1)
        blocked=board.send(0x34,8,struct.pack(">HBH",0x50,0,1))
        time.sleep(.02)
        good=board.send(0x35,9,struct.pack(">HHH",0x50,1,4)+b"\0")
        good_reply,good_time=board.receive(good)
        blocked_reply,blocked_time=board.receive(blocked)
        assert bytes(good_reply.payload)==b"\0\0\4\xa1\1\0\0",bytes(good_reply.payload).hex()
        assert bytes(blocked_reply.payload)==b"\x03",bytes(blocked_reply.payload).hex()
        assert good_time<blocked_time,"Good A controller stalled behind held-low path"
        identity(board,9,0xa1)
        return f"Held-low path I2C0(GPIO21/22, PB10 low) timeout03; I2C1/A success {blocked_time-good_time:.4f}s earlier. No dual-success claim."
    suite.case("swapped-held-low-path-I2C0-vs-working-A-I2C1",held_path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",default="COM3")
    parser.add_argument("--baud",type=int,default=115200)
    parser.add_argument("--fixture",default="COM8")
    parser.add_argument("--identity",help="Expected GET_INFO hardware ID hex (8 bytes)")
    parser.add_argument("--section",choices=("all","i2c","gpio","partial","swapped"),default="all")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    suite=Suite(); fixture=None
    with MCPTransport(args.port,args.baud) as transport:
        board=Board(transport)
        if args.section=="swapped":
            board.i2c_wiring={8:(21,22),9:(18,19)}
        info=board.ok(1,0)
        assert len(info)==16, f"Unexpected GET_INFO {info.hex()}"
        hardware_id=info[3:11].hex()
        assert args.identity is None or hardware_id.lower()==args.identity.lower(), "Unexpected hardware identity"
        print(f"IDENTITY {hardware_id}",flush=True)
        # One active v6 snapshot gates all drive operations. This runner owns
        # peripheral sessions; the caller must keep profile revision stable.
        snapshot=board.read_profile()
        print(f"PROFILE v6 revision={snapshot['revision']} phase={snapshot['phase']}",flush=True)
        try:
            if args.section in ("all","i2c","partial","swapped"):
                def open_fixture():
                    nonlocal fixture
                    fixture=Fixture(args.fixture)
                    status=fixture.cmd("STATUS")
                    assert "stage2-i2c-v1" in status, status
                    fixture.cmd("RUN")
                    return status
                suite.case("fixture-identity",open_fixture)
                if fixture:
                    if args.section=="swapped": swapped_cases(suite,board,fixture)
                    elif args.section=="partial": partial_cases(suite,board,fixture)
                    else: i2c_cases(suite,board,fixture)
            if args.section in ("all","gpio"):
                gpio_cases(suite,board)
        finally:
            if fixture:
                def cleanup():
                    time.sleep(.05)
                    # Every runner fault is <=1500 ms and expires autonomously.
                    tags=("A",) if args.section=="partial" else ("A","B")
                    channels=(8,) if args.section=="partial" else (8,9)
                    for tag in tags:
                        try: fixture.cmd(tag+"7")
                        except AssertionError:
                            time.sleep(1.55); fixture.cmd(tag+"7")
                    for ch in channels: board.raw(0x31,ch)
                    return fixture.cmd("STATUS")
                suite.case("fixture-cleanup-7bit-close-buses",cleanup)
                fixture.ser.close()
    report=dict(identity=hardware_id,port=args.port,section=args.section,profile=snapshot,results=suite.results)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    passed=sum(r["status"]=="PASS" for r in suite.results)
    print(f"TOTAL {passed} PASS / {len(suite.results)-passed} FAIL",flush=True)
    return 0 if passed==len(suite.results) else 1


if __name__=="__main__":
    raise SystemExit(main())
