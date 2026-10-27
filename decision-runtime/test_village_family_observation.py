import unittest
from village_family_observation import sleeping_family_homes,founders_still_asleep

class FamilyObservationTests(unittest.TestCase):
 def case(self):
  people=[];flags=[];rows={}
  for i,uid in enumerate(['p1','p2','c1','c2']):
   people.append({'uuid':uid,'health':20,'is_baby':False,'pos':[i+.5,64.5625,10.5]})
   flags.append({'uuid':uid,'client_health':20,'is_baby':False,'passenger':False,'no_ai_client_flag':False,'sleeping':True})
   for z,part in [(10,'head'),(11,'foot')]:rows[i,64,z]={'state':f'Block{{minecraft:white_bed}}[facing=north,occupied=true,part={part}]'}
  return {'world_session':'w','loaded_villagers':{'villagers':people}},{'world_session':'w','villagers':flags},rows
 def test_derives_child_beds_from_current_sleeping_identity(self):
  s,f,r=self.case();out=sleeping_family_homes(s,f,r,['p1','p2'],['c1','c2'])
  self.assertEqual([2,64,11],out['children']['c1']['foot']);self.assertEqual([3,64,10],out['children']['c2']['head']);self.assertTrue(founders_still_asleep(s,f,['p1','p2']))
 def test_waking_missing_or_changed_family_never_authorizes_unlinking(self):
  for mode in ['awake','missing','world','baby','health','bed','shared']:
   with self.subTest(mode=mode):
    s,f,r=self.case()
    if mode=='awake':f['villagers'][0]['sleeping']=False
    if mode=='missing':f['villagers'].pop()
    if mode=='world':f['world_session']='other'
    if mode=='baby':s['loaded_villagers']['villagers'][2]['is_baby']=True
    if mode=='health':f['villagers'][1]['client_health']=19
    if mode=='bed':r.pop((2,64,10))
    if mode=='shared':s['loaded_villagers']['villagers'][2]['pos']=[.5,64.5625,10.5]
    self.assertIsNone(sleeping_family_homes(s,f,r,['p1','p2'],['c1','c2']))
 def test_sleep_guard_fails_closed_on_missing_or_awake_founder(self):
  s,f,r=self.case();f['villagers'][0]['sleeping']=False;self.assertFalse(founders_still_asleep(s,f,['p1','p2']));self.assertFalse(founders_still_asleep(s,None,['p1','p2']))

if __name__=='__main__':unittest.main()
