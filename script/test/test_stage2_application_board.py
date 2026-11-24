"""Explicit Stage2 CLI/Tk board check; uses active mapping, never saves a profile."""
import argparse
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'script'))
sys.path.insert(0, str(ROOT / 'tool/funcitonPinMap'))
import app
from hexbridge_io import BusinessSession, execute
from hexbridge_profile import MCPTransport


def tk_check(port):
    root = tk.Tk()
    gui = app.ProfileApp(root)
    root.geometry('980x650')
    errors = []
    results = dict(port=port, frontend='Tk')
    def pump():
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            root.update()
            if not gui.busy:
                if errors:
                    raise AssertionError(errors[-1])
                return
            time.sleep(0.01)
        raise TimeoutError('Tk operation timed out')
    def io(method, *args):
        method(*args)
        pump()
        result = json.loads(gui.stage2.result)
        if isinstance(result, dict) and result.get('status', 0):
            raise AssertionError(result)
        return result
    with patch.object(app.messagebox, 'showerror', side_effect=lambda *args, **kwargs: errors.append(args)):
        try:
            gui.port_var.set(port)
            gui.baud_var.set('115200')
            gui.buttons['read'].invoke()
            pump()
            gui.notebook.select(gui.stage2.tab)
            gui.stage2.fields[('i2c0', 'timeout_ms')].set('750')
            gui.stage2.edit(('i2c0', 'timeout_ms'))
            pump()
            gui.buttons['check'].invoke()
            pump()
            results['profile'] = dict(schema=gui.view['descriptor']['schema'], phase=gui.view['snapshot']['phase'], check=gui.status_var.get())
            io(gui.stage2.connect)
            gui.stage2.bus.set('0')
            gui.stage2.address.set('0x50')
            gui.stage2.register.set('00')
            gui.stage2.length.set('1')
            io(gui.stage2.i2c, 'open')
            results['signature'] = io(gui.stage2.i2c, 'read-reg')
            assert results['signature']['data'] == 'a1', results
            for level in (1, 0):
                gui.stage2.line.set('0')
                gui.stage2.level.set(str(level))
                io(gui.stage2.gpio, 'write')
                gui.stage2.line.set('1')
                result = io(gui.stage2.gpio, 'read')
                assert result['level'] == level, result
                results['gpio_' + str(level)] = result
            io(gui.stage2.i2c, 'close')
        finally:
            if gui.stage2.session and gui.stage2.session.connected:
                try:
                    gui.stage2.session.gpio('write',line=0,level=0)
                    if '0' in gui.stage2.session.open_buses:
                        gui.stage2.session.i2c('close',bus=0)
                finally:
                    gui.stage2.disconnect()
            gui._closed = True
            root.after_cancel(gui._poll_id)
            root.destroy()
    return results


def cli_check(port):
    results = dict(port=port, frontend='CLI')
    with MCPTransport(port, 115200) as transport:
        session = BusinessSession(transport)
        try:
            assert execute(session,['i2c','open','--bus','0'])['status'] == 0
            result = execute(session,['i2c','read-reg','--bus','0','--addr','0x50','--reg','00','--length','1'])
            assert result['status'] == 0 and result['data'] == b'\xa1', result
            results['signature'] = result
            for level in (1, 0):
                assert execute(session,['gpio','write','--line','0','--level',str(level)])['status'] == 0
                result = execute(session,['gpio','read','--line','1'])
                assert result['status'] == 0 and result['level'] == level, result
                results['gpio_' + str(level)] = result
        finally:
            if session.connected:
                session.gpio('write',line=0,level=0)
                if '0' in session.open_buses:
                    session.i2c('close',bus=0)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', action='append', required=True)
    args = parser.parse_args()
    for port in args.port:
        for check in (tk_check, cli_check):
            print(json.dumps(check(port), default=lambda value: value.hex() if isinstance(value, bytes) else str(value), ensure_ascii=False), flush=True)
