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
                if op=='snapshot':return self.status()
                self.scan_min=params['min']
                return {'blocks':[{'state':'Block{minecraft:stone}'}]}
        client=Client()
        result=descend_if_clear(client,65,0)
        self.assertFalse(result['used'])
        self.assertEqual([9,63,19],client.scan_min)

    def test_uses_fresh_position_after_flight_momentum_settles(self):
        class Client:
            index=0
            scan_min=None
            def status(self):
                return {'pos':[10.5,100,20.5],'velocity':[0,0,0],
                        'health':20,'guard_armed':True,'freefall_protocol':1}
            def request(self,op,**params):
                if op=='snapshot':
                    positions=[10.5,10.8,11.2,11.2,11.2,11.2]
                    x=positions[min(self.index,len(positions)-1)];self.index+=1
                    return {**self.status(),'pos':[x,100,20.5]}
                self.scan_min=params['min']
                return {'blocks':[{'state':'Block{minecraft:stone}'}]}
        client=Client()
        result=descend_if_clear(client,65,0)
        self.assertFalse(result['used'])
        self.assertEqual([10,63,19],client.scan_min)


if __name__=='__main__':unittest.main()
