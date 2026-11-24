"""Regressions for unassigned Stage2 pins and sequential local editing."""
import copy
import unittest
from unittest.mock import patch

import test_stage2 as fixtures
from backend import cli


class Pin255ValidationTests(unittest.TestCase):
    def setUp(self):
        self.mapping = fixtures.mapping()
        self.desc = fixtures.existing.MemoryBoard().desc
        self.desc.update(schema=6, capabilities=0x7ff)

    def preview(self):
        return cli.build_tables(self.desc, dict(active=self.mapping, candidate=None), self.mapping)

    def test_disabled_unassigned_rows_have_no_pin_error_or_occupancy(self):
        self.assertFalse(any(row['signal'].startswith(('i2c', 'gpio.'))
                             for row in self.preview()['invalid_pins']))
        self.assertFalse(any(row['gpio'] == 255 for row in self.preview()['candidate_occupancy']))

    def test_enabled_unassigned_rows_require_pin_without_treating_255_as_hardware(self):
        self.mapping['gpio_lines']['6']['enabled'] = True
        self.mapping['i2c']['1']['enabled'] = True
        problems = {row['signal']: row for row in self.preview()['invalid_pins']}
        for signal in ('gpio.6', 'i2c1.scl', 'i2c1.sda'):
            self.assertIn('no assigned GPIO', problems[signal]['reason'])
        self.mapping['gpio_lines']['6']['pin'] = 35
        self.assertNotIn('gpio.6', {row['signal'] for row in self.preview()['invalid_pins']})


class Pin255TkTests(unittest.TestCase):
    setUp = fixtures.Stage2TkTests.setUp
    destroy_window = fixtures.Stage2TkTests.destroy_window
    pump = fixtures.Stage2TkTests.pump
    click = fixtures.Stage2TkTests.click
    edit = fixtures.Stage2TkTests.edit

    def test_unassigned_can_choose_pin_before_or_after_enabling(self):
        before = copy.deepcopy(self.board.state)
        self.edit('gpio.6', 'enabled', True)
        self.assertTrue(self.service.draft['gpio_lines']['6']['enabled'])
        self.assertEqual(self.service.draft['gpio_lines']['6']['pin'], 255)
        self.assertIn('35', self.gui.stage2.widgets[('gpio.6', 'pin')]['values'])
        self.edit('gpio.6', 'pin', '35')
        self.assertEqual(self.service.draft['gpio_lines']['6']['pin'], 35)
        self.assertNotIn('gpio.6', {row['signal'] for row in self.service.view()['preview_tables']['invalid_pins']})
        self.edit('gpio.7', 'pin', '39')
        self.edit('gpio.7', 'enabled', True)
        self.assertEqual(self.service.draft['gpio_lines']['7']['pin'], 39)
        self.assertEqual(self.board.state, before)
        self.assertEqual(self.board.calls, [])

    def test_focusout_without_change_does_not_submit_or_rewrite_draft(self):
        before = copy.deepcopy(self.service.draft)
        with patch.object(self.gui, '_edit_local_draft') as local:
            self.gui.stage2.edit(('gpio.6', 'pin'))
            self.gui.stage2.edit(('gpio.6', 'enabled'))
            self.gui.stage2.edit(('i2c0', 'clock_hz'))
        local.assert_not_called()
        self.assertEqual(self.service.draft, before)

    def test_pull_choices_follow_actual_hardware_and_restore_on_pin_change(self):
        pane = self.gui.stage2
        self.assertEqual(tuple(pane.widgets[('gpio.6', 'pull')]['values']), cli.GPIO_PULLS)
        self.edit('gpio.6', 'pin', '35')
        self.assertEqual(tuple(pane.widgets[('gpio.6', 'pull')]['values']), ('none',))
        self.edit('gpio.6', 'pin', '32')
        self.assertEqual(tuple(pane.widgets[('gpio.6', 'pull')]['values']), cli.GPIO_PULLS)


if __name__ == '__main__':
    unittest.main()
