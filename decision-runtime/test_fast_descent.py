import unittest

from fast_descent import clear_column, descend_if_clear


class FastDescentTest(unittest.TestCase):
    def test_non_air_or_fluid_prevents_freefall(self):
        self.assertTrue(clear_column([]))
        self.assertFalse(clear_column([{'state':'Block{minecraft:stone}'}]))
        self.assertFalse(clear_column([{'state':'Block{minecraft:water}[level=0]'}]))

    def test_short_drop_never_disables_flight(self):
        class Client:
            def status(self):return {'pos':[10.5,120,20.5],'health':20,'guard_armed':True,'freefall_protocol':1}
            def request(self,*args,**kwargs):raise AssertionError('No game action expected')
        self.assertFalse(descend_if_clear(Client(),100)['used'])

    def test_old_host_refuses_to_start_unbraked_freefall(self):
        class Client:
            def status(self):return {'pos':[10.5,215,20.5],'health':20,'guard_armed':True}
            def request(self,*args,**kwargs):raise AssertionError('No game action expected')
        self.assertFalse(descend_if_clear(Client(),90)['used'])

    def test_python_clearance_scan_includes_native_two_block_margin(self):
        class Client:
            scan_min=None
            def status(self):
                return {'pos':[10.5,100,20.5],'velocity':[0,0,0],
                        'health':20,'guard_armed':True,'freefall_protocol':1}
            def request(self,op,**params):
                self.scan_min=params['min']
                return {'blocks':[{'state':'Block{minecraft:stone}'}]}
        client=Client()
        result=descend_if_clear(client,65,0)
        self.assertFalse(result['used'])
        self.assertEqual([9,63,19],client.scan_min)


if __name__=='__main__':unittest.main()
