"""Hardware-free SPI role editing and mapped Tk regression coverage."""
import copy
import unittest
import app
import test_app as existing


class SpiRoleTests(unittest.TestCase):
    destroy_window = existing.TkTests.destroy_window
    pump = existing.TkTests.pump
    click = existing.TkTests.click
    feature = existing.TkTests.feature
    pin = existing.TkTests.pin
    visible_signals = existing.TkTests.visible_signals
    parameter = existing.V2TkTests.parameter
    geometry = existing.FeedbackTkTests.geometry
    color = existing.FeedbackTkTests.color
    assert_red = existing.FeedbackTkTests.assert_red

    def setUp(self):
        existing.V3TkTests.setUp(self)
        self.board.desc.update(schema=5, capabilities=0x1ff)
        mapping = self.board.state['active']
        mapping['uart1_business'] = False
        for bus in mapping['spi'].values():
            bus.update(role='master', slave_cs=255)
        self.board.confirmed = copy.deepcopy(mapping)
        self.click('read')

    def role(self, host, role):
        self.parameter('spi' + str(host), 'role', app.ROLE_NAMES[role])

    def test_slave_keeps_attachments_and_other_bus_and_blocks_save(self):
        before = copy.deepcopy(self.service.draft)
        calls = list(self.board.calls)
        self.role(2, 'slave')
        for key in ('external', 'external2', 'features', 'mcp2518fd', 'pins'):
            self.assertEqual(before[key], self.service.draft[key])
        self.assertEqual(before['spi']['3'], self.service.draft['spi']['3'])
        self.assertEqual(self.service.draft['spi']['2']['width'], 1)
        self.assertEqual(tuple(self.gui.parameter_widgets[('spi2', 'width')]['values']), ('1',))
        self.assertIn('spi2.slave_cs', self.visible_signals())
        self.assertEqual(self.gui.pin_vars['spi2.slave_cs'].get(), '待分配从机 CS')
        self.assertNotIn('spi2.io2', self.visible_signals())
        self.assertEqual(self.gui.mapping_labels['spi2.sck'][0].cget('text'), '输入')
        self.assertEqual(self.gui.mapping_labels['spi2.miso'][0].cget('text'), '输出')
        self.assertIn('spi2', self.gui.conflicting_devices)
        self.assertIn('external', self.gui.conflicting_devices)
        self.assertIn('请选择', self.gui.conflict_labels['spi2.slave_cs'].cget('text'))
        self.assertTrue(self.gui.buttons['save'].instate(['disabled']))
        with self.assertRaises(ValueError):
            self.service.save()
        self.assertEqual(calls, self.board.calls)

    def test_slave_cs_choices_direction_and_save_candidate_summary(self):
        self.parameter('external', 'enabled', False)
        self.role(2, 'slave')
        self.pin('spi2.slave_cs', 27)
        self.gui.overview.mode_var.set('draft')
        self.gui.overview.refresh()
        self.assertIn('本机角色：从机；输出', self.gui.overview.all_cards[21]['detail'])
        self.assertIn(35, self.gui._pin_choices['spi2.slave_cs'].values())
        self.assertNotIn(35, self.gui._pin_choices['spi2.miso'].values())
        self.assertFalse(self.gui.buttons['save'].instate(['disabled']))
        self.click('save')
        self.assertEqual(self.board.state['candidate']['spi']['2']['role'], 'slave')
        self.assertEqual(self.board.state['candidate']['spi']['2']['slave_cs'], 27)
        summary = self.gui.candidate_changes()
        self.assertIn('本机角色', summary)
        self.assertIn('从机', summary)
        self.assertIn('从机 CS', summary)
        self.assertNotIn('主机独占', summary)
        self.gui.overview.mode_var.set('current')
        self.gui.overview.refresh()
        self.assertIn('本机角色：主机；双向', self.gui.overview.all_cards[21]['detail'])
        self.gui.overview.mode_var.set('candidate')
        self.gui.overview.refresh()
        self.assertIn('本机角色：从机；输出', self.gui.overview.all_cards[21]['detail'])
        self.assertFalse(self.showerror.called)

    def test_spi3_input_only_miso_marks_pin_and_can_then_restores(self):
        self.role(3, 'slave')
        self.assertIn('GPIO36', self.gui.conflict_labels['spi3.miso'].cget('text'))
        self.assertNotIn(36, self.gui._pin_choices['spi3.miso'].values())
        self.assertIn(36, self.gui._pin_choices['spi3.mosi'].values())
        self.assertIn('can', self.gui.conflicting_devices)
        self.assert_red(self.gui.feature_widgets['can'])
        self.role(3, 'master')
        self.assertNotIn('can', self.gui.conflicting_devices)
        self.assertNotIn('spi3.slave_cs', self.visible_signals())
        self.assertEqual(self.gui.mapping_labels['spi3.miso'][0].cget('text'), '输入')
        self.assertFalse(self.board.calls)

    def test_role_capability_is_per_controller_and_older_versions_disabled(self):
        for schema, caps in ((5, 0xff), (4, 0x7f), (3, 0x3f)):
            self.service.descriptor.update(schema=schema, capabilities=caps)
            if schema < 5:
                for bus in self.service.draft['spi'].values():
                    bus.pop('role', None)
                    bus.pop('slave_cs', None)
                for bus in self.service.snapshot['active']['spi'].values():
                    bus.pop('role', None)
                    bus.pop('slave_cs', None)
            view = self.service.view()
            self.gui.view = view
            self.gui._render(view)
            self.gui._update_controls()
            self.assertTrue(self.gui.parameter_widgets[('spi3', 'role')].instate(['disabled']))
            self.assertEqual(self.gui.parameter_widgets[('spi2', 'role')].instate(['disabled']), schema < 5)
            with self.assertRaises(ValueError):
                self.service.set_parameter('spi3', 'role', 'slave')

    def test_v1_shows_readonly_role_explanation(self):
        legacy = existing.MemoryBoard()
        self.board.desc, self.board.state = legacy.desc, legacy.state
        self.board.confirmed = legacy.confirmed
        self.click('read')
        self.assertFalse(self.gui.parameter_widgets)
        self.assertTrue(self.gui.legacy_role_hint.winfo_manager())
        self.assertIn('当前固件不支持角色配置', self.gui.legacy_role_hint.cget('text'))
        self.assertFalse(self.board.calls)

    def test_roles_and_diagnostics_keep_mapped_function_controls_stable(self):
        self.root.deiconify()
        self.root.geometry('980x650')
        self.gui.notebook.select(0)
        self.root.update()
        widgets = {str(key): value for key, value in self.gui.parameter_widgets.items()}
        widgets.update({key: self.gui.buttons[key] for key in ('save', 'check', 'export', 'reset')})
        initial = self.geometry(widgets)
        self.role(2, 'slave')
        self.assertEqual(initial, self.geometry(widgets))
        self.role(3, 'slave')
        self.assertEqual(initial, self.geometry(widgets))
        self.role(2, 'master')
        self.role(3, 'master')
        self.assertEqual(initial, self.geometry(widgets))
        for widget in self.gui.parameter_widgets.values():
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), self.root.winfo_rootx() + 980)
        self.assertFalse(self.board.calls)


if __name__ == '__main__':
    unittest.main()
