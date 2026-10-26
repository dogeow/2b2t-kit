import unittest
from roof_cell_repair import options,COBBLESTONE
from roof_slab_window_plan import SLAB
from roof_double_slab_plan import DOUBLE
class RoofCellRepairPlanTest(unittest.TestCase):
 def fixture(self):
  return {(1,72,1):SLAB},{(1,72,1):{'state':DOUBLE,'fluid':False,'block_entity':False}},[0.5,74.1,0.5]
 def choose(self,e,r,p,protected=()):return options(e,r,p,low=[0,70,0],high=[3,82,3],protected=protected)
 def test_only_named_roof_material_mismatches_are_authorized(self):
  e,r,p=self.fixture();self.assertEqual(self.choose(e,r,p)[0]['target'],[1,72,1]);r[(1,72,1)]['state']=COBBLESTONE;self.assertEqual(self.choose(e,r,p)[0]['drop_item'],'minecraft:cobblestone');r[(1,72,1)]['state']='Block{minecraft:stone}';self.assertEqual(self.choose(e,r,p),[])
 def test_valid_upper_pillar_is_preserved(self):
  e,r,p=self.fixture();e[(1,73,1)]='Block{minecraft:cobblestone}';r[(1,73,1)]={'state':e[(1,73,1)]};self.assertEqual(self.choose(e,r,p),[])
 def test_clear_working_body_does_not_hide_an_overhead_approach_block(self):
  e,r,p=self.fixture();r[(1,75,1)]={'state':SLAB};self.assertEqual(self.choose(e,r,p),[])
 def test_reserved_target_and_possible_anchors_stay_reserved(self):
  e,r,p=self.fixture()
  for protected in [[[1,72,1]],[[2,72,1]],[[1,73,1]]]:self.assertEqual(self.choose(e,r,p,protected),[])
 def test_wet_or_container_observations_never_allow_removal(self):
  for field in ['fluid','block_entity']:
   e,r,p=self.fixture();r[(1,72,1)][field]=True;self.assertEqual(self.choose(e,r,p),[])
 def test_matching_double_model_cells_are_not_correction_targets(self):
  e,r,p=self.fixture();e[(1,72,1)]=DOUBLE;self.assertEqual(self.choose(e,r,p),[])

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from roof_cell_repair import run
import math,json

class NativeRoofDouble:
 def __init__(self,*,ack=True,pickup=True,side_effect=False,cube=False):
  self.client=self;self.ack=ack;self.pickup=pickup;self.side_effect=side_effect;self.stock=5;self.full=False;self.cobble=2;self.cube=cube;self.pending_print=False;self.pos=[1.5,74.15,1.5];self.calls=[]
  self.rows={(1,72,1):{'pos':[1,72,1],'state':COBBLESTONE if cube else DOUBLE,'fluid':False,'block_entity':False},(2,72,1):{'pos':[2,72,1],'state':SLAB,'fluid':False,'block_entity':False}}
 def check(self):
  slots=[{'slot':i,'item':'minecraft:dirt'if self.full else 'minecraft:air','count':64 if self.full else 0}for i in range(36)]
  slots[0]={'slot':0,'item':'minecraft:cobblestone_slab'if self.stock else 'minecraft:air','count':self.stock};slots[1]={'slot':1,'item':'minecraft:cobblestone','count':self.cobble}
  return {'world_session':'world','health':20,'pos':self.pos,'inventory':slots,'professional_printer':{'owned':False,'travel_pending':1 if self.pending_print else 0,'waiting_for_server':self.pending_print,'failure':''}}

 def n(self,op,**kw):
  self.calls.append(op)
  if op=='scan':
   lo,hi=kw['min'],kw['max'];return {**deepcopy(self.check()),'world_session':'world','scan_start_revision':1,'scan_end_revision':1,'scan_cells_read':math.prod(b-a+1 for a,b in zip(lo,hi)),'scan_total_cells':math.prod(b-a+1 for a,b in zip(lo,hi)),'blocks':[(deepcopy(row)if kw.get('details')else {'pos':row['pos'],'state':row['state']})for p,row in self.rows.items()if all(a<=n<=b for a,n,b in zip(lo,p,hi))]}
  if op=='navigate':self.pos=kw['target']
  if op=='mine_block':
   self.rows.pop((1,72,1))
   if self.pickup:
    if self.cube:self.cobble+=1
    else:self.stock+=2
   return {'id':'original-mine','server_confirmed':self.ack,'native_sequence':7,'server_ack_sequence':7 if self.ack else -1}
  return {'phase':'done'}
 def print_model(self,*args,**kw):
  self.calls.append('native_print');self.rows[(1,72,1)]={'pos':[1,72,1],'state':SLAB,'fluid':False,'block_entity':False};self.stock-=1
  if self.side_effect:self.rows[(2,72,1)]['state']=DOUBLE
  return {'complete':True}

