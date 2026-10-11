import copy
import json
import tempfile
import unittest
from pathlib import Path
from native_wheat_exit_reconcile import reconcile
from potato_farm import FarmWait


class NativeWheatExitReconcileTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'original';self.home.mkdir()
        self.cells=[[0,63,0],[1,63,0]];self.target=[.5,63.9375,.5]
        self.lease={'id':'lease','job_session':'task','world_session':'world'}
        self.inventory=[{'slot':0,'item':'minecraft:wheat','count':5},
                        {'slot':1,'item':'minecraft:wheat_seeds','count':8}]
        self.native={'id':'crop','phase':'done','time':10,'world_session':'world','control_revision':3,
            'supervision_lease':self.lease,'inventory':self.inventory,
            'planter_material_batch':{'protocol':1,'total':2,'grain_before':3,'harvest_sent':2,
                'removed_confirmed':2,'plant_sent':2,'replanted_confirmed':2,
                'cells_server_confirmed':True,'crop_positions':[[0,64,0],[1,64,0]]}}
        self.book={'complete':False,'pending':{'operation':'registered_farmland_exit_step','target':self.target},
            'controller':'Kit.AutoPlanter','world_session':'world','inventory_before':{'minecraft:wheat':3},
            'cells':self.cells,'scope':{'cells':self.cells,'scan_min':[0,63,0],'scan_max':[1,65,0]}}
        self.save('native-wheat-batch.json',self.book);self.save('native-wheat-receipt.json',self.native)
        for n in range(2):
            self.save('native-wheat-final-%d.json'%n,{'phase':'done','world_session':'world','time':11+n,
                'scan_cells_read':6,'scan_total_cells':6,'scan_start_revision':3,'scan_end_revision':3,
                'supervision_lease':self.lease,'inventory':self.inventory,'blocks':[row for p in self.cells for row in [
                    {'pos':p,'state':'Block{minecraft:farmland}[moisture=7]','fluid':False,'block_entity':False},
                    {'pos':[p[0],64,0],'state':'Block{minecraft:wheat}[age=1]',
                     'passable':True,'fluid':False,'block_entity':False}]]})
        self.save('farmland-exit.json',{'world_session':'world','target':self.target,
            'inventory_before':{'minecraft:wheat':5,'minecraft:wheat_seeds':8},'pending':True})
        self.events=[{'request_id':'crop'},
            {'request_id':'step','world_session':'world','op':'walk','phase':'done','time':.013,
             'params':{'task_session':'task','target':self.target,'arrival':.15},'pos':self.target,
             'health':20,'inventory_delta':{}},
            {'request_id':'read','world_session':'world','op':'scan','phase':'done','time':.015,
             'params':{'task_session':'task'},'pos':[.704,63.9375,.5],'health':20,'inventory_delta':{}}]
        self.eventfile=self.root/'events.jsonl';self.write_events()

    def save(self,name,value):(self.home/name).write_text(json.dumps(value))
    def write_events(self):self.eventfile.write_text('\n'.join(json.dumps(e)for e in self.events)+'\n')
    def test_exact_native_walk_and_later_dry_coasting_produce_a_copy_preserving_the_original(self):
        path=self.home/'native-wheat-batch.json';original=path.read_bytes()
        new,proof=reconcile(path,self.eventfile,self.root/'resolved')
        book=json.loads(new.read_text());self.assertTrue(book['complete']);self.assertIsNone(book['pending'])
        self.assertEqual(2,book['inventory_credit']);self.assertEqual(0,proof['new_game_commands'])
        self.assertEqual(original,path.read_bytes());self.assertEqual('step',proof['walk_request'])

    def test_missing_ack_foreign_owner_inventory_change_or_wet_unknown_footing_is_not_resolved(self):
        for n,kind in enumerate(('ack','owner','delta','outside','repeated')):
            with self.subTest(kind=kind):
                native=copy.deepcopy(self.native);events=copy.deepcopy(self.events)
                if kind=='ack':native['planter_material_batch']['replanted_confirmed']=1
                if kind=='owner':events[2]['params']['task_session']='foreign'
                if kind=='delta':events[2]['inventory_delta']={'minecraft:wheat':1}
                if kind=='outside':events[2]['pos']=[1.9,63.9375,.5]
                if kind=='repeated':events.append(copy.deepcopy(events[1]))
                self.save('native-wheat-receipt.json',native)
                self.eventfile.write_text('\n'.join(json.dumps(e)for e in events)+'\n')
                with self.assertRaises(FarmWait):reconcile(self.home/'native-wheat-batch.json',self.eventfile,self.root/('bad-%d'%n))
                self.assertFalse((self.root/('bad-%d'%n)).exists())


if __name__=='__main__':unittest.main()
