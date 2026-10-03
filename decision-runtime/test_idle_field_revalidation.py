"""A new connection observes completed fields; it never adopts unknown old actions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from farm_preparation import _identity,assert_preparation_resolved
from idle_field_revalidation import revalidate_fields
from idle_service import default_profile
from potato_farm import plan,_key
from test_potato_farm import row


class RevalidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.request={'authorized':True,'center':[0,63,0],'crop':'wheat'};self.layout=plan(self.request)
        self.scope={'server':'example.test','dimension':'minecraft:overworld','layout':self.layout}
        self.key=hashlib.sha256(json.dumps(self.scope,sort_keys=True).encode()).hexdigest()[:16]
        self.registry=self.root/'farms'/self.key/'registry.json';self.registry.parent.mkdir(parents=True)
        self.directory=self.root/'original';self.directory.mkdir();self.journal=self.directory/('wheat-farm-'+self.key+'.json')
        self.registry.write_text(json.dumps({'scope':self.scope,'world_session':'old','directory':str(self.directory)}))
        self.original={'schema':1,'scope':self.scope,'world_session':'old','complete':True,'pending':None,
            'seeds_before':24,'cells':{_key(pos):{'planted':True,'plant':{'original_receipt':'old-action'}} for pos in self.layout['cells']}}
        self.journal.write_text(json.dumps(self.original))
        self.profile=default_profile();self.profile.update(authorized=True,server='example.test',plant_registries=[str(self.registry)])
        self.state={'time':int(time.time()*1000),'connected':True,'server':'example.test','dimension':'minecraft:overworld','world_session':'new',
            'control_revision':2,'phase':'done','screen':'','manual_movement':False,'window_active':False,'health':20,'food':20,'under_water':False,
            'pos':[.5,110,.5],'supervision_lease':{},'menu':{'type':'InventoryMenu','cursor':{'count':0}},
            'idle_activity_protocol':1,'idle_activity':{'busy':False,'conflicts':[]},'material_task':{'occupied':False,'process_alive':False,'cancelling':False}}
        self.frames=0;self.calls=[];self.bad_field=False;outer=self
        class Reader:
            def request(self,op,**params):
                outer.calls.append((op,params));outer.frames+=1
                blocks=[row(outer.layout['center'],'Block{minecraft:water}[level=0]',False,True)]
                for pos in outer.layout['cells']:
                    blocks.append(row(pos,'Block{minecraft:farmland}[moisture=7]',False))
                    blocks.append(row([pos[0],pos[1]+1,pos[2]],'Block{minecraft:wheat}[age=7]',False))
                if outer.bad_field:blocks[2]['state']='Block{minecraft:potatoes}[age=7]'
                return deepcopy(outer.state)|{'time':outer.state['time']+outer.frames*250,'phase':'done','blocks':blocks,'scan_entities':[],
                    'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'}
        self.reader=Reader()
    def invoke(self,ack=True):
        return revalidate_fields(self.root,self.profile,acknowledge_existing_fields=ack,
            observer=lambda:deepcopy(self.state)|{'time':self.state['time']+self.frames*250},client_factory=lambda out:self.reader)
    def test_acknowledged_two_frames_preserve_original_bytes_and_rebind_only_connection(self):
        old_registry=self.registry.read_bytes();old_book=self.journal.read_bytes();result=self.invoke()
        self.assertEqual(('revalidated',1,0,False),(result['phase'],result['fields'],result['game_mutations_sent'],result['worker_started']))
        proof=json.loads(Path(result['evidence']).read_text());self.assertTrue(proof['committed'])
        for path,before in ((self.registry,old_registry),(self.journal,old_book)):
            saved=proof['originals'][str(path.resolve())];self.assertEqual(before,Path(saved['copy']).read_bytes())
            self.assertEqual(hashlib.sha256(before).hexdigest(),saved['sha256'])
        updated=json.loads(self.journal.read_text());self.assertEqual('new',updated['world_session']);self.assertEqual('old',updated['original_planting_world_session'])
        self.assertEqual(self.original['cells'],updated['cells']);self.assertEqual(24,updated['seeds_before']);self.assertTrue(updated['complete'])
        self.assertFalse(updated['connection_binding']['new_planting_receipt']);self.assertEqual(['scan','scan'],[op for op,_ in self.calls])
    def test_unacknowledged_unknown_plant_or_harvest_never_changes_original_binding(self):
        for fault in ('ack','plant','harvest'):
            with self.subTest(fault=fault):
                self.journal.write_text(json.dumps(self.original));active=self.registry.parent/'harvest-active.json';active.unlink(missing_ok=True)
                if fault=='plant':value=deepcopy(self.original);value['pending']={'operation':'plant'};self.journal.write_text(json.dumps(value))
                if fault=='harvest':
                    old=self.directory/'unknown-harvest.json';old.write_text('{"pending":{"operation":"harvest"}}');active.write_text(json.dumps({'journal':str(old)}))
                before=(self.registry.read_bytes(),self.journal.read_bytes());self.calls.clear()
                with self.assertRaises((ValueError,RuntimeError)):self.invoke(ack=fault!='ack')
                self.assertEqual(before,(self.registry.read_bytes(),self.journal.read_bytes()));self.assertEqual([],self.calls)
    def test_wrong_crop_or_missing_farmland_rejects_before_binding_writes(self):
        self.bad_field=True;before=(self.registry.read_bytes(),self.journal.read_bytes())
        with self.assertRaisesRegex(RuntimeError,'same crop'):self.invoke()
        self.assertEqual(before,(self.registry.read_bytes(),self.journal.read_bytes()))
    def test_completed_preparation_is_reobserved_and_retains_old_action_receipts(self):
        scope={'server':'example.test','dimension':'minecraft:overworld','center':[0,63,0],'radius':2}
        center={k:v for k,v in scope.items() if k!='radius'};home=self.root/'farm-preparation'/_identity(center);home.mkdir(parents=True)
        directory=self.root/'original-prep';directory.mkdir();registry=home/'registry.json';journal=directory/('farm-preparation-'+_identity(scope)+'.json')
        registry.write_text(json.dumps({'scope':scope,'world_session':'old','directory':str(directory)}))
        original={'scope':scope,'world_session':'old','complete':True,'pending':None,'actions':[{'old':'water-slot-ack'}]};journal.write_text(json.dumps(original));before=journal.read_bytes()
        result=self.invoke();updated=json.loads(journal.read_text());self.assertEqual('new',updated['world_session']);self.assertEqual(original['actions'],updated['actions'])
        proof=json.loads(Path(result['evidence']).read_text());self.assertEqual(before,Path(proof['originals'][str(journal.resolve())]['copy']).read_bytes())
        assert_preparation_resolved(self.root,self.state,self.request)
    def test_update_io_failure_rolls_back_exact_original_bytes(self):
        before=(self.registry.read_bytes(),self.journal.read_bytes())
        from idle_field_revalidation import write_json as write
        def fail(path,data):
            if Path(path).resolve()==self.registry.resolve():raise OSError('simulated registry write failure')
            return write(path,data)
        with patch('idle_field_revalidation.write_json',side_effect=fail):
            with self.assertRaises(OSError):self.invoke()
        self.assertEqual(before,(self.registry.read_bytes(),self.journal.read_bytes()))
    def test_completed_scan_status_lag_is_observed_without_replaying_scan(self):
        self.reader.last='owned-scan';seen=[]
        def observer():
            state=deepcopy(self.state)|{'time':self.state['time']+self.frames*250}
            if self.frames and not seen:
                seen.append(True);state.update(phase='running',last_request='owned-scan')
                state['idle_activity']={'busy':True,'conflicts':['scan']}
            return state
        result=revalidate_fields(self.root,self.profile,acknowledge_existing_fields=True,observer=observer,client_factory=lambda out:self.reader)
        self.assertEqual('revalidated',result['phase']);self.assertEqual(['scan','scan'],[op for op,_ in self.calls])
    def test_foreign_running_scan_is_not_adopted_and_binding_is_not_written(self):
        self.reader.last='owned-scan';before=(self.registry.read_bytes(),self.journal.read_bytes())
        def observer():
            state=deepcopy(self.state)|{'time':self.state['time']+self.frames*250}
            if self.frames:
                state.update(phase='running',last_request='foreign-scan');state['idle_activity']={'busy':True,'conflicts':['scan']}
            return state
        with self.assertRaisesRegex(RuntimeError,'did not settle'):
            revalidate_fields(self.root,self.profile,acknowledge_existing_fields=True,observer=observer,client_factory=lambda out:self.reader)
        self.assertEqual(before,(self.registry.read_bytes(),self.journal.read_bytes()))


if __name__=='__main__':unittest.main()
