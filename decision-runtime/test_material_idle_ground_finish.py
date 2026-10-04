"""Exact returned idle ground reads authorize a new ascent, never a fake walk."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import material_ground_finish as module
from material_client import Client,MaterialClient
from potato_farm import ENTITY_SCOPE
import test_material_ground_rebase as fixtures


class IdleGroundReadTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.GroundRebaseTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.c=fixture.c;self.c.last_owned_ground_walk=None
        self.before=deepcopy(fixture.landed)
        self.before.update(time=1000,last_request='closed-ender-menu',pos=[761021.5,64.875,797850.5],
            game_mode='survival',menu={'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}},
            projection_selection={'key':'map','min':[761024,64,797631],'max':[761151,64,797759]})
        self.params={'min':[761021,-64,797850],'max':[761021,319,797850],'details':True}
        self.receipt={**deepcopy(self.before),'time':1100,'id':self.c.last,'phase':'done',
            'scan_cells_read':384,'scan_total_cells':384,'scan_start_revision':42,'scan_end_revision':42,
            'blocks':[],'scan_entity_scope':ENTITY_SCOPE,'scan_entities':[]}
        self.receipt.pop('last_request')  # Native synchronous snapshots do not manufacture this status field.
        self.published={**deepcopy(self.before),'time':1200,'last_request':self.c.last}
        self.later={**deepcopy(self.published),'time':1700}
        self.actions=[]

    def capture(self):
        proof=module.idle_read_proof(self.c,'scan',self.params,self.before,self.receipt,self.published)
        self.assertIsNotNone(proof);self.c.last_owned_idle_ground_read=proof
        return proof

    def settle(self):
        self.capture();self.c.raw=lambda **kwargs:deepcopy(self.later)
        self.c.status=lambda **kwargs:self.fail('Idle settlement must only read raw without interface waiting')
        with patch('material_ground_finish.time.monotonic',side_effect=itertools.count(step=.1)),patch('material_ground_finish.time.sleep'):
            return module.settle(self.c,self.published)

    def install_requests(self,state):
        self.current=deepcopy(state)
        def raw(**kwargs):return deepcopy(self.current)
        def request(op,**params):
            self.actions.append((op,params));self.c.last='native-'+str(len(self.actions))
            self.current.update(last_request=self.c.last,phase='done')
            if op=='navigate':
                self.c.rev+=1;self.current['control_revision']=self.c.rev
                self.current['supervision_lease']['revision']=self.c.rev
                self.current.update(pos=params['target'],flight=True,on_ground=False,velocity=[0,0,0])
            if op=='material_job_park':
                self.assertIs(self.current['flight'],True)
                self.current['supervision_lease']['park_target']=params['park_target']
            self.c.last_terminal_evidence={'request_id':self.c.last,'op':op,'phase':'done','task_session':self.c.task,
                'world_session':self.c.world,'revision_after':self.c.rev}
            result={**deepcopy(self.current),'id':self.c.last,'phase':'done'}
            if op=='scan':
                total=1
                for a,b in zip(params['min'],params['max']):total*=b-a+1
                result.update(scan_cells_read=total,scan_total_cells=total,scan_start_revision=self.c.rev,
                    scan_end_revision=self.c.rev,scan_entity_scope=ENTITY_SCOPE,scan_entities=[],
                    blocks=[{'pos':[761021,64,797850],'state':'Block{minecraft:ender_chest}[facing=south,waterlogged=false]',
                             'solid':False,'fluid':False,'passable':False,'block_entity':True}])
            return result
        self.c.request=request;self.c.raw=raw

    def test_ender_close_then_exact_final_scan_new_ascent_and_accepted_park_without_walk(self):
        state=self.settle();proof=self.c.ground_finish_rebase['proof']
        self.assertFalse(proof['original_walk_performed']);self.assertNotIn('last_request',proof['returned_receipt'])
        self.assertEqual(self.receipt,proof['returned_receipt'])
        self.install_requests(state);result=module.ascend(self.c,state)
        self.assertEqual(['scan','scan','navigate','material_job_park'],[op for op,_ in self.actions])
        self.assertTrue(result['flight']);self.assertEqual(10,result['inventory'][5]['count'])
        self.assertEqual(result['supervision_lease']['park_target'],self.c.park_target)
        evidence=json.loads((self.c.out/'park-ground-settlement.json').read_text())
        self.assertEqual('known_owned_idle_ground_baseline',evidence['scope'])
        self.assertIsNone(evidence['walk_request_id']);self.assertFalse(evidence['original_walk_performed'])

    def test_returned_snapshot_none_is_bound_to_its_exact_cache_and_original_frames(self):
        self.receipt.pop('phase');self.receipt.pop('scan_cells_read');self.receipt.pop('scan_total_cells')
        self.c.last_terminal_evidence.update(op='snapshot',phase=None)
        proof=module.idle_read_proof(self.c,'snapshot',{},self.before,self.receipt,self.published)
        self.assertIsNotNone(proof);self.assertNotIn('phase',proof['returned_receipt'])
        self.c.last_terminal_evidence['request_id']='previous'
        self.assertIsNone(module.idle_read_proof(self.c,'snapshot',{},self.before,self.receipt,self.published))

    def test_same_returned_scan_pending_publication_waits_read_only_before_admission(self):
        pending={'id':self.c.last,'world_session':self.c.world,'control_revision':42,'reading_complete':False}
        self.receipt['pending_scan']=deepcopy(pending);self.published['pending_scan']=deepcopy(pending)
        self.capture();ready={**deepcopy(self.later),'pending_scan':None};stable={**deepcopy(ready),'time':2200}
        states=iter([ready,stable]);self.c.raw=lambda **kwargs:next(states)
        self.c.request=lambda *a,**k:self.fail('Publication wait may not dispatch a new read')
        with patch('material_ground_finish.time.monotonic',side_effect=itertools.count(step=.1)),patch('material_ground_finish.time.sleep'):
            result=module.settle(self.c,self.published)
        self.assertEqual(2200,result['time']);self.assertEqual(pending,self.c.ground_finish_rebase['proof']['returned_receipt']['pending_scan'])

    def test_missing_headers_menu_inventory_or_control_changes_cannot_mint_a_baseline(self):
        for change in ('uuid','key','inventory','mode','menu','cursor','flight','airborne','input','damage','busy','owner','partial','foreign_read','foreign_pending'):
            with self.subTest(change=change):
                self.setUp()
                if change=='uuid':self.receipt.pop('player_uuid')
                elif change=='key':self.receipt['projection_selection']={}
                elif change=='inventory':self.receipt['inventory'][5]['count']-=1
                elif change=='mode':self.receipt.pop('game_mode')
                elif change=='menu':self.receipt['menu']['type']='ChestMenu'
                elif change=='cursor':self.receipt['menu']['cursor']['count']=1
                elif change=='flight':self.receipt['flight']=True
                elif change=='airborne':self.receipt['on_ground']=False
                elif change=='input':self.receipt['movement_keys']['forward']=True
                elif change=='damage':self.receipt['recent_hurt_at']+=1
                elif change=='busy':self.receipt['professional_printer']={'enabled':True}
                elif change=='owner':self.receipt['supervision_lease']['id']='foreign'
                elif change=='partial':self.receipt['scan_cells_read']-=1
                elif change=='foreign_read':self.receipt['id']='foreign'
                else:self.receipt['pending_scan']={'id':'foreign','world_session':self.c.world,'control_revision':42}
                self.assertIsNone(module.idle_read_proof(self.c,'scan',self.params,self.before,self.receipt,self.published))

    def test_no_cache_legacy_walk_or_unknown_outcome_cannot_scan_or_rewrite_proofs(self):
        for case in ('missing','legacy','unknown','last_changed','drift'):
            with self.subTest(case=case):
                self.setUp();self.capture()
                if case=='missing':self.c.last_owned_idle_ground_read=None
                elif case=='legacy':self.c.last_owned_ground_walk={'op':'walk','phase':'done'}
                elif case=='unknown':self.c.unconfirmed_native_request={'request_id':self.c.last}
                elif case=='last_changed':self.c.last='unreturned'
                else:self.published['pos'][0]+=.1
                self.c.request=lambda *a,**k:self.fail('Unknown baseline may not dispatch')
                self.c.raw=lambda **k:deepcopy(self.later)
                with self.assertRaises(module.GroundFinishStop):module.settle(self.c,self.published)
                self.assertFalse((self.c.out/'park-ground-settlement.json').exists())

    def test_real_client_captures_only_exact_return_and_invalidates_before_unknown_dispatch(self):
        c=self.c;c.anchor=list(self.before['pos']);c.server=self.before['server'];c.owned=True
        current=deepcopy(self.before);c.status=lambda **kwargs:deepcopy(current)
        def raw(**kwargs):
            request=json.loads((c.root/'request.json').read_text())
            current.update(time=1200,id=request['id'],last_request=request['id'],phase='done')
            reply={**deepcopy(current),'phase':None}
            (c.root/('reply-'+request['id']+'.json')).write_text(json.dumps(reply))
            return deepcopy(current)
        c.raw=raw;Client.request(c,'snapshot')
        self.assertIsNotNone(c.last_owned_idle_ground_read)
        old=c.last_owned_idle_ground_read
        self.assertTrue((c.out/('idle-ground-read-'+old['request_id']+'.json')).exists())
        c.raw=lambda **kwargs:(_ for _ in ()).throw(RuntimeError('response unavailable'))
        with self.assertRaises(RuntimeError):Client.request(c,'snapshot')
        self.assertIsNone(c.last_owned_idle_ground_read)
        self.assertTrue((c.out/('idle-ground-read-'+old['request_id']+'.json')).exists())

    def test_read_baseline_takeoff_then_native_keep_parking_finishes_the_same_owner(self):
        state=self.settle();self.install_requests(state);c=self.c
        module.ascend(c,state);c.remote_finish='guard';c.owned_material_menu=None
        c.status=lambda **kwargs:deepcopy(self.current)
        c.owned_inventory_crafting=None
        def close_heartbeat():
            self.current['control_revision']+=1
            self.current['supervision_lease'].update(kind='parking',revision=self.current['control_revision'],
                parked_at=3000,park_target=c.park_target)
            self.current.update(time=3200,phase='parking')
            native={'lease':c.heartbeat.id,'job_session':c.task,'action':'KEEP_PVE_GUARD',
                'cause':'controller_finished','time':3000,'snapshot':deepcopy(self.current)}
            (c.root/('supervision-receipt-'+c.heartbeat.id+'.json')).write_text(json.dumps(native))
        c.heartbeat.close=close_heartbeat
        with patch('material_cleanup.run'),patch('craft_recovery.clear_owned_workbench'):
            c.finish()
        saved=json.loads((c.out/'stock-safety.json').read_text())
        self.assertIs(saved['native_receipt'],True)
        self.assertEqual('KEEP_PVE_GUARD',saved['action'])
        self.assertEqual('parking',saved['parking_confirmation']['supervision_lease']['kind'])
        self.assertEqual(10,saved['snapshot']['inventory'][5]['count'])


if __name__=='__main__':unittest.main()
