import copy,unittest
from potion_storage_click import signature
class PotionTests(unittest.TestCase):
 def test_only_fresh_exact_potion(self):
  rows=[{'slot':i,'item':'minecraft:air','count':0}for i in range(63)];rows[23]={'slot':23,'item':'minecraft:potion','count':1}
  s={'time':1000,'connected':True,'world_session':'w','player_uuid':'p','runtime_generation':1,'health':20,'manual_movement':False,'control_revision':2,'screen':'ContainerScreen','supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':2},'menu':{'type':'ChestMenu','id':7,'cursor':{'item':'minecraft:air','count':0},'slots':rows}}
  e={'world_session':'w','player_uuid':'p','runtime_generation':1,'potion_inventory':{'complete':True,'menu_id':7,'menu_type':'ChestMenu','observed_at':999,'potions':[{'slot':23,'nonempty_child_index':-1,'item':'minecraft:potion','potion_contents':{'potion':'minecraft:healing'}}]}}
  p={'menu_id':7,'slot':23,'kind':'quick_move','expected_item':'minecraft:potion','expected_count':1,'expected_cursor':'minecraft:air','expected_cursor_count':0};self.assertIsNotNone(signature(s,e,p,'w','t','minecraft:healing'))
  for change in ('stale','type','world','menu','full','cursor','manual'):
   a,b=copy.deepcopy((s,e))
   if change=='stale':b['potion_inventory']['observed_at']=0
   if change=='type':b['potion_inventory']['potions'][0]['potion_contents']={'potion':'minecraft:water'}
   if change=='world':b['world_session']='other'
   if change=='menu':b['potion_inventory']['menu_id']=8
   if change=='full':
    for row in a['menu']['slots'][-36:]:row.update(item='minecraft:stone',count=64)
   if change=='cursor':a['menu']['cursor']['count']=1
   if change=='manual':a['manual_movement']=True
   with self.subTest(change=change):self.assertIsNone(signature(a,b,p,'w','t','minecraft:healing'))
if __name__=='__main__':unittest.main()