class RoofCellRepairExecutionTest(unittest.TestCase):
 model={'placement_key':'model','expected':[{'pos':[1,72,1],'state':SLAB},{'pos':[2,72,1],'state':SLAB}]}
 def execute(self,builder,out):return run(builder,self.model,out,low=[0,70,0],high=[3,82,3],protected=[],allowed_at=lambda target,pose:True,limit=1)
 def test_recover_both_drops_before_printing_and_credit_net_one(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble()
   with patch('roof_cell_repair.build_phase',side_effect=b.print_model):r=self.execute(b,Path(directory)/'proof')
   self.assertEqual(r['verified_repairs'],1);self.assertEqual(b.stock,6);self.assertEqual(b.calls.count('mine_block'),1);self.assertEqual(b.calls.count('native_print'),1);self.assertEqual(r['cells'][0]['mining_ack']['native_sequence'],7)
 def test_wrong_cube_recovers_one_cobble_and_consumes_one_slab(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble(cube=True)
   with patch('roof_cell_repair.build_phase',side_effect=b.print_model):r=self.execute(b,Path(directory)/'proof')
   self.assertEqual(r['verified_repairs'],1);self.assertEqual(b.cobble,3);self.assertEqual(b.stock,4);self.assertEqual(r['cells'][0]['drop_item'],'minecraft:cobblestone');self.assertEqual(r['cells'][0]['verified_recovered'],1)
 def test_cube_is_not_mined_without_the_replacement_slab(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble(cube=True);b.stock=0
   with patch('roof_cell_repair.build_phase')as printer:r=self.execute(b,Path(directory)/'proof');printer.assert_not_called()
   self.assertEqual(r['verified_repairs'],0);self.assertNotIn('mine_block',b.calls)
 def test_insufficient_room_for_both_slab_drops_blocks_mining(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble();b.stock=63;b.full=True
   with patch('roof_cell_repair.build_phase')as printer:r=self.execute(b,Path(directory)/'proof');printer.assert_not_called()
   self.assertEqual(r['verified_repairs'],0);self.assertNotIn('mine_block',b.calls)
 def test_unacknowledged_original_mine_never_retries_or_prints(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble(ack=False);out=Path(directory)/'proof'
   with patch('roof_cell_repair.build_phase')as printer:
    with self.assertRaisesRegex(RuntimeError,'never remine'):self.execute(b,out)
    printer.assert_not_called()
   self.assertEqual(b.calls.count('mine_block'),1);self.assertFalse(json.loads((out/'progress.json').read_text())['complete'])
 def test_uncollected_drops_keep_hole_instead_of_sealing_away_material(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble(pickup=False)
   with patch('roof_cell_repair.build_phase')as printer,patch('roof_cell_repair.time.monotonic',side_effect=[0,10]):
    with self.assertRaisesRegex(RuntimeError,'not all collected'):self.execute(b,Path(directory)/'proof')
    printer.assert_not_called()
   self.assertEqual(b.calls.count('mine_block'),1)
 def test_adjacent_change_is_detected_after_the_single_attempt(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble(side_effect=True)
   with patch('roof_cell_repair.build_phase',side_effect=b.print_model):
    with self.assertRaisesRegex(RuntimeError,'surrounding'):self.execute(b,Path(directory)/'proof')
   self.assertEqual(b.calls.count('native_print'),1)

 def test_observed_target_alone_does_not_clear_a_pending_printer_input(self):
  with TemporaryDirectory()as directory:
   b=NativeRoofDouble()
   def pending(*args,**kw):
    result=b.print_model(*args,**kw);b.pending_print=True;return result
   with patch('roof_cell_repair.build_phase',side_effect=pending):
    with self.assertRaisesRegex(RuntimeError,'unsettled input'):self.execute(b,Path(directory)/'proof')
   self.assertEqual(b.calls.count('native_print'),1)

if __name__=='__main__':unittest.main()
