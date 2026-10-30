import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from projected_trapdoor_waterlog import waterlog,drain,row_bounds,receipt
WET='Block{minecraft:spruce_trapdoor}[facing=south,half=bottom,open=false,powered=false,waterlogged=true]';DRY=WET.replace('true','false')
SLAB='Block{minecraft:cobblestone_slab}[type=top,waterlogged=false]';FLOOR=[15,62,21];TARGET=[15,65,20]
class Fake:
    world='w';task='owner';last='';protocol=1
    def __init__(self):
        self.model={'placement_key':'k','expected':[{'pos':[x,65,20],'state':WET}for x in range(10,39)]+[{'pos':FLOOR,'state':SLAB}]};self.states={tuple(v['pos']):v['state'].replace('waterlogged=true','waterlogged=false')for v in self.model['expected']};self.states[tuple(FLOOR)]=SLAB.replace('false','true');self.empty=1;self.water=1;self.uses=0;self.tick=0;self.unknown=False;self.leak=False
    def status(self):return {'projected_trapdoor_waterlog_protocol':self.protocol,'projected_waterlog_drain_protocol':1,'health':20,'food':20,'air_supply':300,'guard_armed':True,'world_session':'w','screen':'','manual_movement':False,'guard_busy':False,'supervision_lease':{'job_session':'owner'},'projection_selection':{'key':'k'},'hand':{'item':'minecraft:water_bucket','count':1},'inventory':[{'slot':0,'item':'minecraft:bucket','count':self.empty},{'slot':1,'item':'minecraft:water_bucket','count':self.water}]}
    def checked(self,op,**kw):
        if op=='select_item':return self.status()
        assert op=='scan';self.tick+=1;lo=kw['min'];hi=kw['max'];rows=[{'pos':list(p),'state':s}for p,s in self.states.items()if all(lo[i]<=p[i]<=hi[i]for i in range(3))]
        if self.leak and self.uses and hi!=lo:rows.append({'pos':[16,64,20],'state':'Block{minecraft:water}[level=8]'})
        count=1
        for i in range(3):count*=hi[i]-lo[i]+1
        return {'world_session':'w','phase':'done','scan_cells_read':count,'scan_total_cells':count,'scan_coherent':True,'scan_predictions':{'complete':True,'pending_count':0},'blocks':rows,'time':self.tick}
    def request(self,op,**kw):
        self.uses+=1;self.last='one';fill=op=='bucket_fill';target=kw['pos'];self.empty+=-1 if fill else 1;self.water+=1 if fill else-1;expected=kw['expected_dry_state']if fill else kw['expected_wet_state'];self.states[tuple(target)]=expected
        return {'id':'one','world_session':'w','phase':'waiting'if self.unknown else'done','bucket_water':{'request_id':'one','world_session':'w','pos':target,'operation':op,'projected_trapdoor_waterlog':not fill,'projected_waterlog_drain':fill,'confirmed':not self.unknown,'unknown_outcome':self.unknown,'use_count':1,'server_block_confirmed':True,'server_inventory_confirmed':True,'server_observed_state':expected}}
class TransferTest(unittest.TestCase):
    def test_single_fill_preserves_structure_and_has_three_frames(self):
        c=Fake()
        with tempfile.TemporaryDirectory()as d:r=waterlog(c,TARGET,'k',c.model,Path(d)/'one');self.assertTrue(r['complete']);self.assertEqual(len(r['observations']),3)
        self.assertEqual(c.uses,1);self.assertEqual(c.states[tuple(TARGET)],WET)
    def test_wrong_floor_drain_is_one_normal_transfer(self):
        c=Fake()
        with tempfile.TemporaryDirectory()as d:r=drain(c,FLOOR,'k',c.model,Path(d)/'one');self.assertTrue(r['complete'])
        self.assertEqual(c.uses,1);self.assertEqual(c.states[tuple(FLOOR)],SLAB)
    def test_old_host_and_existing_source_never_dispatch(self):
        for existing in [False,True]:
            c=Fake();c.protocol=0 if not existing else 1
            if existing:c.states[tuple(TARGET)]=WET
            with tempfile.TemporaryDirectory()as d:
                with self.assertRaises(RuntimeError):waterlog(c,TARGET,'k',c.model,Path(d)/'one')
                b=json.loads((Path(d)/'one/progress.json').read_text());self.assertFalse(b['dispatch_started']);self.assertIsNone(b['pending'])
            self.assertEqual(c.uses,0)
    def test_unknown_identity_is_retained_without_retry(self):
        c=Fake();c.unknown=True
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(RuntimeError):waterlog(c,TARGET,'k',c.model,Path(d)/'one')
            b=json.loads((Path(d)/'one/progress.json').read_text());self.assertEqual(b['pending'],'one_normal_bucket_use');self.assertEqual(b['request_id'],'one')
        self.assertEqual(c.uses,1)
    def test_plain_water_and_wrong_slab_shape_cannot_be_drained(self):
        for state in ['Block{minecraft:water}[level=0]','Block{minecraft:cobblestone_slab}[type=bottom,waterlogged=true]']:
            c=Fake();c.states[tuple(FLOOR)]=state
            with tempfile.TemporaryDirectory()as d:
                with self.assertRaises(RuntimeError):drain(c,FLOOR,'k',c.model,Path(d)/'one')
            self.assertEqual(c.uses,0)
    def test_row_must_be_exact_and_contiguous(self):
        c=Fake();self.assertEqual(row_bounds(c.model,TARGET)['max'],[38,65,20]);c.model['expected'].pop(0)
        with self.assertRaises(RuntimeError):row_bounds(c.model,TARGET)
    def test_new_external_water_is_not_success_and_confirmed_use_is_not_repeated(self):
        c=Fake();c.leak=True
        with tempfile.TemporaryDirectory()as d,patch('projected_trapdoor_waterlog.time.monotonic',side_effect=[0,13]):
            with self.assertRaises(RuntimeError):waterlog(c,TARGET,'k',c.model,Path(d)/'one')
            b=json.loads((Path(d)/'one/progress.json').read_text());self.assertTrue(b['native_confirmed']);self.assertIsNone(b['pending']);self.assertFalse(b['complete'])
        self.assertEqual(c.uses,1)
if __name__=='__main__':unittest.main()
