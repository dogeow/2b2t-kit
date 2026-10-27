import unittest
from unittest.mock import patch,Mock
from projection_painting import geometry,ready_weapon


class PaintingGeometryTest(unittest.TestCase):
    def test_switching_from_painting_to_sword_waits_for_real_cooldown(self):
        c=object();checkpoint=Mock(side_effect=[{'attack_strength':.72},{'attack_strength':1.,'guard_busy':False}])
        with patch('projection_painting.select_container_hand')as select,patch('projection_painting.time.sleep'):
            self.assertEqual(1.,ready_weapon(c,checkpoint)['attack_strength'])
        select.assert_called_once_with(c);self.assertEqual(2,checkpoint.call_count)
    def test_source_three_by_three_center_uses_its_real_south_wall(self):
        anchor,face,pose=geometry({'facing':3,'pos':[761014.5,68.5,797833.03125]})
        self.assertEqual([761014,68,797832],anchor);self.assertEqual('south',face)
        self.assertEqual([761014.5,67.1,797835.53125],pose)
