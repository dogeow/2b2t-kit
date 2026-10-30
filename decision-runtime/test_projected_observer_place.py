import tempfile,unittest,copy,json
from pathlib import Path
from projected_observer_place import place
class Fake:
    world='w';task='owner';last='';protocol=1
    def __init__(self):self.used=0;self.scans=0;self.tick=0;self.uncertain=False;self.existing=False
    def status(self):return {'projected_observer_place_protocol':self.protocol,'health':20,'guard_armed':True,'guard_busy':False,'screen':'','manual_movement':False,'world_session':'w','supervision_lease':{'job_session':'owner'},'inventory':[{'item':'minecraft:observer','slot':0,'count':2-self.used}]}
    def request(self,op,**kw):
        if op=='projection_model':return {'projection_model':{'placement_key':'key','expected':[{'pos':[2,3,4],'state':'Block{minecraft:observer}[facing=south,powered=true]'}]}}
        assert op=='interact';assert kw['projected_observer_place'];assert kw['place_pos']==[2,3,4];self.last='one'
        if getattr(self,'early_reject',False):return {'id':'one','world_session':'w','phase':'error','projected_observer_place_protocol':1,'detail':'Target interaction face is occluded or out of reach'}
        self.used+=1;return {'id':'one','world_session':'w','phase':'waiting'if self.uncertain else'done'}
    def checked(self,op,**kw):
        if op=='select_item':return self.status()
        assert op=='scan';self.tick+=1;target=kw['min']==kw['max'];count=1 if target else 2
        rows=[{'pos':[1,3,4],'state':'Block{minecraft:stone}'}]if not target else []
        if self.used or self.existing:rows.append({'pos':[2,3,4],'state':'Block{minecraft:observer}[facing=south,powered=false]'})
        if target:self.scans+=1
        return {'world_session':'w','phase':'done','scan_cells_read':count,'scan_total_cells':count,'scan_coherent':True,'scan_predictions':{'complete':True,'pending_count':1 if target and self.scans<3 else 0},'blocks':rows,'time':self.tick}
class ObserverPlaceTest(unittest.TestCase):
    def run_one(self,c,d):return place(c,[2,3,4],[1,3,4],'east','key',Path(d)/'one')
    def test_waits_for_prediction_free_frames_without_a_second_use(self):
        c=Fake()
        with tempfile.TemporaryDirectory()as d:r=self.run_one(c,d);self.assertTrue(r['complete']);self.assertEqual(len(r['observations']),3)
        self.assertEqual(c.used,1);self.assertEqual(c.scans,5)
    def test_old_host_has_no_side_effect(self):
        c=Fake();c.protocol=0
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(RuntimeError):self.run_one(c,d)
        self.assertEqual(c.used,0)
    def test_occupied_cell_is_not_replaced(self):
        c=Fake();c.existing=True
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(RuntimeError):self.run_one(c,d)
        self.assertEqual(c.used,0)
    def test_unknown_use_identity_remains_pending_and_is_never_retried(self):
        c=Fake();c.uncertain=True
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(RuntimeError):self.run_one(c,d)
            b=json.loads((Path(d)/'one/progress.json').read_text());self.assertEqual(b['pending'],'one_normal_observer_use');self.assertEqual(b['request_id'],'one')
        self.assertEqual(c.used,1)
    def test_exact_native_visible_face_precheck_has_no_input_and_does_not_retry(self):
        c=Fake();c.early_reject=True
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(RuntimeError):self.run_one(c,d)
            b=json.loads((Path(d)/'one/progress.json').read_text());self.assertIsNone(b['pending']);self.assertTrue(b['rejected_before_use'])
        self.assertEqual(c.used,0)
    def test_bad_support_geometry_has_no_use(self):
        c=Fake()
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(ValueError):place(c,[2,3,4],[1,3,4],'west','key',Path(d)/'one')
        self.assertEqual(c.used,0)
if __name__=='__main__':unittest.main()
