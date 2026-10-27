import copy,json,tempfile,unittest
from pathlib import Path
from villager_events import read,pickups,entity_events,joined_pickups,SCOPE

class VillagerEventsTest(unittest.TestCase):
    def witnessed(self):
        return {'world_session':'w','runtime_generation':1,'observed_at':9980,
                'entity':{'id':2,'uuid':'bread-drop','type':'minecraft:item','stack':{'item':'minecraft:bread','count':3}}}
    def test_removed_entity_requires_its_prior_exact_witness_and_resolved_server_collector(self):
        s,f=self.fixture();e=f['events'][0];e['kind']='pickup_entities_unresolved';e.pop('source');e.pop('item')
        frame=self.reading(f,s);proof=joined_pickups(frame,'minecraft:bread',{'founder'},self.witnessed(),after_time=9970)
        self.assertEqual(3,proof[0]['amount']);self.assertEqual('bread-drop',proof[0]['joined_source']['uuid'])
        e.pop('collector');self.assertEqual([],joined_pickups(self.reading(f,s),'minecraft:bread',{'founder'},self.witnessed()))
    def test_witness_from_another_world_generation_time_or_stack_cannot_credit_food(self):
        s,f=self.fixture();frame=self.reading(f,s)
        for changes in({'world_session':'other'},{'runtime_generation':0},{'observed_at':9991},
                        {'observed_at':8999},{'entity':{**self.witnessed()['entity'],'id':99}},
                        {'entity':{**self.witnessed()['entity'],'uuid':'other'}},
                        {'entity':{**self.witnessed()['entity'],'stack':{'item':'minecraft:bread','count':1}}}):
            self.assertEqual([],joined_pickups(frame,'minecraft:bread',{'founder'},{**self.witnessed(),**changes}))
    def test_unresolved_collector_cannot_claim_a_different_entity_number(self):
        s,f=self.fixture();e=f['events'][0];e['kind']='pickup_entities_unresolved';e.pop('source');e.pop('item');e['collector']['entity_id']=99
        self.assertIsNone(self.reading(f,s))
    def fixture(self):
        state={'connected':True,'time':10000,'world_session':'w','server':'s','dimension':'minecraft:overworld',
               'player_uuid':'player','runtime_version':'1.8.11','runtime_generation':1}
        def identity(id,uuid,type):return{'entity_id':id,'uuid':uuid,'type':type,'pos':[1,64,2]}
        source=identity(2,'bread-drop','minecraft:item');npc=identity(3,'founder','minecraft:villager')
        npc.update(is_baby=False,sleeping=False,passenger=False,no_ai_client_flag=False)
        event={'kind':'item_pickup','source_entity_id':2,'collector_entity_id':3,'source':source,'collector':npc,
               'item':'minecraft:bread','amount':3,'sequence':1,'received_at':9990}
        frame={**state,'protocol':1,'scope':SCOPE,'subscriber_active':True,'world_entered_at':9000,'events':[event],'villagers':[npc]}
        return state,frame
    def reading(self,frame,state):
        with tempfile.TemporaryDirectory()as d:
            (Path(d)/'loaded-villager-events.json').write_text(json.dumps(frame));return read(d,state)
    def test_requires_exact_current_world_engine_generation_and_fresh_listener(self):
        s,f=self.fixture();self.assertIsNotNone(self.reading(f,s))
        for update in({'world_session':'old'},{'runtime_generation':0},{'runtime_version':'old'},{'time':8000},
                       {'connected':False},{'subscriber_active':False},{'world_entered_at':10001}):
            self.assertIsNone(self.reading({**f,**update},s))
    def test_positive_receipt_matches_exact_collector_source_item_and_time(self):
        s,f=self.fixture();frame=self.reading(f,s)
        self.assertEqual(3,pickups(frame,'minecraft:bread',{'founder'},sources={'bread-drop'},after_time=9900)[0]['amount'])
        self.assertEqual([],pickups(frame,'minecraft:bread',{'player'}))
        self.assertEqual([],pickups(frame,'minecraft:bread',{'founder'},sources={'another-drop'}))
        self.assertEqual([],pickups(frame,'minecraft:bread',{'founder'},after_time=9991))
        for amount in(0,65,True):
            bad=copy.deepcopy(f);bad['events'][0]['amount']=amount;self.assertIsNone(self.reading(bad,s))
    def test_absent_food_or_unresolved_packet_is_never_invented_as_npc_pickup(self):
        s,f=self.fixture();f['events']=[];frame=self.reading(f,s)
        self.assertEqual([],pickups(frame,'minecraft:bread',{'founder'}))
        f['events']=[{'kind':'pickup_entities_unresolved','source_entity_id':2,'collector_entity_id':3,'amount':3,'sequence':1,'received_at':9990}]
        self.assertEqual([],pickups(self.reading(f,s),'minecraft:bread',{'founder'}))
        with self.assertRaises(ValueError):pickups(None,'minecraft:bread',{'founder'})
    def test_duplicate_packets_and_mixed_entity_identity_cannot_double_count_food(self):
        s,f=self.fixture();f['events'].append(copy.deepcopy(f['events'][0]));self.assertIsNone(self.reading(f,s))
        s,f=self.fixture();f['events'][0]['collector']['entity_id']=99;self.assertIsNone(self.reading(f,s))

if __name__=='__main__':unittest.main()
