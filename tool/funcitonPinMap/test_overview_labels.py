"""Real Tk regressions for the panorama's two fixed lines of pin information.

Run: python tool/funcitonPinMap/test_overview_labels.py
Only MemoryBoard fixtures are used; this never opens hardware transports.
"""
import copy
import unittest
from unittest.mock import patch

import test_stage2 as fixtures


class OverviewFunctionTkTests(unittest.TestCase):
    setUp = fixtures.Stage2TkTests.setUp
    destroy_window = fixtures.Stage2TkTests.destroy_window
    pump = fixtures.Stage2TkTests.pump
    click = fixtures.Stage2TkTests.click
    edit = fixtures.Stage2TkTests.edit

    def prepare_mapping(self):
        """Keep all physical choices, but occupy only I2C1 and logical GPIO6."""
        mapping = copy.deepcopy(self.service.snapshot['active'])
        for feature in ('can', 'dap', 'uart'):
            mapping['features'][feature] = False
        for bus in mapping['spi'].values():
            bus['enabled'] = False
        for name in ('external', 'external2'):
            mapping[name]['enabled'] = False
        mapping['i2c']['1'].update(enabled=True, scl=13, sda=14)
        mapping['gpio_lines']['6'].update(enabled=True, pin=35, mode='input')
        self.service.snapshot['active'] = copy.deepcopy(mapping)
        candidate = copy.deepcopy(mapping)
        candidate['i2c']['1']['scl'] = 25
        self.service.snapshot['candidate'] = candidate
        self.service.draft.update(copy.deepcopy(mapping))
        self.gui.view = self.service.view()
        self.gui._render(self.gui.view)
        self.root.deiconify()
        self.root.update()
        return self.gui.overview

    def mode(self, mode):
        overview = self.gui.overview
        overview.mode_var.set(mode)
        overview.refresh()
        self.root.update()

    def item(self, gpio, tag):
        canvas = self.gui.overview.canvas
        matches = [item for item in canvas.find_withtag(f'gpio-{gpio}')
                   if tag in canvas.gettags(item)]
        self.assertEqual(len(matches), 1, (gpio, tag, matches))
        return matches[0]

    def label(self, gpio):
        canvas = self.gui.overview.canvas
        return canvas.itemcget(self.item(gpio, 'card-function'), 'text')

    def geometry(self):
        overview = self.gui.overview
        canvas = overview.canvas
        return (dict(overview.card_bounds),
                {gpio: canvas.coords(self.item(gpio, 'card-title')) for gpio in overview.cards},
                overview.winfo_height(), canvas.winfo_height(), self.gui.notebook.winfo_rooty())

    def assert_function_bounds(self):
        overview = self.gui.overview
        canvas = overview.canvas
        for gpio, (left, top, right, bottom) in overview.card_bounds.items():
            item = self.item(gpio, 'card-function')
            box = canvas.bbox(item)
            if self.label(gpio):
                self.assertIsNotNone(box)
                self.assertGreaterEqual(box[0], left, (gpio, box, (left, right)))
                self.assertLessEqual(box[2], right, (gpio, box, (left, right)))
                self.assertGreaterEqual(box[1], top)
                self.assertLessEqual(box[3], bottom)
                title_box = canvas.bbox(self.item(gpio, 'card-title'))
                self.assertGreaterEqual(box[1], title_box[3], (gpio, title_box, box))

    def test_labels_move_with_selected_snapshot_without_changing_layout(self):
        overview = self.prepare_mapping()
        calls = copy.deepcopy(self.board.calls)
        reads = copy.deepcopy(self.board.reads)
        for width in (980, 1180):
            self.root.geometry(f'{width}x780+20+20')
            for show_all in (False, True):
                with self.subTest(width=width, show_all=show_all):
                    self.service.draft.update(copy.deepcopy(self.service.snapshot['active']))
                    self.gui.view = self.service.view()
                    self.gui._render(self.gui.view)
                    overview.show_all_var.set(show_all)
                    self.mode('current')
                    baseline = self.geometry()
                    self.assertEqual(self.label(13), 'I²C1 SCL')
                    self.assertEqual(self.label(25), '')
                    self.assertEqual(self.label(35), '路 6 输入')
                    self.assert_function_bounds()
                    self.mode('candidate')
                    self.assertEqual(self.label(13), '')
                    self.assertEqual(self.label(25), 'I²C1 SCL')
                    self.assertEqual(self.geometry(), baseline)
                    self.mode('draft')
                    self.edit('i2c1', 'scl', '26')
                    self.assertEqual(self.label(13), '')
                    self.assertEqual(self.label(26), 'I²C1 SCL')
                    self.assertEqual(self.geometry(), baseline)
                    self.edit('i2c1', 'enabled', False)
                    self.assertEqual(self.label(26), '')
                    self.assertEqual(overview.cards[26]['state'], 'free')
                    self.assertEqual(self.geometry(), baseline)
                    self.edit('i2c1', 'enabled', True)
                    self.edit('gpio.6', 'pin', '26')
                    self.assertEqual(overview.cards[26]['state'], 'conflict')
                    text_items = [overview.canvas.itemcget(item, 'text')
                                  for item in overview.canvas.find_withtag('gpio-26')
                                  if overview.canvas.type(item) == 'text']
                    self.assertIn('!', ''.join(text_items))
                    self.assertIn('i2c1.scl', overview.cards[26]['detail'])
                    self.assertIn('gpio.6', overview.cards[26]['detail'])
                    self.assertTrue(overview.cards[26]['function'].startswith('路 6 输入、I²C1 SCL'))
                    self.assert_function_bounds()
                    self.assertEqual(self.geometry(), baseline)
                    self.edit('gpio.7', 'pin', '26')
                    self.edit('gpio.7', 'mode', 'open_drain')
                    self.edit('gpio.7', 'enabled', True)
                    self.assertTrue(self.label(26).endswith('…'))
                    self.assertIn('gpio.7', overview.cards[26]['detail'])
                    self.assert_function_bounds()
                    self.assertEqual(self.geometry(), baseline)
                    with patch('overview.messagebox.showinfo') as dialog:
                        overview._open_pin(26)
                    self.assertEqual(dialog.call_args.args[1], overview.cards[26]['detail'])
                    self.edit('gpio.7', 'enabled', False)
                    self.edit('gpio.6', 'pin', '35')
                    self.assertEqual(self.label(26), 'I²C1 SCL')
                    self.assertEqual(self.geometry(), baseline)
                    self.mode('current')
                    self.assertEqual(self.label(13), 'I²C1 SCL')
                    self.assertEqual(self.label(26), '')
                    self.assertEqual(self.geometry(), baseline)
        self.assertEqual(self.board.calls, calls)
        self.assertEqual(self.board.reads, reads)

    def test_gpio_direction_fixed_purposes_and_blank_reserved_cards(self):
        overview = self.prepare_mapping()
        overview.show_all_var.set(True)
        self.mode('draft')
        self.assertEqual(self.label(6), 'Flash')
        self.assertEqual(self.label(12), 'EEPROM')
        for gpio in (0, 2, 5, 20, 24, 28, 29, 30, 31, 37, 38):
            self.assertEqual(self.label(gpio), '', gpio)
        self.edit('gpio.6', 'pin', '25')
        for mode, text in (('input', '路 6 输入'), ('output', '路 6 输出'),
                           ('open_drain', '路 6 开漏输出')):
            self.edit('gpio.6', 'mode', mode)
            self.assertEqual(self.label(25), text)
        self.edit('gpio.6', 'enabled', False)
        self.assertEqual(self.label(25), '')
        self.assertEqual(overview.cards[25]['state'], 'free')

    def test_existing_spi_uart_labels_and_uart1_reserved_use(self):
        overview = self.gui.overview
        self.root.deiconify()
        self.root.geometry('1180x780+20+20')
        overview.show_all_var.set(True)
        self.mode('current')
        active = self.service.snapshot['active']
        self.assertEqual(self.label(active['pins']['uart.tx']), 'UART2 TX')
        self.assertEqual(self.label(active['spi']['2']['miso']), 'SPI2 MISO')
        self.assertIn('UART1', self.label(4))
        self.service.draft['features']['serial'] = False
        self.service.draft['uart1_business'] = False
        self.gui.view = self.service.view()
        self.gui._render(self.gui.view)
        self.mode('draft')
        for gpio in (4, 34):
            self.assertEqual(self.label(gpio), '')
            self.assertIn('保留', overview.cards[gpio]['detail'])
        self.mode('current')
        self.assertIn('UART1', self.label(4))

    def test_unread_device_does_not_invent_function_labels(self):
        self.gui.overview.set_view(None)
        self.root.update()
        self.assertFalse(self.gui.overview.canvas.find_withtag('card-function'))
        self.assertFalse(self.gui.overview.cards)


if __name__ == '__main__':
    unittest.main()
