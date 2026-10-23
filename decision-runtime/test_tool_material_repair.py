import unittest
from copy import deepcopy
from tool_material_repair import validate_preview,outcome


def axe(d):return dict(item='minecraft:diamond_axe',count=1,durability=d,max_durability=1561)
class ToolRepairTest(unittest.TestCase):
 def fixture(self):
  left=axe(310);right=dict(item='minecraft:diamond',count=2)
  state={'experience_level':31,'menu':{'type':'AnvilMenu','cursor':{'count':0},'anvil_cost':2,'anvil_too_expensive':False,'anvil_result_may_pickup':True,'slots':[left,right,axe(1090)]}}
  return state,left,right
 def test_exact_native_preview(self):
  s,l,r=self.fixture();v,c=validate_preview(s,l,r);self.assertEqual((v['durability'],c),(1090,2))
 def test_wrong_material_tool_cost_enchantment_or_partial_preview_rejected(self):
  for mode in ['material','tool','cost','xp','preview','curse','cursor','pickup']:
   s,l,r=self.fixture();l=deepcopy(l);r=deepcopy(r)
   if mode=='material':s['menu']['slots'][1]['count']=1
   if mode=='tool':s['menu']['slots'][0]['durability']=309
   if mode=='cost':s['menu']['anvil_cost']=5
   if mode=='xp':s['experience_level']=1
   if mode=='preview':s['menu']['slots'][2]['durability']=1089
   if mode=='curse':s['menu']['slots'][2]['enchantments']=[{'id':'minecraft:vanishing_curse','level':1}]
   if mode=='cursor':s['menu']['cursor']['count']=1
   if mode=='pickup':s['menu']['anvil_result_may_pickup']=False
   with self.subTest(mode=mode),self.assertRaises(ValueError):validate_preview(s,l,r)
 def test_exact_outcome_includes_anvil_break_window_close(self):
  for kind in ['AnvilMenu','InventoryMenu']:
   empty={'item':'minecraft:air','count':0};tool=axe(1090)
   s={'experience_level':29,'inventory':[{**tool,'slot':2}], 'menu':{'type':kind,'cursor':{'count':0},'slots':[empty,empty,empty,tool]}}
   self.assertTrue(outcome(s,{'minecraft:diamond_axe':1,'minecraft:diamond':2},tool,31,2))
   for mode in ['diamond','xp','tool','cursor','input']:
    bad=deepcopy(s)
    if mode=='diamond':bad['inventory'].append({'slot':5,'item':'minecraft:diamond','count':1})
    if mode=='xp':bad['experience_level']=30
    if mode=='tool':bad['menu']['slots'][3]=axe(310)
    if mode=='cursor':bad['menu']['cursor']['count']=1
    if mode=='input':bad['menu']['type']='AnvilMenu';bad['menu']['slots'][0]=axe(310)
    with self.subTest(kind=kind,mode=mode):self.assertFalse(outcome(bad,{'minecraft:diamond_axe':1,'minecraft:diamond':2},tool,31,2))
if __name__=='__main__':unittest.main()
