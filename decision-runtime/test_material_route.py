import math
import unittest

from material_route import next_relay


class Tests(unittest.TestCase):
    def test_far_route_uses_high_bounded_relay(self):
        start=[0,85,0]
        home=[350,110,400]
        relay=next_relay(start,home)
        self.assertEqual(150,relay[1])
        self.assertAlmostEqual(280,math.hypot(relay[0],relay[2]))
        self.assertLess(math.hypot(relay[0]-home[0],relay[2]-home[2]),400)
        self.assertIsNone(next_relay(relay,home))

    def test_nearby_or_invalid_route(self):
        self.assertIsNone(next_relay([0,85,0],[100,110,100]))
        with self.assertRaises(ValueError):
            next_relay([math.nan,85,0],[100,110,100])


if __name__=='__main__':unittest.main()
