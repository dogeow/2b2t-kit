import copy
import unittest
from village_sleeping_beds import current_claims

class SleepingBedClaimsTest(unittest.TestCase):
 def scene(self):
  blocks=[];actors=[];flags=[]
  for uid,n,x in [('child',12,5),('parent',13,7)]:
   actors.append(dict(uuid=uid,id=n,type='minecraft:villager',alive=True,health=20,is_baby=False,pos=[x+.5,64.5625,10.5]))
   flags.append(dict(uuid=uid,entity_id=n,is_baby=False,sleeping=True,passenger=False,no_ai_client_flag=False,sleeping_pos=[float(x),64.,10.]))
   for z,part in [(10,'head'),(11,'foot')]:blocks.append(dict(pos=[x,64,z],state=f'Block{{minecraft:white_bed}}[facing=north,occupied=true,part={part}]'))
  return dict(world_session='w',time=1000,scan_cells_read=40,scan_total_cells=40,scan_entities=actors,blocks=blocks),dict(world_session='w',time=1050,villagers=flags)
 def test_current_sleeping_position_follows_bed_swap_instead_of_old_assignment(self):
  s,f=self.scene();s['scan_entities'][0]['pos'][0]=7.5;s['scan_entities'][1]['pos'][0]=5.5;f['villagers'][0]['sleeping_pos'][0]=7.;f['villagers'][1]['sleeping_pos'][0]=5.
  r=current_claims(s,f,{'parent','child'});self.assertEqual(r['child']['foot'],[7,64,11]);self.assertEqual(r['parent']['foot'],[5,64,11])
 def test_awake_or_unseen_resident_means_wait(self):
  for missing in [False,True]:
   s,f=self.scene()
   if missing:s['scan_entities'].pop()
   else:f['villagers'][1]['sleeping']=False
   self.assertIsNone(current_claims(s,f,{'parent','child'}))
 def test_breeding_babies_keep_their_actual_bed_only_with_explicit_opt_in(self):
  s,f=self.scene();s['scan_entities'][0]['is_baby']=True;f['villagers'][0]['is_baby']=True
  with self.assertRaises(ValueError):current_claims(s,f,{'parent','child'})
  self.assertEqual(current_claims(s,f,{'parent','child'},include_babies=True)['child']['head'],[5,64,10])
 def test_baby_opt_in_does_not_accept_disagreeing_or_missing_age(self):
  for value in [True,None,1]:
   s,f=self.scene();f['villagers'][0]['is_baby']=value
   with self.subTest(value=value),self.assertRaises(ValueError):current_claims(s,f,{'parent','child'},include_babies=True)
 def test_baby_opt_in_keeps_occupied_half_and_sleep_requirements(self):
  s,f=self.scene();s['scan_entities'][0]['is_baby']=True;f['villagers'][0]['is_baby']=True;s['blocks'][0]['state']=s['blocks'][0]['state'].replace('occupied=true','occupied=false')
  with self.assertRaises(ValueError):current_claims(s,f,{'parent','child'},include_babies=True)
 def test_stale_wrong_world_and_partial_scans_do_not_authorize_bed_selection(self):
  for field,value in [('time',3000),('world_session','other'),('scan_cells_read',39)]:
   s,f=self.scene();s[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):current_claims(s,f,{'child','parent'})
 def test_identity_duplicate_head_and_unoccupied_half_are_rejected(self):
  for mode in ['identity','shared_head','foot','head_missing','no_ai']:
   s,f=self.scene()
   if mode=='identity':f['villagers'][0]['entity_id']=99
   elif mode=='shared_head':f['villagers'][1]['sleeping_pos']=copy.deepcopy(f['villagers'][0]['sleeping_pos']);s['scan_entities'][1]['pos']=copy.deepcopy(s['scan_entities'][0]['pos'])
   elif mode=='foot':s['blocks'][1]['state']=s['blocks'][1]['state'].replace('occupied=true','occupied=false')
   elif mode=='head_missing':s['blocks'].pop(0)
   else:f['villagers'][0]['no_ai_client_flag']=True
   with self.subTest(mode=mode),self.assertRaises(ValueError):current_claims(s,f,{'child','parent'})
if __name__=='__main__':unittest.main()
