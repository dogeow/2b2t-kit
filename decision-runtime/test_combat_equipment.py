import tempfile
import unittest
from pathlib import Path
from material_jobs.combat_equipment import ammunition_target, prepare


def state(*rows):
    return {'world_session': 'current', 'time': 1234, 'inventory': list(rows)}


def bow(infinite=False):
    return {'slot': 8, 'item': 'minecraft:bow', 'count': 1, 'durability': 300,
            'enchantments': [{'id': 'minecraft:infinity', 'level': 1}] if infinite else []}


def arrows(n, item='minecraft:arrow', slot=15):
    return {'slot': slot, 'item': item, 'count': n}


class Backend:
    def __init__(self, initial, after=None):
        self.current = initial
        self.after = after if after is not None else initial
        self.fetched = []

    def ensure_client(self):
        return self

    def status(self):
        return self.current

    def fetch(self, targets):
        self.fetched.append(targets)
        self.current = self.after
        return {'phase': 'done'}


class CombatEquipmentTest(unittest.TestCase):
    def test_infinity_still_requires_one_normal_arrow(self):
        self.assertEqual(ammunition_target(state(bow(True))), 1)
        self.assertEqual(ammunition_target(state(bow(True), arrows(16, 'minecraft:tipped_arrow'))), 1)
        self.assertEqual(ammunition_target(state(bow(True), arrows(1, slot=40))), 0)

    def test_finite_bow_reserves_real_projectiles(self):
        self.assertEqual(ammunition_target(state(bow(), arrows(6))), 16)
        self.assertEqual(ammunition_target(state(bow(), arrows(6), arrows(5, 'minecraft:spectral_arrow', 16))), 11)
        self.assertEqual(ammunition_target(state(bow(), arrows(16, 'minecraft:tipped_arrow'))), 0)

    def test_container_slots_and_armor_are_not_carried_ammunition(self):
        self.assertEqual(ammunition_target(state(bow(True), arrows(64, slot=45), arrows(64, slot=36))), 1)
        self.assertEqual(ammunition_target(state(arrows(64))), 0)

    def test_ready_inventory_avoids_supply_trip(self):
        backend = Backend(state(bow(True), arrows(1)))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(prepare(backend, Path(tmp))['phase'], 'done')
        self.assertEqual(backend.fetched, [])

    def test_fetch_is_verified_against_actual_backpack(self):
        backend = Backend(state(bow(True)), state(bow(True), arrows(1)))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(prepare(backend, Path(tmp))['phase'], 'done')
            self.assertTrue((Path(tmp)/'bow-ammunition.json').exists())
        self.assertEqual(backend.fetched, [{'minecraft:arrow': 1}])

    def test_done_receipt_without_arrow_does_not_allow_diving(self):
        backend = Backend(state(bow(True)))
        with tempfile.TemporaryDirectory() as tmp:
            result = prepare(backend, Path(tmp))
        self.assertEqual(result['code'], 'WAIT_COMBAT_EQUIPMENT')
        self.assertEqual(result['requirements'], {'minecraft:arrow': 1})


if __name__ == '__main__':
    unittest.main()
