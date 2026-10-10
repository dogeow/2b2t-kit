import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from material_storage_index import select_sources,bind_source,remember_current,index_path,records


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/'config';self.root=self.base/'twob2tkit/automation';self.root.mkdir(parents=True)
        self.state={'server':'simpcraft.com:25565','dimension':'minecraft:overworld','world_session':'world',
                    'player_uuid':'player-a','time':200,'connected':True}
        self.c=SimpleNamespace(root=self.root,status=lambda:copy.deepcopy(self.state))
        self.a,self.b=[1,64,3],[5,64,3]
    def native(self,pos,items,**extra):
        return {'server':'simpcraft.com','worldId':'','dimension':'minecraft:overworld','playerId':'player-a',
            'x':pos[0],'y':pos[1],'z':pos[2],'containerPositions':[pos],
            'blockId':'minecraft:chest','status':'active','contentsDirty':False,'lastSeenEpochMillis':100,
            'items':[{'id':i,'count':n}for i,n in items.items()],**extra}
    def save_native(self,rows):
        (self.base/'twob2tkit.json').write_text(json.dumps({'storageSnapshots':rows}))
    def menu(self,count=64):
        rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(63)]
        rows[0].update(item='minecraft:dirt',count=count)
        self.state['menu']={'id':2,'type':'ChestMenu','cursor':{'count':0},'slots':rows}
    def test_local_search_skips_known_empty_and_routes_directly_to_the_matching_double_chest_half(self):
        self.save_native([self.native(self.a,{}),self.native(self.b,{'minecraft:dirt':64},containerPositions=[self.b,[6,64,3]])])
        r=select_sources(self.c,[self.a,[6,64,3]],{'minecraft:dirt':4})
        self.assertEqual([[6,64,3]],r['positions']);self.assertEqual([self.a],r['skipped_known_empty']);self.assertEqual(0,r['inventory_credit'])
    def test_new_worker_and_reconnect_reuse_post_withdrawal_and_deposit_counts(self):
        self.menu();bind_source(self.c,self.state,self.b,'minecraft:chest')
        self.state['time']=210;self.state['menu']['slots'][0]['count']=60;remember_current(self.c,self.state)
        self.state['time']=220;self.state['menu']['slots'][0]['count']=62;remember_current(self.c,self.state)
        self.state['world_session']='new-connection';new=SimpleNamespace(root=self.root,status=lambda:copy.deepcopy(self.state))
        r=records(new);self.assertEqual(62,r[0]['counts']['minecraft:dirt']);self.assertEqual(220,r[0]['observed_at'])
        self.assertEqual(self.b,select_sources(new,[self.a,self.b],{'minecraft:dirt':4})['positions'][0])
    def test_foreign_server_dimension_and_ender_player_never_match(self):
        self.save_native([self.native(self.a,{'minecraft:dirt':64},server='foreign'),
            self.native(self.b,{'minecraft:dirt':64},blockId='minecraft:ender_chest',playerId='other-player')])
        self.assertEqual([],records(self.c));self.assertEqual([self.b],select_sources(self.c,[self.b],{'minecraft:dirt':4},ender=True)['positions'])
    def test_empty_after_take_is_saved_and_not_reopened_on_the_next_request(self):
        self.menu();bind_source(self.c,self.state,self.b,'minecraft:chest')
        self.state['menu']['slots'][0]['count']=0;self.state['time']=210;remember_current(self.c)
        self.assertEqual([],select_sources(self.c,[self.b],{'minecraft:dirt':4})['positions'])
    def test_missing_and_newer_native_changes_override_old_local_quantities(self):
        self.menu();bind_source(self.c,self.state,self.b,'minecraft:chest')
        self.save_native([self.native(self.b,{},status='missing',lastSeenEpochMillis=100)])
        self.assertEqual([],select_sources(self.c,[self.b],{'minecraft:dirt':4})['positions'])
        self.save_native([self.native(self.b,{},lastSeenEpochMillis=300)])
        self.assertEqual([],select_sources(self.c,[self.b],{'minecraft:dirt':4})['positions'])
    def test_nested_shulker_contents_are_searchable_but_old_native_totals_are_not_inventory_credit(self):
        self.menu();r=self.state['menu']['slots'][0];r.update(item='minecraft:blue_shulker_box',count=1,contains=[{'item':'minecraft:dirt','count':32}])
        bind_source(self.c,self.state,self.b,'minecraft:chest')
        self.save_native([self.native(self.b,{'minecraft:blue_shulker_box':1},lastSeenEpochMillis=300)])
        self.assertEqual([self.b],select_sources(self.c,[self.b],{'minecraft:dirt':4})['positions'])
    def test_unclean_or_different_menu_does_not_overwrite_a_saved_record(self):
        self.menu();bind_source(self.c,self.state,self.b,'minecraft:chest');before=index_path(self.root).read_bytes()
        self.state['menu']['cursor']['count']=1;self.assertFalse(remember_current(self.c))
        self.state['menu']['cursor']['count']=0;self.state['menu']['id']=3;self.assertFalse(remember_current(self.c))
        self.assertEqual(before,index_path(self.root).read_bytes())
    def test_real_transfer_updates_local_quantity_after_each_withdrawal_and_deposit(self):
        from material_client import Client
        from unittest.mock import patch
        self.menu(10);self.state['inventory']=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]
        client=Client.__new__(Client);client.root=self.root
        def status():
            self.state['time']+=1
            self.state['inventory']=[{**r,'slot':i}for i,r in enumerate(self.state['menu']['slots'][27:])]
            return copy.deepcopy(self.state)
        client.status=status;bind_source(client,status(),self.b,'minecraft:chest')
        def move(session,state,source,destination,amount):
            a=self.state['menu']['slots'][source['slot']];b=self.state['menu']['slots'][destination['slot']]
            a['count']-=amount;b.update(item=source['item'],count=b['count']+amount)
        with patch('kit_runtime.storage.move_amount',side_effect=move):
            client.transfer('minecraft:dirt',3)
            self.assertEqual(7,records(client)[0]['counts']['minecraft:dirt'])
            client.transfer('minecraft:dirt',1,deposit=True)
            self.assertEqual(9,records(client)[0]['counts']['minecraft:dirt'])
    def test_no_capacity_does_not_reopen_a_matching_chest(self):
        self.save_native([self.native(self.b,{'minecraft:dirt':64})])
        self.state['inventory']=[{'slot':i,'item':'minecraft:stone','count':64,'max_stack':64}for i in range(36)]
        self.state['inventory'][-1].update(item='minecraft:air',count=0)
        self.assertEqual([],select_sources(self.c,[self.b],{'minecraft:dirt':4},reserve_empty=1)['positions'])
        self.assertEqual([self.b],select_sources(self.c,[self.b],{'minecraft:dirt':4},reserve_empty=0)['positions'])

if __name__=='__main__':unittest.main()
