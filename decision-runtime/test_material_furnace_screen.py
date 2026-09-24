import unittest
from material_client import Client, Handoff


class FurnaceScreenTest(unittest.TestCase):
    def client(self, screen):
        c = Client.__new__(Client)
        c.world = 'same-world'
        c.rev = 7
        c.raw = lambda: {'connected': True, 'world_session': 'same-world', 'control_revision': 7,
                         'manual_movement': False, 'screen': screen}
        return c

    def test_owned_furnace_ui_is_readable(self):
        self.assertEqual(self.client('BlastFurnaceScreen').status()['screen'], 'BlastFurnaceScreen')
        self.assertEqual(self.client('FurnaceScreen').status()['screen'], 'FurnaceScreen')
        self.assertEqual(self.client('AnvilScreen').status()['screen'], 'AnvilScreen')
        self.assertEqual(self.client('BrewingStandScreen').status()['screen'], 'BrewingStandScreen')

    def test_unrelated_ui_still_hands_back_control(self):
        with self.assertRaises(Handoff): self.client('GrindstoneScreen').status()


if __name__ == '__main__': unittest.main()
