import unittest
from copy import deepcopy
from mega_spruce_harvest import trunk_certificate
class TrunkCertificateTest(unittest.TestCase):
 def rows(self):return [{'pos':[x,y,z],'state':'Block{minecraft:spruce_log}[axis=y]'}for x in [10,11]for z in [20,21]for y in range(64,80)]
 def test_all_four_continuous_columns_are_required(self):self.assertEqual(len(trunk_certificate([10,64,20],self.rows())),64)
 def test_neighbors_floating_columns_or_duplicates_cannot_enter_harvest(self):
  for mode in ['neighbor','gap','species','duplicate','floor']:
   with self.subTest(mode=mode):
    rows=deepcopy(self.rows())
    if mode=='neighbor':rows[0]['pos'][0]=12
    if mode=='gap':rows.pop(5)
    if mode=='species':rows[0]['state']='Block{minecraft:oak_log}[axis=y]'
    if mode=='duplicate':rows.append(deepcopy(rows[0]))
    if mode=='floor':rows[0]['pos'][1]=63
    with self.assertRaises(ValueError):trunk_certificate([10,64,20],rows)

class HarvestWorldTest(unittest.TestCase):
 def test_uneven_crown_is_cleared_without_touching_neighbors_or_soil(self):
  import math,tempfile
  from pathlib import Path
  from mega_spruce_harvest import harvest
  root=[10,64,20];logs=[{'pos':[x,64,z],'state':'Block{minecraft:spruce_log}[axis=y]'}for x in [10,11]for z in [20,21]]+[{'pos':[10,65,20],'state':'Block{minecraft:spruce_log}[axis=y]'}]
  class Builder:
   def __init__(self):
    self.pos=[14.4,64,17.6];self.gain=0;self.mined=[]
    self.rows={tuple(r['pos']):{**r,'fluid':False,'block_entity':False} for r in logs}
    for x in [10,11]:
     for z in [20,21]:
      self.rows[x,63,z]={'state':'Block{minecraft:podzol}','solid':True}
      for y in [65,66]:self.rows.setdefault((x,y,z),{'state':'Block{minecraft:spruce_leaves}[distance=1,persistent=false,waterlogged=false]'})
    self.rows[12,64,21]={'state':'Block{minecraft:oak_log}[axis=y]'}
   def check(self):return {'pos':self.pos,'world_session':'w','health':20,'inventory':[{'slot':0,'item':'minecraft:diamond_axe','count':1,'durability':100},{'slot':1,'item':'minecraft:spruce_log','count':7+self.gain}]+[{'slot':slot,'item':'minecraft:air','count':0}for slot in range(2,36)]}
   def scan(self,low,high):return {},{p:r for p,r in self.rows.items()if all(low[i]<=p[i]<=high[i]for i in range(3))}
   def nav(self,p):
    low=[p[0]-.3,p[1],p[2]-.3];high=[p[0]+.3,p[1]+1.8,p[2]+.3]
    for cell in self.rows:
     assert not all(high[i]>cell[i]and low[i]<cell[i]+1 for i in range(3)),('Body blocked',p,cell)
    self.pos=p
   def n(self,op,**params):
    if op=='select_item':return {'phase':'done'}
    assert op=='mine_block';p=tuple(params['pos']);r=self.rows.pop(p);assert r['state']==params['expected_state'];self.mined.append(p)
    if 'spruce_log'in r['state']:self.gain+=1
    return {'id':str(len(self.mined)),'server_confirmed':True,'native_sequence':len(self.mined),'server_ack_sequence':len(self.mined)}
  b=Builder()
  with tempfile.TemporaryDirectory()as tmp:result=harvest(b,root,logs,Path(tmp)/'proof.json')
  self.assertTrue(result['complete']);self.assertEqual(result['log_gain'],5);self.assertIn((12,64,21),b.rows)
  self.assertEqual(sum(p[1]==63 for p in b.rows),4)

if __name__=='__main__':unittest.main()
