import json,tempfile,unittest
from pathlib import Path
from projection_access import open_ladder_hatch,restore_ladder_hatch,ladder_room_route
from unittest.mock import patch
class Tests(unittest.TestCase):
 def test_previously_verified_hatch_is_rechecked_after_ladders_are_complete(self):
  with tempfile.TemporaryDirectory() as d:
   class Client:
    out=Path(d);calls=[]
    def status(self):return {'projection_selection':{'key':'house'}}
    def request(self,op,**args):
     self.calls.append((op,args))
     if op=='projection_audit':return {'projection_audit':{'placement_key':'house','mismatches':[]}}
     return {'blocks':[{'pos':[1,64,3],'state':'Block{minecraft:oak_trapdoor}[open=true]','fluid':False}]}
   c=Client();(c.out/'basement-hatch.json').write_text(json.dumps({'placement_key':'house','after':{'pos':[1,64,3]}}))
   self.assertEqual(open_ladder_hatch(c,[1,3])['pos'],[1,64,3])
   self.assertEqual(c.calls[-1],('scan',{'min':[1,64,3],'max':[1,64,3],'details':True}))
 def test_different_projection_cannot_reuse_cached_access(self):
  with tempfile.TemporaryDirectory() as d:
   class Client:
    out=Path(d)
    def status(self):return {'projection_selection':{'key':'new'}}
    def request(self,op,**args):
     assert op=='projection_audit';return {'projection_audit':{'placement_key':'new','mismatches':[]}}
   c=Client();(c.out/'basement-hatch.json').write_text(json.dumps({'placement_key':'old','after':{'pos':[1,64,3]}}))
   self.assertIsNone(open_ladder_hatch(c,[1,3]))

class CompletedLadderTests(unittest.TestCase):
 def client(self,out):
  class Client:
   def __init__(self):
    self.out=Path(out);self.stamp=0;self.calls=[];self.last=None;self.unknown=False
    self.rows=[{'pos':[1,y,3],'state':'Block{minecraft:ladder}[facing=east,waterlogged=false]','fluid':False}for y in range(61,64)]
    self.rows.append({'pos':[1,64,3],'state':'Block{minecraft:oak_trapdoor}[facing=east,half=top,open=false,powered=false,waterlogged=false]','fluid':False})
   def status(self):
    self.stamp+=250
    return {'time':self.stamp,'world_session':'w','pos':[1.5,65.2,3.5],'projection_selection':{'key':'house'},
            'inventory':[{'item':'minecraft:netherite_sword','count':1}]}
   def request(self,op,**args):
    self.calls.append((op,args));assert op=='scan'
    return {'phase':'done','blocks':[dict(r)for r in self.rows if args['min'][1]<=r['pos'][1]<=args['max'][1]]}
   def checked(self,op,**args):
    self.calls.append((op,args));self.last='native-1'
    if op=='interact':
     if self.unknown:raise RuntimeError('Original receipt missing')
     self.rows[-1]['state']=self.rows[-1]['state'].replace('open=false','open=true')if'open=false'in self.rows[-1]['state']else self.rows[-1]['state'].replace('open=true','open=false')
  return Client()
 def model(self,c):return {'placement_key':'house','content_hash':'hash','loaded_chunks_verified':True,'expected':[dict(r)for r in c.rows]}
 def test_completed_existing_ladder_uses_full_model_and_restores_only_its_hatch(self):
  with tempfile.TemporaryDirectory()as d,patch('projection_access.time.sleep'):
   c=self.client(d);model=self.model(c)
   row=open_ladder_hatch(c,[1,3],model=model)
   self.assertIn('open=true',row['state'])
   restore_ladder_hatch(c)
   self.assertEqual(model['expected'][-1]['state'],c.rows[-1]['state'])
   self.assertEqual(2,len([x for x in c.calls if x[0]=='interact']))
   self.assertTrue(all(x[1]['expected_hand']=='minecraft:netherite_sword'for x in c.calls if x[0]=='interact'))
 def test_unknown_first_interaction_blocks_open_and_cleanup_replays(self):
  with tempfile.TemporaryDirectory()as d:
   c=self.client(d);c.unknown=True;model=self.model(c)
   with self.assertRaisesRegex(RuntimeError,'receipt missing'):open_ladder_hatch(c,[1,3],model=model)
   with self.assertRaisesRegex(RuntimeError,'never replay'):open_ladder_hatch(c,[1,3],model=model)
   with self.assertRaisesRegex(RuntimeError,'no cleanup replay'):restore_ladder_hatch(c)
   self.assertEqual(1,len([x for x in c.calls if x[0]=='interact']))
 def test_changed_actual_ladder_and_other_model_cannot_toggle(self):
  with tempfile.TemporaryDirectory()as d:
   c=self.client(d);model=self.model(c);c.rows[0]['state']=c.rows[0]['state'].replace('east','west')
   with self.assertRaisesRegex(RuntimeError,'ladder changed'):open_ladder_hatch(c,[1,3],model=model)
   with self.assertRaisesRegex(RuntimeError,'current projection'):open_ladder_hatch(c,[1,3],model={**model,'placement_key':'other'})
   self.assertFalse(any(x[0]=='interact'for x in c.calls))
 def test_player_changed_hatch_is_preserved_during_restore(self):
  with tempfile.TemporaryDirectory()as d,patch('projection_access.time.sleep'):
   c=self.client(d);open_ladder_hatch(c,[1,3],model=self.model(c))
   c.rows[-1]['state']=c.rows[-1]['state'].replace('powered=false','powered=true')
   with self.assertRaisesRegex(RuntimeError,'preserve the new state'):restore_ladder_hatch(c)
   self.assertEqual(1,len([x for x in c.calls if x[0]=='interact']))

