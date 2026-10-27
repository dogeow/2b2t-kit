import math,unittest
from material_jobs.long_air_transit import candidates,choose,choose_short


class Client:
    world='w';last=''
    def __init__(self):self.calls=[]
    def request(self,op,**params):
        self.calls.append((op,params));self.last='scan-'+str(len(self.calls))
        width=max(params['max'][i]-params['min'][i]for i in(0,2))
        n=math.prod(b-a+1 for a,b in zip(params['min'],params['max']))
        return {'id':self.last,'world_session':self.world,'phase':'done'if width<=130 else'error',
                'scan_cells_read':n if width<=130 else 0,'scan_total_cells':n,'blocks':[]}


class TransitTest(unittest.TestCase):
    def test_long_straight_leg_stays_inside_native_sweep_budget(self):
        here=[0.5,144.,0.5];target=[1300.5,144.,500.5]
        for point in candidates(here,target):
            self.assertLessEqual(math.dist(here,point),256)
            self.assertTrue(point[0]==here[0]or point[2]==here[2])
            volume=(abs(point[0]-here[0])+1.6)*2.8*(abs(point[2]-here[2])+1.6)
            self.assertLess(volume,8192)
    def test_unloaded_long_corridor_falls_back_to_a_current_loaded_shorter_one(self):
        c=Client();point,proof=choose(c,[.5,144.,.5],[1300.5,144.,500.5],lambda:None)
        self.assertEqual([128.5,144.,.5],point)
        self.assertEqual(3,len(proof));self.assertTrue(all(op=='scan'for op,_ in c.calls))
    def test_solid_block_or_foreign_read_never_authorizes_movement(self):
        c=Client();original=c.request
        def blocked(*a,**kw):return {**original(*a,**kw),'blocks':[{'pos':[1,144,0]}]}
        c.request=blocked;point,proof=choose(c,[.5,144.,.5],[300.5,144.,.5],lambda:None)
        self.assertIsNone(point);self.assertTrue(all(not p['movement_dispatched']for p in proof))
        c.request=lambda *a,**kw:{'id':'foreign','world_session':'w'}
        with self.assertRaisesRegex(RuntimeError,'another world/request'):choose(c,[.5,144.,.5],[300.5,144.,.5],lambda:None)
    def test_short_destination_does_not_add_long_leg_reads(self):
        c=Client();point,proof=choose(c,[.5,144.,.5],[30.5,144.,.5],lambda:None)
        self.assertIsNone(point);self.assertEqual([],proof);self.assertEqual([],c.calls)
    def test_loading_boundary_uses_only_a_completely_read_shorter_segment(self):
        c=Client();original=c.request
        def loading(op,**kw):
            r=original(op,**kw);width=max(kw['max'][i]-kw['min'][i]for i in(0,2))
            if width>18:r.update(phase='waiting',scan_cells_read=0)
            return r
        c.request=loading;p,proof=choose_short(c,[.5,140.,.5],[-300.5,140.,.5],lambda:None)
        self.assertEqual([-15.5,140.,.5],p);self.assertEqual(3,len(proof));self.assertTrue(all(op=='scan'for op,_ in c.calls))


if __name__=='__main__':unittest.main()
