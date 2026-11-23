"""Check CANable suite switch ordering without serial ports or hardware."""
from types import SimpleNamespace
from unittest.mock import patch
import test_canable as suite


def main():
    events = []

    class Adapter:
        def __getattr__(self, name):
            return lambda *a, **k: events.append((name, a))

    can = Adapter()
    with patch.object(suite.time, "sleep"):
        suite.canable_setup(can, baud=250000)
    assert [e[0] for e in events] == ["cmd_close", "set_bitrate", "set_data_bitrate", "set_silent", "set_retransmit", "cmd_open"]
    events.clear()

    def config(transport, seq, index, **kw):
        events.append(("config", (index,)))
        return SimpleNamespace(payload=b"\0")

    def send(transport, seq, ident, data):
        events.append(("send", (ident,)))

    with patch.object(suite.time, "sleep"), patch.object(suite, "can_config", config), \
            patch.object(suite, "can_send", send), patch.object(suite, "recv_canable", return_value=object()), \
            patch.object(suite, "check_canable"):
        seq = suite.test_can_baud_switch(None, 10, can, base_baud=1000000, base_index=8)
    assert seq == 15
    configs = [i for i, event in enumerate(events) if event[0] == "config"]
    assert [events[i][1][0] for i in configs] == [5, 8]
    assert all(events[i - 1][0] == "cmd_close" for i in configs)
    assert ("set_bitrate", (1000000,)) in events
    events.clear()
    with patch.object(suite.time, "sleep"), patch.object(suite, "can_config", return_value=None), \
            patch.object(suite, "can_send", send), patch.object(suite, "recv_canable", return_value=object()), \
            patch.object(suite, "check_canable"):
        try:
            suite.test_can_baud_switch(None, 10, can)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Failed configuration must stop the switch test")
    assert [e for e in events if e[0] == "send"] == [("send", (0x600,))]
    print("CANable setup and bitrate switch ordering/selected baseline/error gating PASS")


if __name__ == "__main__":
    main()