class FurnishedLadderExitTests(unittest.TestCase):
 def room(self):
  rows=[{'pos':[x,y,z],'state':'Block{minecraft:stone}'}for x in range(9)for z in range(9)for y in(0,3)]
  for x,z in((3,2),(5,2),(2,3),(6,3),(2,5),(6,5),(3,6),(5,6)):
   rows.append({'pos':[x,2,z],'state':'Block{minecraft:bookshelf}'})
  rows.extend({'pos':[1,y,3],'state':'Block{minecraft:ladder}[facing=east,waterlogged=false]'}for y in(1,2))
  return rows
 def test_new_bookshelves_block_the_direct_exit_but_leave_a_routed_middle_gap(self):
  from material_jobs.navigation import _body_sweep
  rows=self.room();start=[4.497,1.,5.499];shaft=[1,1,3];low=[0,0,0];high=[8,4,8]
  a,b=_body_sweep(start,[1.5,1.2,3.5])
  self.assertTrue(any(r['state']=='Block{minecraft:bookshelf}'and all(a[i]<=r['pos'][i]<=b[i]for i in range(3))for r in rows))
  path=ladder_room_route(rows,start,shaft,low,high)
  self.assertGreater(len(path),2)
  end=path[-1];self.assertEqual(1,abs(int(end[0])-shaft[0])+abs(int(end[2])-shaft[2]))
  self.assertTrue(any(p[0]<2.9 or p[2]<2.9 or p[2]>6.1 for p in path[1:]))
 def test_a_sealed_bookshelf_ring_does_not_authorize_breaking_it(self):
  from material_jobs.protocol import JobBlocked
  rows=self.room()+[{'pos':[x,2,z],'state':'Block{minecraft:bookshelf}'}for x,z in((2,4),(4,2),(6,4),(4,6))]
  with self.assertRaises(JobBlocked):ladder_room_route(rows,[4.5,1,4.5],[1,1,3],[0,0,0],[8,4,8])
if __name__=='__main__':unittest.main()
