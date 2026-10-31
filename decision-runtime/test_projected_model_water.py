import unittest,copy
from projected_model_water import layout,receipt,SOURCE
class ModelWaterTests(unittest.TestCase):
 def model(self):return {'expected':[{'pos':[10,68,20-i],'state':f'Block{{minecraft:water}}[level={i}]'}for i in range(5)]}
 def test_bounds_include_source_regeneration_halo(self):
  b,c=layout(self.model(),[10,68,20]);self.assertEqual({'min':[8,67,14],'max':[12,69,22]},b);self.assertEqual(5,len(c))
 def test_bent_path_is_retained(self):
  m={'expected':[{'pos':[10,68,20],'state':SOURCE},{'pos':[9,68,20],'state':'Block{minecraft:water}[level=1]'}, {'pos':[9,68,19],'state':'Block{minecraft:water}[level=2]'}]};self.assertEqual(3,len(layout(m,[10,68,20])[1]))
 def test_non_source_or_falling_layout_is_rejected(self):
  with self.assertRaises(ValueError):layout(self.model(),[10,68,19])
  m=self.model();m['expected'][1]['state']='Block{minecraft:water}[level=8]'
  with self.assertRaises(ValueError):layout(m,[10,68,20])
 def valid(self):return {'id':'r','world_session':'w','phase':'done','bucket_water':{'request_id':'r','world_session':'w','pos':[10,68,20],'operation':'bucket_place','projected_model_water_source':True,'use_count':1,'confirmed':True,'unknown_outcome':False,'server_block_confirmed':True,'server_inventory_confirmed':True,'server_observed_state':SOURCE}}
 def test_receipt_requires_single_use_both_real_receipts_and_exact_scope(self):
  self.assertTrue(receipt(self.valid(),'r','w',[10,68,20]))
  for key,value in [('request_id','other'),('world_session','other'),('pos',[10,68,19]),('operation','bucket_fill'),('projected_model_water_source',False),('use_count',0),('use_count',2),('use_count',True),('confirmed',False),('unknown_outcome',True),('server_block_confirmed',False),('server_inventory_confirmed',False),('server_observed_state','Block{minecraft:water}[level=1]')]:
   r=self.valid();r['bucket_water'][key]=value;self.assertFalse(receipt(r,'r','w',[10,68,20]),key)
if __name__=='__main__':unittest.main()
