import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from farm_preparation import _identity,_scope
from potato_farm import plan
from registered_farm_restoration import create_intent,bind_completed_planting,reconcile_confirmed_center_mine


class RestorationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.state={'server':'example.test','dimension':'minecraft:overworld','world_session':'new','connected':True}
        self.request={'authorized':True,'center':[10,64,10],'radius':2,'crop':'wheat'}
        self.scope={'server':'example.test','dimension':'minecraft:overworld','layout':plan(self.request)}
        key=hashlib.sha256(json.dumps(self.scope,sort_keys=True).encode()).hexdigest()[:16]
        self.registry=self.root/'farms'/key/'registry.json';self.registry.parent.mkdir(parents=True)
        self.old=self.root/'old';self.old.mkdir();self.plant=self.old/('wheat-farm-'+key+'.json')
        self.plant.write_text(json.dumps({'scope':self.scope,'world_session':'old','complete':True,'pending':None}))
        self.registry.write_text(json.dumps({'scope':self.scope,'world_session':'old','directory':str(self.old)}))
        prep=_scope(self.state,self.request);pkey=_identity({k:v for k,v in prep.items()if k!='radius'})
        self.prep_registry=self.root/'farm-preparation'/pkey/'registry.json';self.prep_registry.parent.mkdir(parents=True)
        self.prep=self.old/('farm-preparation-'+_identity(prep)+'.json')
        self.prep.write_text(json.dumps({'scope':prep,'world_session':'old','complete':True,'pending':None}))
        self.prep_registry.write_text(json.dumps({'scope':prep,'world_session':'old','directory':str(self.old)}))
        (self.registry.parent/'harvest-active.json').write_text('{"journal":"old-unknown-harvest"}')

    def test_fresh_intent_preserves_original_mutation_and_unknown_harvest_bytes(self):
        before={p:p.read_bytes()for p in [self.plant,self.prep,self.registry.parent/'harvest-active.json']}
        request,directory=create_intent(self.root,self.registry,self.state,self.root/'restore',water_source=[15,62,12])
        self.assertEqual(request['center'],[10,64,10]);self.assertEqual(request['radius'],2)
        for p,data in before.items():self.assertEqual(p.read_bytes(),data)
        with self.assertRaises(ValueError):bind_completed_planting(self.root,self.registry,self.state,self.root/'restore')

    def test_unresolved_original_work_is_rejected_before_registry_changes(self):
        data=json.loads(self.prep.read_text());data['pending']={'operation':'bucket_fill'};self.prep.write_text(json.dumps(data))
        before=self.prep_registry.read_bytes()
        with self.assertRaises(ValueError):create_intent(self.root,self.registry,self.state,self.root/'restore',water_source=[15,62,12])
        self.assertEqual(self.prep_registry.read_bytes(),before);self.assertFalse((self.root/'restore').exists())

    def test_center_mine_requires_original_server_ack_and_distinct_empty_frames(self):
        center=[10,64,10];params={'pos':center,'expected_state':'Block{minecraft:grass_block}[snowy=false]'}
        reply={'id':'mine-one','world_session':'new','time':50,'phase':'done','server_confirmed':True,
               'outcome_pending':False,'native_sequence':3,'server_ack_sequence':3,
               'server_update_seen':True,'server_observed_state':'Block{minecraft:air}',
               'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack','mining_target':center}
        book={'scope':_scope(self.state,self.request),'world_session':'new','actions':[],
              'pending':{'op':'mine_block','stage':'returned_pending_proof','params':params,'receipt':reply}}
        journal=self.root/'center.json';journal.write_text(json.dumps(book));before=journal.read_bytes()
        def frame(at):
            return {'phase':'done','world_session':'new','control_revision':7,'time':at,
                'scan_scope':'loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot',
                'scan_coherent':True,'scan_started_at':at,'scan_ended_at':at,'scan_start_tick':10,
                'scan_end_tick':10,'scan_elapsed_ticks':0,'scan_start_revision':7,'scan_end_revision':7,
                'scan_cells_read':245,'scan_total_cells':245,'blocks':[],
                'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd',
                'scan_entities':[]}
        state={**self.state,'control_revision':7};scans=[frame(100),frame(101)]
        book['pending']['receipt']['server_confirmed']=False;journal.write_text(json.dumps(book))
        with self.assertRaises(ValueError):reconcile_confirmed_center_mine(journal,state,scans)
        book['pending']['receipt']['server_confirmed']=True;journal.write_bytes(before)
        proof=reconcile_confirmed_center_mine(journal,state,scans)
        self.assertFalse(proof['new_mining_sent']);self.assertIsNone(json.loads(journal.read_text())['pending'])
        self.assertEqual((journal.parent/'reconciliation'/('before-'+hashlib.sha256(before).hexdigest()[:16]+'.json')).read_bytes(),before)


if __name__=='__main__':unittest.main()
