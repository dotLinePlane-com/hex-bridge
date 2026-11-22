"""Read a real board through actual Tk widgets; reject every profile mutation.

Run: python tool/funcitonPinMap/verify_readonly.py --port COM3 --baud 115200
Only DESCRIBE, READ and hardware identity queries are permitted.
"""
import argparse
import json
import time
import tkinter as tk
from unittest.mock import patch
import app
import backend


class ReadOnlyDevice(backend.cli.Device):
    operations = []

    def request(self, op, data=b''):
        if op not in ('describe', 'read'):
            raise RuntimeError(f'Read-only verification rejected operation: {op}')
        self.operations.append(op)
        return super().request(op, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--baud', type=int, default=115200)
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    ReadOnlyDevice.operations = []
    service = backend.ProfileService(device_factory=ReadOnlyDevice)
    gui = app.ProfileApp(root, service)
    gui.port_var.set(args.port)
    gui.baud_var.set(str(args.baud))
    errors = []
    root.report_callback_exception = lambda *error: errors.append(repr(error))
    end = time.monotonic() + 20

    def check():
        if gui.busy and time.monotonic() < end:
            root.after(30, check)
            return
        try:
            if gui.busy or errors or not gui.view:
                raise RuntimeError(errors or gui.status_var.get())
            view = gui.view
            if len(gui.notebook.tabs()) != 2:
                raise RuntimeError('Expected function control and pin configuration tabs')
            if view['dirty'] or gui.overview.mode_var.get() != 'current':
                raise RuntimeError('First read must preserve current wiring and a clean draft')
            expected_modes = ['current', 'draft']
            if view['snapshot']['candidate'] is not None:
                expected_modes.insert(1, 'candidate')
            # These controls must only inspect the locally read snapshot.
            before = list(ReadOnlyDevice.operations)
            for tab in gui.notebook.tabs():
                gui.notebook.select(tab)
                root.update_idletasks()
            gui.overview.open_details()
            gui.overview.show_all_button.invoke()
            if len(gui.overview.cards) != 40:
                raise RuntimeError('Expanded panorama must show GPIO0 through GPIO39')
            all_counts = dict(gui.overview.counts)
            for mode in expected_modes:
                gui.overview.mode_buttons[mode].invoke()
            gui.overview.mode_buttons['current'].invoke()
            gui.overview.show_all_button.invoke()
            if ReadOnlyDevice.operations != before:
                raise RuntimeError('Local inspection unexpectedly accessed the device')
            print(json.dumps({
                'schema': view['descriptor']['schema'], 'board': view['descriptor']['board'],
                'capabilities': view['descriptor'].get('capabilities', 0),
                'revision': view['snapshot']['revision'], 'phase': view['snapshot']['phase'],
                'candidate_id': view['snapshot']['candidate_id'], 'source_revision': view['source_revision'],
                'tabs': [gui.notebook.tab(tab, 'text').strip() for tab in gui.notebook.tabs()],
                'signal_widgets': len(gui.pin_boxes),
                'visible_signals': [signal for signal, box in gui.pin_boxes.items() if box.winfo_manager()],
                'parameters': len(gui.parameter_widgets),
                'spi_controls': [f'{instance}.{field}' for instance, field in gui.parameter_widgets],
                'spi_roles': {
                    str(host): {
                        'supported': view['descriptor']['schema'] >= 5 and bool(view['descriptor'].get('capabilities', 0) & (0x80 if host == 2 else 0x100)),
                        'current': view['snapshot']['active'].get('spi', {}).get(str(host), {}).get('role', 'master'),
                        'candidate': view['snapshot']['candidate'].get('spi', {}).get(str(host), {}).get('role', 'master') if view['snapshot']['candidate'] else None,
                        'draft': view['draft'].get('spi', {}).get(str(host), {}).get('role', 'master'),
                    } for host in (2, 3)
                },
                'uart1_business_supported': view['descriptor']['schema'] >= 4 and bool(view['descriptor'].get('capabilities', 0) & 64),
                'uart1_roles': {
                    'current': gui._uart1_role(view['snapshot']['active']),
                    'candidate': gui._uart1_role(view['snapshot']['candidate']) if view['snapshot']['candidate'] else None,
                    'draft': gui._uart1_role(view['draft']),
                },
                'view_modes': expected_modes,
                'visible_gpio': gui.overview.visible_gpios, 'counts': gui.overview.counts,
                'all_gpio_counts': all_counts, 'dirty': view['dirty'],
                'requires_reconnect': view['requires_reconnect'],
                'profile_queries': ReadOnlyDevice.operations,
            }, indent=2, ensure_ascii=False))
        except Exception as exc:
            errors.append(str(exc))
        finally:
            gui._closed = True
            root.after_cancel(gui._poll_id)
            root.destroy()

    with patch.object(app.messagebox, 'showerror', side_effect=lambda *a, **k: errors.append(str(a))):
        gui.buttons['read'].invoke()
        root.after(30, check)
        root.mainloop()
    if errors:
        raise SystemExit('; '.join(errors))


if __name__ == '__main__':
    main()
