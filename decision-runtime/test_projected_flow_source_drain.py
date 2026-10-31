import copy,unittest
from projected_flow_source_drain import confirmed,removed,AIR,SOURCE
class FlowDrainReceiptTests(unittest.TestCase):
 def test_regenerated_source_is_not_a_corrected_channel(self):
  self.assertFalse(removed(SOURCE));self.assertTrue(removed(AIR));self.assertTrue(removed('Block{minecraft:water}[level=3]'));self.assertFalse(removed('Block{minecraft:bubble_column}[drag=true]'));self.assertFalse(removed('Block{minecraft:lava}[level=0]'))
 def test_exact_identity_mode_and_both_server_acknowledgements(self):
  r={'id':'one','world_session':'world','phase':'done','bucket_water':{'request_id':'one','world_session':'world','pos':[1,2,3],'operation':'bucket_fill','projected_flow_source_drain':True,'use_count':1,'confirmed':True,'unknown_outcome':False,'server_block_confirmed':True,'server_inventory_confirmed':True}}
  self.assertTrue(confirmed(r,'one','world',[1,2,3]))
  for section,key,value in [('top','id','other'),('top','world_session','old'),('top','phase','waiting'),('bucket','request_id','other'),('bucket','world_session','old'),('bucket','pos',[1,2,4]),('bucket','operation','bucket_place'),('bucket','projected_flow_source_drain',False),('bucket','use_count',0),('bucket','use_count',2),('bucket','use_count',True),('bucket','confirmed',False),('bucket','unknown_outcome',True),('bucket','server_block_confirmed',False),('bucket','server_inventory_confirmed',False)]:
   wrong=copy.deepcopy(r);(wrong if section=='top'else wrong['bucket_water'])[key]=value
   with self.subTest(key=key,value=value):self.assertFalse(confirmed(wrong,'one','world',[1,2,3]))
