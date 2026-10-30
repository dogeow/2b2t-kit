import unittest
from projected_bent_channel import path_for,flow_after
from projected_source_column import SOURCE,AIR,geometry
from test_projected_source_column import fixture,change,LOW,HIGH,WORLD
class BentFlowTest(unittest.TestCase):
    def scene(self):
        m,f=fixture()
        for y in range(59,68):
            for x in range(10,13):change(f,[x,y,20],SOURCE)
        plan=geometry(m,f,LOW,HIGH,WORLD);before={tuple(v['pos']):v['state']for v in f['blocks']}
        for i,p in enumerate(path_for(LOW,HIGH)):change(f,p,f'Block{{minecraft:water}}[level={i}]')
        f.update(scan_cells_read=504,scan_total_cells=504)
        return f,plan,before
    def test_exact_path(self):
        p=path_for(LOW,HIGH);self.assertEqual(p[0],[12,68,20]);self.assertEqual(p[-1],[9,68,24]);self.assertEqual(len(set(map(tuple,p))),8)
    def test_complete_flow(self):
        f,p,b=self.scene();self.assertTrue(flow_after(f,WORLD,LOW,HIGH,p,b))
    def test_wrong_terminal(self):
        for state in [AIR,SOURCE,'Block{minecraft:water}[level=8]']:
            f,p,b=self.scene();change(f,[9,68,24],state);self.assertFalse(flow_after(f,WORLD,LOW,HIGH,p,b))
    def test_lost_source_and_leak(self):
        for pos in [[11,63,20],[8,64,24]]:
            f,p,b=self.scene();change(f,pos,AIR if pos[0]==11 else SOURCE);self.assertFalse(flow_after(f,WORLD,LOW,HIGH,p,b))
    def test_dropper_clock(self):
        f,p,b=self.scene();change(f,[11,58,20],'Block{minecraft:dropper}[facing=up,triggered=true]');self.assertTrue(flow_after(f,WORLD,LOW,HIGH,p,b))
    def test_lost_seal_and_roof_obstruction(self):
        for pos,state in [([9,63,20],AIR),([12,69,20],'Block{minecraft:glass}')]:
            f,p,b=self.scene();change(f,pos,state);self.assertFalse(flow_after(f,WORLD,LOW,HIGH,p,b))
    def test_bad_frame(self):
        for key,value in [('world_session','old'),('scan_coherent',False),('scan_cells_read',503)]:
            f,p,b=self.scene();f[key]=value;self.assertFalse(flow_after(f,WORLD,LOW,HIGH,p,b))
if __name__=='__main__':unittest.main()
