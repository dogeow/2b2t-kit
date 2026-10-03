"""Idle adapter uses only an existing wheat field and the shared real-proof kernel."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from farm_preparation import PreparationWait,preparation_lock
from idle_service_native import NativeRunner
from potato_harvest import _counts
from test_wheat_harvest import WheatHarvestClient,REQUEST,WHEAT


class AdapterClient(WheatHarvestClient):
    def status(self):return super().status()|{'server':self.server}
    def request(self,op,**params):
        result=super().request(op,**params)
        if op=='scan':result.update(phase='done',id='scan-'+str(self.time))
        return result


class RegisteredWheatAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.client=AdapterClient(self.root);self.client.heartbeat.close=lambda:None;self.client.job_progress=None
        self.service=SimpleNamespace(root=self.root,key='service',book={'sequence':1},clock=lambda:0,checkpoint=lambda *a:None,
            profile={'plant_registries':[str(self.client.registry)]})
        self.directory=self.root/'idle-job';self.directory.mkdir();self.runner=NativeRunner(self.service,'plant',self.directory);self.runner.client=self.client
        self.addCleanup(self.release)
        self.profile={'server':'server','dimension':'minecraft:overworld'}
    def release(self):
        if self.runner.field_context is not None:
            context=self.runner.field_context;self.runner.field_context=None;context.__exit__(None,None,None)
    def pickup(self,client,drop,observation):
        item,count=drop['stack']['item'],drop['stack']['count'];client.credit(item,count)
        client.entities=[e for e in client.entities if e.get('uuid')!=drop['uuid']]
        client.pending_pickup=None
        return {'movement_only':True}
    def test_mature_registered_wheat_produces_actual_feed_grain_and_replants_exact_four_cells(self):
        original=self.client.plant_journal.read_bytes()
        def arrived(client,target,checkpoint,trace):
            checkpoint();client.extra['pos']=target[:];trace.append({'target':target,'phase':'done'})
        with patch('idle_service_native._travel',side_effect=arrived),patch('idle_service_native.make_pickup',return_value=self.pickup) as factory:
            result=self.runner._registered_plant_job(self.client.status(),self.profile)
        self.assertEqual('done',result['phase'],result);self.assertFalse(result['pending']);self.assertEqual(4,result['harvested_replanted'])
        self.assertEqual(4,result['wheat_gain']);self.assertEqual(4,_counts(self.client.status())[WHEAT]);self.assertGreaterEqual(_counts(self.client.status())['minecraft:wheat_seeds'],4)
        self.assertEqual('wheat',factory.call_args.kwargs['crop']);self.assertEqual(original,self.client.plant_journal.read_bytes())
        self.assertEqual(4,sum(op=='mine_block' for op,_ in self.client.calls));self.assertEqual(4,self.client.plant_calls)
        with self.assertRaises(PreparationWait):
            with preparation_lock(self.root,self.client.status(),REQUEST):pass
        self.release()
        with preparation_lock(self.root,self.client.status(),REQUEST):pass
    def test_old_unknown_harvest_is_retained_without_scan_or_new_world_action(self):
        old=self.root/'original-unknown.json';old.write_text('{"pending":{"operation":"harvest"},"world_session":"world-1"}\n')
        (self.client.registry.parent/'harvest-active.json').write_text(json.dumps({'journal':str(old)}));before=old.read_bytes()
        result=self.runner._registered_plant_job(self.client.status(),self.profile)
        self.assertEqual(('WAIT_RECONCILE',True,str(old)),(result['code'],result['pending'],result['active_journal']))
        self.assertEqual([],self.client.calls);self.assertEqual(before,old.read_bytes());self.assertTrue(self.runner.has_unknown())
    def test_immature_wheat_does_not_dispatch_harvest_or_till(self):
        for row in self.client.rows.values():
            if row['state'].startswith('Block{minecraft:wheat}'):row['state']='Block{minecraft:wheat}[age=3]'
        with patch('idle_service_native.plant',return_value={'phase':'idle'}) as plant:
            result=self.runner._registered_plant_job(self.client.status(),self.profile)
        self.assertFalse(result['pending']);self.assertTrue(plant.call_args.kwargs['existing_farmland_only'])
        self.assertTrue(all(op=='scan' for op,_ in self.client.calls))


if __name__=='__main__':unittest.main()
