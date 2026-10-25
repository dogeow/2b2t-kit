import unittest
from mega_spruce_supply import growth_kind,roots,require_growth_pose,require_ground

class GrowthAdmissionTest(unittest.TestCase):
 def test_mixed_roots_never_allow_another_use(self):
  r=[10,64,20];q={tuple(p):{'state':'Block{minecraft:spruce_sapling}[stage=0]'}for p in roots(r)}
  self.assertEqual(growth_kind(q,r),'saplings');q[tuple(r)]={'state':'Block{minecraft:spruce_log}[axis=y]'}
  with self.assertRaises(RuntimeError):growth_kind(q,r)
  for p in roots(r):q[tuple(p)]={'state':'Block{minecraft:spruce_log}[axis=y]'}
  self.assertEqual(growth_kind(q,r),'grown')
 def test_point_clearance_does_not_allow_body_overlapping_leaves(self):
  r=[10,64,20];pose=[14.4,64,17.6];s={'health':20,'manual_movement':False,'screen':'','on_ground':True,'flight':False,'pos':pose}
  require_growth_pose(s,r,pose)
  for key,value in [('guard_busy',True),('safety_hold',{'active':True}),('flight',True),('on_ground',False),('health',19),('manual_movement',True),('screen','InventoryScreen'),('pos',[14.1,64,17.6])]:
   with self.subTest(key=key),self.assertRaises(RuntimeError):require_growth_pose({**s,key:value},r,pose)
 def test_small_settled_drift_is_accepted_only_with_safe_body_and_reach(self):
  r=[760963,64,797812];pose=[760967.4,64,797809.6];state={'health':20,'manual_movement':False,'screen':'','on_ground':True,'flight':False,'pos':[760967.5744468125,64,797809.4995425831]};require_growth_pose(state,r,pose)
  require_growth_pose({**state,'pos':[760967.700240641,64,797809.4179833443]},r,pose)
  with self.assertRaises(RuntimeError):require_growth_pose({**state,'pos':[760967.12,64,797809.6]},r,pose)
  with self.assertRaises(RuntimeError):require_growth_pose({**state,'pos':[760967.84,64,797809.3]},r,pose)
 def test_clear_floor_is_not_enough_if_body_is_obstructed(self):
  pose=[14.4,64,17.6];rows={(14,63,17):{'solid':True,'fluid':False,'block_entity':False}}
  require_ground(rows,pose);rows[(14,65,17)]={'state':'Block{minecraft:oak_leaves}'}
  with self.assertRaises(RuntimeError):require_ground(rows,pose)

