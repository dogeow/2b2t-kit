import copy,unittest
from known_injury_station_repair import check
class Tests(unittest.TestCase):
 def state(self):
  return {'connected':True,'world_session':'w','health':20,'screen':'','manual_movement':False,'guard_pve_only':True,'supervision_lease':{'id':'lease','job_session':'job','kind':'materials','world_session':'w'},'loaded_villagers':{'villagers':[{'uuid':'hurt','health':11.389759},{'uuid':'other','health':20}]}}
 def test_only_known_stable_or_improving_injury_is_accepted(self):
  s=self.state();self.assertIs(check(s,'w',{'hurt':11.389759}),s);s['loaded_villagers']['villagers'][0]['health']=20;check(s,'w',{'hurt':11.389759})
 def test_new_damage_control_changes_and_invalid_baselines_stop_repair(self):
  for mode in ['decline','new_injury','player','world','manual','menu','no_owner','owner_world','pvp','hold','nan','dead']:
   s=copy.deepcopy(self.state())
   if mode=='decline':s['loaded_villagers']['villagers'][0]['health']=10
   if mode=='new_injury':s['loaded_villagers']['villagers'][1]['health']=19
   if mode=='player':s['health']=19
   if mode=='world':s['world_session']='other'
   if mode=='manual':s['manual_movement']=True
   if mode=='menu':s['screen']='InventoryScreen'
   if mode=='no_owner':s['supervision_lease']=None
   if mode=='owner_world':s['supervision_lease']['world_session']='other'
   if mode=='pvp':s['guard_pve_only']=False
   if mode=='hold':s['safety_hold']={'active':True}
   if mode=='nan':s['loaded_villagers']['villagers'][0]['health']=float('nan')
   if mode=='dead':s['loaded_villagers']['villagers'][0]['health']=0
   with self.subTest(mode=mode),self.assertRaises(RuntimeError):check(s,'w',{'hurt':11.389759})
  for baseline in [{},{'hurt':0},{'hurt':20},{'hurt':float('nan')}]:
   with self.assertRaises(ValueError):check(self.state(),'w',baseline)
if __name__=='__main__':unittest.main()
