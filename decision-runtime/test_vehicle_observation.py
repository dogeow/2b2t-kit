import copy,json,tempfile,unittest
from pathlib import Path
from vehicle_observation import read,read_frame,villagers_aboard,SCOPE

class VehicleObservationTests(unittest.TestCase):
    def test_dead_passenger_can_only_be_read_for_safety_and_never_authorizes_transport(self):
        state=dict(connected=True,world_session='w',server='s',dimension='d',player_uuid='player',time=2000)
        passenger=dict(uuid='v',id=2,type='minecraft:villager',alive=False,is_baby=False,has_custom_name=False,health=0)
        frame=dict(state,protocol=1,scope=SCOPE,truncated=False,vehicles=[dict(uuid='boat',id=1,alive=True,type='minecraft:oak_boat',pos=[0,64,0],passengers=[passenger])])
        with tempfile.TemporaryDirectory()as directory:
            (Path(directory)/'loaded-vehicle-survey.json').write_text(json.dumps(frame));self.assertIsNone(read_frame(directory,state));observed=read_frame(directory,state,allow_dead_passengers=True);self.assertIsNotNone(observed);self.assertFalse(villagers_aboard(observed['vehicles'][0],['v']))
    def test_old_world_player_partial_and_stale_surveys_cannot_supply_transport_identity(self):
        state={'connected':True,'world_session':'w','server':'s','dimension':'d','player_uuid':'player','time':2000}
        frame={**state,'protocol':1,'scope':SCOPE,'truncated':False,'vehicles':[
            {'uuid':'boat','id':1,'alive':True,'type':'minecraft:oak_boat','pos':[0,64,0],'passengers':[]}]}
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'loaded-vehicle-survey.json';path.write_text(json.dumps(frame))
            self.assertEqual(read(directory,state)[0]['uuid'],'boat')
            for update in ({'world_session':'other'},{'player_uuid':'other'},{'truncated':True},{'time':500},{'connected':False}):
                path.write_text(json.dumps({**frame,**update}));self.assertEqual(read(directory,state),[])
            path.write_text(json.dumps({**frame,'vehicles':[]}))
            self.assertIsNotNone(read_frame(directory,state))
            path.unlink();self.assertIsNone(read_frame(directory,state))
    def test_exact_passengers_and_resolved_player_leash_required_before_towing(self):
        row={'passengers':[{'uuid':'founder','type':'minecraft:villager','alive':True,'is_baby':False,'has_custom_name':False,'health':20}],
             'leashed':True,'leash_resolved':True,'leash_holder':{'uuid':'player'}}
        self.assertTrue(villagers_aboard(row,['founder'],player_uuid='player'))
        for update in ({'health':18},{'is_baby':True},{'has_custom_name':True},{'type':'minecraft:player'}):
            changed=copy.deepcopy(row);changed['passengers'][0].update(update)
            self.assertFalse(villagers_aboard(changed,['founder'],player_uuid='player'))
        self.assertFalse(villagers_aboard(row,['other'],player_uuid='player'))
        self.assertFalse(villagers_aboard(row,['founder'],player_uuid='other'))
        self.assertFalse(villagers_aboard({**row,'leash_resolved':False},['founder'],player_uuid='player'))

if __name__=='__main__':unittest.main()
