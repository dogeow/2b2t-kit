import unittest,copy,tempfile,json
from pathlib import Path
from projected_model_water import layout,receipt,SOURCE,floor_mismatches,place
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
 def test_floor_mismatch_identifies_the_real_block_before_input(self):
  m=self.model();m['expected'].append({'pos':[10,67,20],'state':'Block{minecraft:magma_block}'})
  self.assertEqual([{'pos':[10,67,20],'expected':'Block{minecraft:magma_block}','actual':'Block{minecraft:dirt}'}],floor_mismatches(m,{(10,68,20):SOURCE},{(10,67,20):'Block{minecraft:dirt}'}))
  self.assertEqual([],floor_mismatches(m,{(10,68,20):SOURCE},{(10,67,20):'Block{minecraft:magma_block}'}))
 def test_native_dynamic_floor_bits_do_not_hide_changed_orientation(self):
  p=(10,67,20);a='Block{minecraft:hopper}[enabled=true,facing=down]';m={'expected':[{'pos':list(p),'state':a}]};cells={(10,68,20):SOURCE}
  self.assertEqual([],floor_mismatches(m,cells,{p:a.replace('true','false')}))
  self.assertTrue(floor_mismatches(m,cells,{p:a.replace('down','west')}))
 def test_existing_water_source_floor_keeps_native_phase_handling(self):
  p=(10,67,20);m={'expected':[{'pos':list(p),'state':'Block{minecraft:water}[level=1]'}]};cells={(10,68,20):SOURCE}
  self.assertEqual([],floor_mismatches(m,cells,{p:SOURCE}))
  self.assertTrue(floor_mismatches(m,cells,{p:'Block{minecraft:lava}[level=0]'}))
 def test_bad_floor_stops_before_tool_selection_or_bucket_dispatch(self):
  m={'placement_key':'k','expected':[{'pos':[10,68,20],'state':SOURCE},
       {'pos':[10,67,20],'state':'Block{minecraft:magma_block}'},
       {'pos':[11,68,20],'state':'Block{minecraft:cobblestone}'}]}
  class Client:
   world='w';task='t'
   def __init__(self):self.calls=[]
   def status(self):return {'projected_model_water_source_protocol':1,'health':20,'food':20,'air_supply':300,
      'guard_armed':True,'guard_pve_only':True,'supervision_lease':{'job_session':'t'},'projection_selection':{'key':'k'}}
   def checked(self,op,**kw):
    self.calls.append(op)
    if op!='scan':raise AssertionError('No mutable operation before valid floor')
    lo,hi=kw['min'],kw['max'];count=(hi[0]-lo[0]+1)*(hi[1]-lo[1]+1)*(hi[2]-lo[2]+1);blocks=[]
    for pos,state in [([11,68,20],'Block{minecraft:cobblestone}'),([10,67,20],'Block{minecraft:dirt}')]:
     if all(lo[i]<=pos[i]<=hi[i]for i in range(3)):blocks.append({'pos':pos,'state':state,'solid':True,'fluid':False,'block_entity':False})
    return {'world_session':'w','phase':'done','scan_cells_read':count,'scan_total_cells':count,'scan_coherent':True,
      'scan_predictions':{'complete':True,'pending_count':0},'time':len(self.calls),'blocks':blocks}
   def request(self,*args,**kw):raise AssertionError('No bucket dispatch before valid floor')
  c=Client()
  with tempfile.TemporaryDirectory()as tmp:
   out=Path(tmp)/'attempt'
   with self.assertRaisesRegex(RuntimeError,'Original water network floor differs'):place(c,[10,68,20],[11,68,20],'west','k',m,out)
   book=json.loads((out/'progress.json').read_text());self.assertFalse(book['dispatch_started']);self.assertIsNone(book['pending'])
   self.assertEqual([10,67,20],book['blocking_floor_cells'][0]['pos'])
  self.assertEqual(['scan','scan'],c.calls)
 def valid(self):return {'id':'r','world_session':'w','phase':'done','bucket_water':{'request_id':'r','world_session':'w','pos':[10,68,20],'operation':'bucket_place','projected_model_water_source':True,'use_count':1,'confirmed':True,'unknown_outcome':False,'server_block_confirmed':True,'server_inventory_confirmed':True,'server_observed_state':SOURCE}}
 def test_receipt_requires_single_use_both_real_receipts_and_exact_scope(self):
  self.assertTrue(receipt(self.valid(),'r','w',[10,68,20]))
  for key,value in [('request_id','other'),('world_session','other'),('pos',[10,68,19]),('operation','bucket_fill'),('projected_model_water_source',False),('use_count',0),('use_count',2),('use_count',True),('confirmed',False),('unknown_outcome',True),('server_block_confirmed',False),('server_inventory_confirmed',False),('server_observed_state','Block{minecraft:water}[level=1]')]:
   r=self.valid();r['bucket_water'][key]=value;self.assertFalse(receipt(r,'r','w',[10,68,20]),key)
if __name__=='__main__':unittest.main()