class UnknownUseTest(unittest.TestCase):
 def test_missing_fertilizer_debit_retains_pending_effect_and_never_replays(self):
  from tempfile import TemporaryDirectory
  from pathlib import Path
  from unittest.mock import patch
  import json
  from mega_spruce_supply import grow
  clock=[0.0]
  class Builder:
   def __init__(self):
    self.pos=[12.5,64,19.5];self.seeds=8;self.bone=12;self.uses=0;self.tick=0
    self.rows={tuple([x,63,z]):{'state':'Block{minecraft:grass_block}[snowy=false]','solid':True} for x,z in [(10,20),(10,21),(11,20),(11,21),(12,19),(12,18),(14,17)]}
   def check(self):
    self.tick+=1
    return {'world_session':'w','health':20,'manual_movement':False,'screen':'','on_ground':True,'flight':False,'pos':self.pos,'time':self.tick,'inventory':[{'slot':0,'item':'minecraft:spruce_sapling','count':self.seeds},{'slot':1,'item':'minecraft:bone_meal','count':self.bone}]}
   def scan(self,low,high):return {},{p:r for p,r in self.rows.items()if all(low[i]<=p[i]<=high[i]for i in range(3))}
   def n(self,op,**params):
    if op=='walk':
     self.pos=list(params['target'])
     if self.pos==[12.5,64,19.5]:self.pos[2]-=.26
    if op=='interact':self.uses+=1
    return {'id':'one-original-use','phase':'done'}
   def place(self,p,*args,**kwargs):
    self.seeds-=1;self.rows[tuple(p)]={'state':'Block{minecraft:spruce_sapling}[stage=0]'}
  b=Builder()
  with TemporaryDirectory() as tmp,patch('mega_spruce_supply.time.monotonic',side_effect=lambda:clock[0]),patch('mega_spruce_supply.time.sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
   p=Path(tmp)/'growth.json'
   with self.assertRaisesRegex(RuntimeError,'never retry'):
    grow(b,[10,64,20],[12.5,64,19.5],1,p)
   self.assertEqual(b.uses,1);self.assertEqual(b.bone,12)
   record=json.loads(p.read_text());self.assertEqual(record['pending_effect']['kind'],'fertilize');self.assertFalse(record['complete']);self.assertAlmostEqual(record['actual_planting_pose'][2],19.24)
   with self.assertRaisesRegex(RuntimeError,'Original growth journal'):
    grow(b,[10,64,20],[12.5,64,19.5],1,p)
   self.assertEqual(b.uses,1)


class GroundSettlementTest(unittest.TestCase):
 def test_lagging_ground_flag_is_observed_without_another_walk(self):
  from mega_spruce_supply import settle_growth_pose
  from unittest.mock import patch
  r=[10,64,20];pose=[14.4,64,17.6];clock=[0.0];calls=[0]
  class Reader:
   def check(self):
    calls[0]+=1
    return {'pos':pose,'health':20,'manual_movement':False,'screen':'','guard_busy':False,'flight':False,'on_ground':calls[0]>1,'time':calls[0]}
   def scan(self,low,high):return {},{(14,63,17):{'solid':True}}
  with patch('mega_spruce_supply.time.monotonic',side_effect=lambda:clock[0]),patch('mega_spruce_supply.time.sleep',side_effect=lambda dt:clock.__setitem__(0,clock[0]+dt)):
   out=settle_growth_pose(Reader(),r,pose)
  self.assertTrue(out['on_ground']);self.assertEqual(calls[0],4)
 def test_offset_pose_rechecks_every_actual_floor_column(self):
  from mega_spruce_supply import settle_growth_pose
  class Reader:
   tick=0
   def check(self):
    self.tick+=1
    return {'pos':[760967.700240641,64,797809.4179833443],'health':20,'manual_movement':False,'screen':'','guard_busy':False,'flight':False,'on_ground':True,'time':self.tick}
   def scan(self,low,high):return {},{(760967,63,797809):{'solid':True}}
  with self.assertRaisesRegex(RuntimeError,'dry floor'):settle_growth_pose(Reader(),[760963,64,797812],[760967.4,64,797809.6])
 def test_active_defense_never_waits_into_a_fertilizer_use(self):
  from mega_spruce_supply import settle_growth_pose
  class Reader:
   def check(self):return {'pos':[14.4,64,17.6],'health':20,'guard_busy':True}
  with self.assertRaisesRegex(RuntimeError,'protection active'):settle_growth_pose(Reader(),[10,64,20],[14.4,64,17.6])


class SoilStateTest(unittest.TestCase):
 def test_podzol_properties_do_not_hide_the_confirmed_soil(self):
  from mega_spruce_supply import natural_soil
  for state in ['Block{minecraft:podzol}[snowy=false]','Block{minecraft:grass_block}[snowy=false]','Block{minecraft:dirt}']:
   self.assertTrue(natural_soil({'state':state,'solid':True,'fluid':False,'block_entity':False}))
  for extra in [{'state':'Block{minecraft:farmland}[moisture=7]'}, {'fluid':True},{'block_entity':True},{'solid':False}]:
   self.assertFalse(natural_soil({'state':'Block{minecraft:podzol}[snowy=false]','solid':True,**extra}))

if __name__=='__main__':unittest.main()
