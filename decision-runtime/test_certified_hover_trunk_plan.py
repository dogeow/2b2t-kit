import copy,unittest
from certified_hover_trunk_plan import plan
class CertifiedHoverTrunkPlanTest(unittest.TestCase):
 def fixture(self):
  rows=[{'pos':[0,62,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False,'block_entity':False}]
  rows += [{'pos':[0,y,0],'state':'Block{minecraft:oak_log}[axis=y]','fluid':False,'block_entity':False}for y in range(63,71)]
  rows += [{'pos':[0,y,0],'state':'Block{minecraft:oak_leaves}[persistent=false,distance=1,waterlogged=false]','fluid':False,'block_entity':False}for y in [71,72]]
  rows += [{'pos':[x,71,z],'state':'Block{minecraft:oak_leaves}[persistent=false,distance=2,waterlogged=false]'}for x,z in [(1,0),(-1,0),(0,1),(0,-1)]]
  scene={'phase':'done','world_session':'w','scan_cells_read':3*17*3,'scan_total_cells':3*17*3,'scan_start_revision':5,'scan_end_revision':5,'blocks':rows};return scene
 def call(self,s):return plan([0,63,0],s,[-1,62,-1],[1,78,1],world='w')
 def test_ceiling_is_removed_before_descending_and_no_grounded_chop_is_planned(self):
  p=self.call(self.fixture());self.assertEqual(8,p['expected_logs']);self.assertEqual([72,71,70,69,68,67,66,65,64,63],[s['pos'][1]for s in p['steps']]);self.assertFalse(p['grounded_walk_or_chop_allowed']);self.assertTrue(p['pickup_requires_fresh_ground_threat_scan']);self.assertTrue(p['steps'][-1]['ground_threat_scan_required'])
 def test_incomplete_or_unsafe_tree_is_rejected(self):
  for mode in ['partial','world','branch','hive','persistent','unknown_core','floating_log','missing_details','wet_leaf','hover_unknown']:
   s=copy.deepcopy(self.fixture())
   if mode=='partial':s['scan_cells_read']-=1
   elif mode=='world':s['world_session']='old'
   elif mode=='branch':s['blocks'].append({'pos':[1,68,0],'state':'Block{minecraft:oak_log}[axis=x]'})
   elif mode=='hive':s['blocks'].append({'pos':[1,69,0],'state':'Block{minecraft:bee_nest}','block_entity':True})
   elif mode=='persistent':s['blocks'][9]['state']='Block{minecraft:oak_leaves}[persistent=true]'
   elif mode=='unknown_core':s['blocks'].append({'pos':[0,74,0],'state':'Block{minecraft:stone}'})
   elif mode=='floating_log':s['blocks'].append({'pos':[0,74,0],'state':'Block{minecraft:oak_log}[axis=y]','fluid':False,'block_entity':False})
   elif mode=='missing_details':s['blocks'][2].pop('fluid')
   elif mode=='wet_leaf':s['blocks'][9]['state']='Block{minecraft:oak_leaves}[persistent=false,waterlogged=true]'
   else:s['blocks'].append({'pos':[0,76,0],'state':'Block{minecraft:oak_leaves}[persistent=false]','fluid':False,'block_entity':False})
   with self.subTest(mode=mode),self.assertRaises(ValueError):self.call(s)
if __name__=='__main__':unittest.main()
