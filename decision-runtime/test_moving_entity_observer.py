import unittest
from material_jobs.moving_entity_observer import candidates


class MovingEntityObserverTests(unittest.TestCase):
    def state(self):
        return {'connected': True, 'world_session': 'w', 'screen': '',
            'supervision_lease': {'kind': 'materials', 'job_session': 't', 'world_session': 'w'},
            'entities': [{'uuid': 's', 'type': 'minecraft:squid', 'health': 10,
                          'has_custom_name': False, 'pos': [1, 50, 2]}]}

    def test_host_nearby_snapshot_without_alive_flag_still_observes_real_squid(self):
        s = self.state()
        self.assertEqual('s', candidates(s, 'w', 't', 'minecraft:squid')[0]['uuid'])

    def test_only_requested_height_layer_and_ordinary_unnamed_living_squid(self):
        for y in (50, 64):
            s = self.state(); s['entities'][0]['pos'][1] = y
            self.assertEqual(1, len(candidates(s, 'w', 't', 'minecraft:squid')))
        for field, value in (('pos', [1, 49.9, 2]), ('pos', [1, 64.1, 2]),
                             ('type', 'minecraft:glow_squid'), ('has_custom_name', True),
                             ('health', 0), ('alive', False)):
            s = self.state(); s['entities'][0][field] = value
            self.assertEqual([], candidates(s, 'w', 't', 'minecraft:squid'))

    def test_foreign_world_owner_and_manual_control_never_supply_targets(self):
        for field, value in (('world_session', 'old'), ('manual_movement', True),
                             ('connected', False), ('screen', 'InventoryScreen')):
            s = self.state(); s[field] = value
            self.assertEqual([], candidates(s, 'w', 't', 'minecraft:squid'))
        s = self.state(); s['supervision_lease']['job_session'] = 'other'
        self.assertEqual([], candidates(s, 'w', 't', 'minecraft:squid'))


if __name__ == '__main__':
    unittest.main()
