import copy,unittest
from brewing_slot_click import signature
class BrewingClickTests(unittest.TestCase):
 def test_scoped_click(self):
  rows=[{'slot':i,'item':'minecraft:air','count':0}for i in range(41)];rows[10]={'slot':10,'item':'minecraft:potion','count':1}
  s={'connected':True,'world_session':'w','health':20,'manual_movement':False,'control_revision':2,'screen':'BrewingStandScreen','supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':2},'menu':{'type':'BrewingStandMenu','id':7,'cursor':{'item':'minecraft:air','count':0},'slots':rows}}
  p={'menu_id':7,'slot':10,'kind':'pickup','button':0,'expected_item':'minecraft:potion','expected_count':1,'expected_cursor':'minecraft:air','expected_cursor_count':0};self.assertIsNotNone(signature(s,p,'w','t'))
  for change in ('world','held','count','kind','lease','health','destination','cursor'):
   a,b=copy.deepcopy((s,p))
   if change=='world':a['world_session']='x'
   if change=='held':a['manual_movement']=True
   if change=='count':a['menu']['slots'][10]['count']=2
   if change=='kind':b['kind']='quick_move'
   if change=='lease':a['supervision_lease']['revision']=3
   if change=='health':a['health']=19
   if change=='destination':b.update(slot=3,expected_item='minecraft:air',expected_count=0,expected_cursor='minecraft:potion',expected_cursor_count=1);a['menu']['cursor']={'item':'minecraft:potion','count':1}
   if change=='cursor':a['menu']['cursor']['count']=1
   with self.subTest(change=change):self.assertIsNone(signature(a,b,'w','t'))
  for ingredient in ('minecraft:nether_wart', 'minecraft:glistering_melon_slice'):
   a = copy.deepcopy(s)
   a['menu']['cursor'] = {'item': ingredient, 'count': 1}
   b = dict(p, slot=3, expected_item='minecraft:air', expected_count=0,
            expected_cursor=ingredient, expected_cursor_count=1)
   with self.subTest(ingredient=ingredient):
    self.assertIsNotNone(signature(a,b,'w','t'))
    self.assertIsNone(signature(a,dict(b,slot=0),'w','t'))
    self.assertIsNone(signature(a,dict(b,slot=4),'w','t'))
if __name__=='__main__':unittest.main()
