import math,unittest
from packed_supplies import clear_player_from_pad,player_intersects_pad

class PadFlightClient:
 world='w';task='t'
 def __init__(self,mode='clear'):
  self.pos=[.5,1.0,.5];self.calls=[];self.mode=mode
 def status(self):
  return {'pos':self.pos,'flight':True,'air_only_navigation_protocol':2,'guard_armed':True,'guard_pve_only':True,'health':20,'food':20,'control_revision':7,
   'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':7}}
 def request(self,op,**kw):
  self.calls.append((op,kw))
  if op=='scan':
   lo,hi=kw['min'],kw['max'];n=math.prod(hi[i]-lo[i]+1 for i in range(3));rows=[]
   if self.mode=='wet':rows=[{'pos':[lo[0],lo[1],lo[2]],'state':'Block{minecraft:water}[level=0]','fluid':True,'passable':False}]
   return {'phase':'done','world_session':'w','scan_coherent':self.mode!='unsettled','scan_cells_read':n,'scan_total_cells':n,
           'scan_predictions':{'complete':True,'pending_count':0},'blocks':rows}
  if op=='navigate':
   if self.mode=='move_unknown':return {'phase':'waiting'}
   self.pos=list(kw['target']);return {'phase':'done'}
  raise AssertionError(op)

class PackedFlightClearanceTests(unittest.TestCase):
 def test_loaded_dry_hover_clears_pad_without_needing_a_full_cube_floor(self):
  c=PadFlightClient();clear_player_from_pad(c,[0,1,0]);self.assertFalse(player_intersects_pad(c.pos,[0,1,0]))
  moves=[kw for op,kw in c.calls if op=='navigate'];self.assertEqual(1,len(moves));self.assertIs(moves[0]['air_only'],True);self.assertEqual([-1.5,1.1,.5],moves[0]['target'])
 def test_water_or_unsettled_scan_never_moves(self):
  for mode in ['wet','unsettled']:
   c=PadFlightClient(mode)
   with self.assertRaisesRegex(RuntimeError,'No currently loaded'):clear_player_from_pad(c,[0,1,0])
   self.assertFalse(any(op=='navigate'for op,_ in c.calls))
 def test_an_uncertain_motion_never_falls_back_to_a_second_pose(self):
  c=PadFlightClient('move_unknown')
  with self.assertRaisesRegex(RuntimeError,'outcome retained'):clear_player_from_pad(c,[0,1,0])
  self.assertEqual(1,sum(op=='navigate'for op,_ in c.calls))
 def test_an_already_clear_player_is_not_repositioned(self):
  c=PadFlightClient();c.pos=[3.5,1.1,.5];clear_player_from_pad(c,[0,1,0]);self.assertEqual([],c.calls)
if __name__=='__main__':unittest.main()
