import unittest

from physical_idle import parse_hid_idle_seconds, resume_ready


class Tests(unittest.TestCase):
    def test_parses_nanosecond_idle_and_fails_closed_if_missing(self):
        self.assertEqual(5.25, parse_hid_idle_seconds('"HIDIdleTime" = 5250000000'))
        self.assertIsNone(parse_hid_idle_seconds('no HID counter'))

    def test_foreground_is_allowed_only_after_real_quiet_and_stable_high_park(self):
        state = {'connected': True, 'world_session': 'same',
                 'pos': [100.5, 85, 200.5], 'health': 20,
                 'air_supply': 300, 'under_water': False,
                 'screen': '', 'manual_movement': False,
                 'window_active': True, 'safety_hold': {'active': False}}
        bounds = [[90, 110], [190, 210]]
        self.assertTrue(resume_ready(state, 'same', 5.1, 5.2, bounds))
        self.assertFalse(resume_ready(state, 'same', 4.9, 5.2, bounds))
        self.assertFalse(resume_ready(state, 'same', 5.1, 4.9, bounds))
        self.assertFalse(resume_ready({**state, 'health': 18}, 'same', 5.1, 5.2, bounds))
        self.assertFalse(resume_ready({**state, 'pos': [123, 85, 200]}, 'same', 5.1, 5.2, bounds))
        self.assertFalse(resume_ready({**state, 'safety_hold': {'active': True}},
                                      'same', 5.1, 5.2, bounds))


if __name__ == '__main__':
    unittest.main()
