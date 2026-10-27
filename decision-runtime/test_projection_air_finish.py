import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import projection_air_finish as m

ITEM='minecraft:green_terracotta';POS=[10,64,20]
ROW={'pos':POS,'expected':'Block{'+ITEM+'}','actual':'Block{minecraft:air}',
     'kind':'missing','fluid':False,'block_entity':False}

class Fake:
    world='world';task='task';last=None
    def __init__(self):self.count=5;self.placed=False;self.calls=[];self.clock=0;self.fault=None;self.pos=[10.5,66.2,20.5]
    def status(self):
        self.clock+=1
        return {'time':self.clock,'world_session':self.world,'connected':True,'health':20,'food':20,
                'manual_movement':False,'guard_armed':True,'guard_pve_only':True,'guard_busy':False,'under_water':False,
                'projection_air_seed_axis_protocol':1,'projection_selection':{'key':'map','min':[0,64,0],'max':[127,64,128]},
                'pos':self.pos,'build_job':{'active':False},'professional_printer':{'owned':False},
                'inventory':[{'slot':0,'item':ITEM,'count':self.count}], 'hand':{'item':ITEM,'count':self.count}}
    def checked(self,op,**kw):self.calls.append(op)
    def request(self,op,**kw):
        self.calls.append(op);self.last='materials-once';before=self.count;self.count-=1;self.placed=True
        ack={'request_id':self.last,'world_session':self.world,'placement_key':'map','target':POS,'item':ITEM,
             'server_confirmed':True,'use_count':1,'projection_matches':True,'requires_stripping':False,
             'expected_state':ROW['expected'],'projected_state':ROW['expected'],'inventory_before':before,'inventory_after':before-1,
             'module_settings_changed':False,'automatic_retry_allowed':False,'confirmation_scope':'matched_server_block_update_after_native_send'}
        if self.fault=='ack':ack['server_confirmed']=False
        if self.fault=='world':ack['world_session']='other'
        return {'id':self.last,'world_session':self.world,'phase':'waiting'if self.fault=='unknown'else'done','projection_air_seed':ack}
    def scan(self,*args):return [{'pos':POS,'state':ROW['expected']}]if self.placed else[]

class AirFinishTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.out=Path(tmp.name)/'cell';self.c=Fake()
        for name,fn in [('_scan',self.c.scan),('move',lambda *a,**kw:None),('settled_state',lambda *a,**kw:None)]:
            p=patch.object(m,name,side_effect=fn);p.start();self.addCleanup(p.stop)
        p=patch.object(m.time,'sleep');p.start();self.addCleanup(p.stop)
    def run_cell(self):return m.run_one(self.c,ROW,self.out,self.c.status)
    def test_normal_meteor_air_interaction_finishes_island_without_support_or_module_changes(self):
        r=self.run_cell();self.assertTrue(r['complete']);self.assertEqual(4,self.c.count)
        self.assertEqual(2,len(r['physical_observations']));self.assertEqual(1,self.c.calls.count('projection_air_seed'))
        self.assertEqual(['select_item','projection_air_seed'],self.c.calls)
    def test_unknown_or_foreign_ack_is_retained_without_replaying(self):
        for fault in('unknown','ack','world'):
            with self.subTest(fault=fault):
                self.setUp();self.c.fault=fault
                with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.run_cell()
                self.assertEqual('projection_air_seed',json.loads((self.out/'progress.json').read_text())['pending'])
                with self.assertRaises(FileExistsError):self.run_cell()
                self.assertEqual(1,self.c.calls.count('projection_air_seed'))
    def test_candidates_respect_stock_flat_projection_and_protected_cells(self):
        a={'placement_key':'map','mismatches':[ROW,copy.deepcopy(ROW)]};s=self.c.status()
        self.assertEqual([ROW],m.candidates(a,s,8));self.assertEqual([],m.candidates(a,s,0))
        for change in({'fluid':True},{'block_entity':True},{'actual':'Block{minecraft:stone}'},{'pos':[True,64,20]},
                       {'pos':[10,65,20]},{'expected':'Block{minecraft:sand}'}):
            self.assertEqual([],m.candidates({**a,'mismatches':[{**ROW,**change}]},s,8))
        s['projection_selection']['max'][1]=65;self.assertEqual([],m.candidates(a,s,8))
    def test_active_printer_never_overlaps_single_use_air_placement(self):
        state=self.c.status;self.c.status=lambda:{**state(),'build_job':{'active':True}}
        with self.assertRaisesRegex(RuntimeError,'still owns'):self.run_cell()
        self.assertEqual([],self.c.calls)

    def volume_state(self):
        original=self.c.status
        self.c.status=lambda:{**original(),'projection_selection':{'key':'map','min':[0,63,0],'max':[127,66,128]}}
    def test_volume_requires_explicit_opt_in_and_keeps_exact_bounds(self):
        self.volume_state();a={'placement_key':'map','mismatches':[ROW]};state=self.c.status()
        self.assertEqual([],m.candidates(a,state,8));self.assertEqual([ROW],m.candidates(a,state,8,allow_volume=True))
        for change in ({'fluid':True},{'block_entity':True},{'actual':'Block{minecraft:stone}'},{'pos':[10,67,20]},{'expected':'Block{minecraft:sand}'}):
            self.assertEqual([],m.candidates({**a,'mismatches':[{**ROW,**change}]},state,8,allow_volume=True))
        with self.assertRaises(ValueError):m.candidates(a,state,8,allow_volume='yes')
    def test_volume_uses_the_same_single_native_ack_and_two_stock_frames(self):
        self.volume_state();r=m.run_one(self.c,ROW,self.out,self.c.status,allow_volume=True)
        self.assertTrue(r['complete']);self.assertEqual(4,self.c.count);self.assertEqual(2,len(r['physical_observations']));self.assertEqual(1,self.c.calls.count('projection_air_seed'))
    def test_volume_glass_is_explicit_and_does_not_expand_flat_map_materials(self):
        self.volume_state();state=self.c.status();state['inventory']=[{'slot':0,'item':'minecraft:glass','count':1}];row={**ROW,'expected':'Block{minecraft:glass}'};audit={'placement_key':'map','mismatches':[row]}
        self.assertEqual([row],m.candidates(audit,state,1,allow_volume=True));state['projection_selection']['min'][1]=64;state['projection_selection']['max'][1]=64
        self.assertEqual([],m.candidates(audit,state,1));self.assertEqual([row],m.candidates(audit,state,1,allow_volume=True))
    def test_volume_unknown_outcome_still_has_no_replay(self):
        self.volume_state();self.c.fault='unknown'
        with self.assertRaisesRegex(RuntimeError,'unconfirmed'):m.run_one(self.c,ROW,self.out,self.c.status,allow_volume=True)
        self.assertEqual(1,self.c.calls.count('projection_air_seed'));self.assertEqual('projection_air_seed',json.loads((self.out/'progress.json').read_text())['pending'])

if __name__=='__main__':unittest.main()
