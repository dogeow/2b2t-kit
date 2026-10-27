import itertools,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from material_jobs.dry_hover_harvest import run,known_merged_drop,pickup

ITEM='minecraft:terracotta'
def row():return {'pos':[0,4,0],'state':'Block{minecraft:terracotta}','solid':True,'fluid':False,'block_entity':False}


class HoverAggregatePickupTest(unittest.TestCase):
    def test_current_badlands_hostile_stops_before_any_mining_or_movement(self):
        q={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
           'inventory':[{'slot':0,'item':ITEM,'count':4}],
           'entities':[{'uuid':'zombie','hostile':True,'alive':True,'health':20}]}
        c=SimpleNamespace(world='w',status=lambda:q,request=Mock())
        region={'authorized':True,'source':'natural_survey','item':ITEM,'min':[-3,1,-3],'max':[3,8,3]}
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.terracotta_harvest.verify_region'),\
             patch('material_jobs.dry_hover_harvest.move')as move:
            result=run(c,{},region,64,out,lambda:None,item=ITEM)
        self.assertEqual('WAIT_SOURCE_HOSTILE',result['code']);self.assertEqual(4,result['verified_count'])
        self.assertIsNone(result['pending']);c.request.assert_not_called();move.assert_not_called()
    def test_observed_merged_two_stack_can_arrive_without_replaying_collection(self):
        received=False;clock=itertools.count(0,.2)
        drop={'uuid':'merged','type':'minecraft:item','pos':[.5,4.125,.5],'stack':{'item':ITEM,'count':2}}
        def state():return {'pos':[1.5,4.2,.5],'entities':[]if received else[drop],
            'inventory':[{'slot':0,'item':ITEM,'count':6 if received else 4}]}
        def arriving(*args):
            nonlocal received
            received=True;return[]
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.dry_hover_harvest._scan',return_value=[]),\
             patch('material_jobs.dry_hover_harvest.pickup_offers',side_effect=arriving),\
             patch('material_jobs.dry_hover_harvest.move')as movement,patch('material_jobs.dry_hover_harvest.time.sleep'),\
             patch('material_jobs.dry_hover_harvest.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(pickup(SimpleNamespace(world='w'),drop,4,out,state,item=ITEM,expected_count=2))
            book=json.loads((Path(out)/'pickup.json').read_text());self.assertEqual(6,book['after'])
            self.assertEqual(2,book['expected_count']);movement.assert_not_called()
    def test_only_a_known_unreceived_owned_stack_can_be_offered_as_a_merge(self):
        old={'uuid':'old','type':'minecraft:item','pos':[.5,4,.5],
             'stack':{'item':ITEM,'count':1,'max_stack':64}}
        deferred={'original_drop_uuid':'old','server_removed':True,'actual_gain':0,
                  'inventory_credit':0,'mining_replayed':False}
        for uuid in ('old','new'):
            post={**old,'uuid':uuid,'stack':{**old['stack'],'count':2}}
            self.assertIsNotNone(known_merged_drop([post],{'old':old},[deferred],ITEM,[0,4,0]))
            self.assertIsNone(known_merged_drop([post],{'old':old},[{**deferred,'actual_gain':1}],ITEM,[0,4,0]))
            self.assertIsNone(known_merged_drop([post],{'old':old},[],ITEM,[0,4,0]))
            self.assertIsNone(known_merged_drop([post],{'old':old},[deferred],ITEM,[20,4,0]))

    def test_extra_actual_stock_keeps_source_allocation_unresolved_and_never_remines(self):
        for inflight in (None,{'request_id':'unknown-move'}):
            with self.subTest(inflight=inflight):
                clock=itertools.count(1000)
                inventory=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]
                inventory[0].update(item=ITEM,count=4)
                inventory[1].update(item='minecraft:diamond_pickaxe',count=1,durability=100,max_durability=1561)
                state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
                       'pos':[1.5,4.2,.5],'entities':[],'inventory':inventory}
                drop={'uuid':'new-drop','type':'minecraft:item','pos':[.5,4.125,.5],'stack':{'item':ITEM,'count':1}}
                proof={'id':'r','world_session':'w','phase':'done','server_confirmed':True,'outcome_pending':False,
                       'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
                       'server_update_seen':True,'server_observed_state':'Block{minecraft:air}',
                       'native_sequence':3,'server_ack_sequence':3,'mining_target':[0,4,0]}
                def mine(*a,**kw):state['entities']=[drop];return proof
                def together(*a,**kw):
                    inventory[0]['count']=6;state['entities']=[]
                    raise RuntimeError('Original mined item vanished without actual inventory gain')
                c=SimpleNamespace(world='w',last='r',native_inflight=inflight,
                    status=lambda:{**state,'time':next(clock)},request=Mock(side_effect=mine),set_progress=Mock())
                region={'authorized':True,'source':'natural_survey','item':ITEM,'min':[-3,1,-3],'max':[3,8,3]}
                choice={'target':[0,4,0],'state':'Block{minecraft:terracotta}','station':[1.5,4.2,.5],'face':'east'}
                with tempfile.TemporaryDirectory()as out,patch('material_jobs.terracotta_harvest.verify_region'),\
                     patch('material_jobs.dry_hover_harvest._scan',side_effect=[[row()],[row()],[]]),\
                     patch('material_jobs.dry_hover_harvest.offers',return_value=[choice]),\
                     patch('material_jobs.dry_hover_harvest._protected',return_value=False),\
                     patch('material_jobs.dry_hover_harvest._choose_tool'),patch('material_jobs.dry_hover_harvest.move'),\
                     patch('material_jobs.dry_hover_harvest.visible_face',return_value=True),\
                     patch('material_jobs.dry_hover_harvest.context_for',return_value=True),\
                     patch('material_jobs.dry_hover_harvest.pickup',side_effect=together),patch('material_jobs.dry_hover_harvest.time.sleep'):
                    if inflight is None:
                        result=run(c,{},region,64,out,lambda:None,max_blocks=1,item=ITEM)
                        self.assertEqual(6,result['verified_count']);self.assertIsNone(result['pending'])
                        record=result['unattributed_pickups'][0]
                        self.assertEqual(2,record['aggregate_inventory_gain']);self.assertEqual(0,record['actual_gain'])
                        self.assertTrue(record['source_allocation_unresolved'])
                    else:
                        with self.assertRaises(RuntimeError):run(c,{},region,64,out,lambda:None,max_blocks=1,item=ITEM)
                        self.assertEqual('r',json.loads((Path(out)/'harvest.json').read_text())['pending']['request_id'])
                self.assertEqual(1,c.request.call_count)

if __name__=='__main__':unittest.main()
