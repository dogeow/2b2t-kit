"""New maintenance plants only listed AIR/farmland, preserving the original24 history."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

from farm_reseed import run,prepare_journal
from farm_reseed_cli import main,execute
from potato_farm import FarmWait,plan,_key
from test_wheat_farm import WheatClient,WHEAT
from test_potato_farm import row


class RegisteredClient(WheatClient):
    def status(self):return super().status()|{'server':self.server}
    def __init__(self,root):
        super().__init__(seeds=8,farmland=True);self.root=Path(root)
        self.layout=plan(WHEAT);self.cell=self.layout['cells'][0][:]
        for pos in self.layout['cells']:
            above=[pos[0],pos[1]+1,pos[2]]
            if pos!=self.cell:self.rows[tuple(above)]=row(above,'Block{minecraft:wheat}[age=7]',False)
        scope={'server':'server','dimension':'minecraft:overworld','layout':self.layout}
        key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
        self.registry=self.root/'farms'/key/'registry.json';self.registry.parent.mkdir(parents=True)
        self.original_dir=self.root/'original';self.original_dir.mkdir();self.original=self.original_dir/('wheat-farm-'+key+'.json')
        self.registry.write_text(json.dumps({'scope':scope,'world_session':'old-complete-connection','directory':str(self.original_dir)}))
        self.original.write_text(json.dumps({'schema':1,'scope':scope,'world_session':'old-complete-connection','complete':True,'pending':None,
            'seeds_before':24,'cells':{_key(pos):{'planted':True,'plant':{'receipt':'original'}} for pos in self.layout['cells']}}))


class ReseedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.client=RegisteredClient(self.root)
    def execute(self,**kwargs):return run(self.client,self.client.registry,[self.client.cell],**kwargs)
    def test_one_new_maintenance_interact_exact_seed_loss_two_frames_and23_observations(self):
        originals=(self.client.registry.read_bytes(),self.client.original.read_bytes());result=self.execute()
        self.assertEqual(('done',1,1,23),(result['phase'],result['new_reseed'],result['target_cells'],result['observed_existing']))
        self.assertEqual(1,len(self.client.interact_calls()));self.assertEqual(250,self.client.inv[0]['durability'])
        book=json.loads(Path(result['journal']).read_text());self.assertEqual(1,len(book['receipts']));self.assertEqual(23,len(book['observed_existing']))
        receipt=book['receipts'][_key(self.client.cell)];self.assertEqual([8,7],[receipt[key]['minecraft:wheat_seeds'] for key in ('before_counts','after_counts')])
        self.assertEqual(2,len(receipt['observed_times']));self.assertEqual('Block{minecraft:wheat}[age=0]',receipt['crop_state'])
        self.assertTrue(all(value['origin']=='current_connection_observation_not_new_planting' for value in book['observed_existing'].values()))
        self.assertEqual(originals,(self.client.registry.read_bytes(),self.client.original.read_bytes()))
    def test_unknown_interact_cannot_be_replayed_or_bypassed_with_new_output(self):
        self.client.fail_op='plant';result=self.execute();self.assertEqual('WAIT_RECONCILE',result['code'])
        original=Path(result['journal']).read_bytes();self.assertEqual(1,len(self.client.interact_calls()))
        self.client.fail_op=None
        for output in (None,self.root/'new-output'):
            with self.assertRaises(FarmWait):self.execute(out=output)
        self.assertEqual(1,len(self.client.interact_calls()));self.assertEqual(original,Path(result['journal']).read_bytes())
    def test_nonfarmland_unlisted_air_wrong_crop_and_occupied_target_send_no_interact_or_hoe(self):
        for fault in ('grass','unlisted_air','wrong_crop','occupied_target'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as folder:
                c=RegisteredClient(folder);other=c.layout['cells'][1];target=c.cell
                if fault=='grass':c.rows[tuple(target)]=row(target,'Block{minecraft:grass_block}[snowy=false]')
                if fault=='unlisted_air':c.rows.pop((other[0],other[1]+1,other[2]))
                if fault=='wrong_crop':c.rows[(other[0],other[1]+1,other[2])]['state']='Block{minecraft:potatoes}[age=7]'
                if fault=='occupied_target':c.rows[(target[0],target[1]+1,target[2])]=row([target[0],target[1]+1,target[2]],'Block{minecraft:wheat}[age=7]',False)
                result=run(c,c.registry,[target]);self.assertEqual('waiting',result['phase']);self.assertFalse(c.interact_calls())
                self.assertEqual(250,c.inv[0]['durability']);self.assertTrue(all(op=='scan' for op,_ in c.calls))
    def test_seed_or_crop_delta_missing_retains_unknown_and_no_second_interact(self):
        self.client.wrong_count=1;result=self.execute();self.assertEqual('WAIT_RECONCILE',result['code'])
        self.assertTrue(result['pending']);self.assertEqual(1,len(self.client.interact_calls()))
        with self.assertRaises(FarmWait):self.execute()
        self.assertEqual(1,len(self.client.interact_calls()))
    def test_original_pending_or_active_unknown_harvest_rejects_before_game_request(self):
        original=json.loads(self.client.original.read_text());original['pending']={'operation':'plant'};self.client.original.write_text(json.dumps(original))
        with self.assertRaises(FarmWait):self.execute()
        self.assertEqual([],self.client.calls)
        original['pending']=None;self.client.original.write_text(json.dumps(original));old=self.root/'old-harvest.json';old.write_text('{"pending":{"operation":"harvest"}}')
        (self.client.registry.parent/'harvest-active.json').write_text(json.dumps({'journal':str(old)}))
        with self.assertRaises(FarmWait):self.execute()
        self.assertEqual([],self.client.calls)
    def test_cell_bounds_budget_and_registry_hash_are_strict(self):
        for cells in ([],[self.client.cell]*2,[[100,63,0]],self.client.layout['cells'][:5]):
            with self.assertRaises(ValueError):run(self.client,self.client.registry,cells)
        changed=json.loads(self.client.registry.read_text());changed['scope']['server']='other';self.client.registry.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):self.execute()
        self.assertFalse(self.client.calls)
    def test_cli_forwards_only_explicit_registry_and_cells(self):
        with patch('farm_reseed_cli.execute',return_value={'phase':'done','new_reseed':1}) as execute,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0,main(['--registry',str(self.client.registry),'--cell','-2','63','-2','--no-move']))
        self.assertEqual([[-2,63,-2]],execute.call_args.args[2]);self.assertTrue(execute.call_args.args[4])
    def test_far_route_precondition_rejects_before_client_or_heartbeat_creation(self):
        state=self.client.status();state['pos']=[self.client.layout['center'][0]+385,140,self.client.layout['center'][2]]
        values=__import__('farm_reseed').registered(self.root,self.client.registry,[self.client.cell],server=self.client.server)
        with patch('farm_reseed_cli.read_fresh',return_value=state),patch('farm_reseed_cli.require_unlocked'),\
                patch('farm_reseed_cli.registered',return_value=values),patch('farm_reseed_cli.MaterialClient')as factory:
            with self.assertRaisesRegex(RuntimeError,'bounded384'):execute(self.root,self.client.registry,[self.client.cell])
        factory.assert_not_called()


if __name__=='__main__':unittest.main()
