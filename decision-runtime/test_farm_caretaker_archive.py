"""A manual abandonment never turns unknown game results into a successful receipt."""
from copy import deepcopy
import contextlib
import fcntl
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from farm_caretaker import Caretaker, CaretakerPaused
from farm_caretaker_archive import archive_pending
from farm_caretaker_cli import main
from test_farm_caretaker import Fixture, profile, state


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.game=Path(self.temp.name);self.root=self.game/'config/twob2tkit/automation'
        self.c=Caretaker(self.root,profile());self.cycle=self.c.out/'cycle-000001';self.stage=self.cycle/'harvest_store'
        self.c.lock_path.touch()  # A formerly started worker creates this persistent flock file.
        self.stage.mkdir(parents=True)
        self.c.book.update(cycle=1,stage='harvest_store',world_session='w',enabled=False,paused=True,reason='CONTROL_CHANGED',
            pending={'stage':'harvest_store','directory':str(self.stage)},
            current_cycle={'id':1,'directory':str(self.cycle),'world_session':'w','baseline':{'minecraft:potato':134},'receipts':{}})
        self.c.save()
        self.stage_path=self.stage/'stage.json'
        self.stage_path.write_text(json.dumps({'world_session':'w','cycle_id':1,'stage':'harvest_store','receipts':[],
            'pending':{'operation':'fetch','before_time':800,'params':{'targets':{'minecraft:potato':5}}}}))
        backend=self.cycle/'backend/control-002';backend.mkdir(parents=True)
        (backend/'events.jsonl').write_text(json.dumps({'op':'material_session','request_id':'materials-original',
            'params':{'supervision_lease':'jev-owner-original'},'phase':'done'})+'\n')
        (self.root/'supervision-receipt-jev-owner-original.json').write_bytes(b'{"action":"KEEP_PVE_GUARD","confirmed":false}\n')
        (self.cycle/'binary-evidence.bin').write_bytes(b'\x00\xff original evidence')
        self.current=state();self.current.update(time=1000,world_session='new-world',phase='stopped',navigating=False,
            material_task={'process_alive':False,'occupied':False,'cancelling':False},
            menu={'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}},
            inventory=[{'slot':0,'item':'minecraft:potato','count':17}])
        self.write_current()
        self.profile_file=self.game/'profile.json';self.profile_file.write_text(json.dumps(profile()))

    def write_current(self):(self.root/'status.json').write_text(json.dumps(self.current))
    def archive(self,**kwargs):
        return archive_pending(self.root,profile(),acknowledge_unknown_outcome=True,now_ms=1000,**kwargs)
    def files(self):return {str(p.relative_to(self.game)):p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def test_manual_archive_preserves_original_book_cycle_intent_and_native_evidence_exactly(self):
        original_book=self.c.path.read_bytes();original_files={p:p.read_bytes() for p in self.cycle.rglob('*') if p.is_file()}
        native=self.root/'supervision-receipt-jev-owner-original.json';native_before=native.read_bytes()
        result=self.archive();dest=Path(result['archive']);record=json.loads((dest/'archive.json').read_text())
        self.assertEqual(('archived','abandoned','outcome_unknown',2,False,0),
            tuple(result[k] for k in ('phase','state','outcome','next_cycle','worker_started','game_actions_sent')))
        self.assertEqual(original_book,(dest/'original-caretaker.json').read_bytes())
        for source,data in original_files.items():
            self.assertEqual(data,source.read_bytes());self.assertEqual(data,(dest/'cycle'/source.relative_to(self.cycle)).read_bytes())
        self.assertEqual(native_before,native.read_bytes());self.assertEqual(native_before,(dest/'native-evidence'/native.name).read_bytes())
        self.assertIn('reply-materials-original.json',record['missing_native_evidence'])
        self.assertEqual('WORLD_SESSION_ENDED',record['termination_proof']['termination_basis'])
        self.assertTrue(record['committed']);self.assertEqual('fetch',json.loads((dest/'cycle/harvest_store/stage.json').read_text())['pending']['operation'])
        saved=json.loads(self.c.path.read_text());self.assertIsNone(saved['pending']);self.assertIsNone(saved['current_cycle'])
        self.assertEqual((1,False,True),(saved['cycle'],saved['enabled'],saved['paused']))
        self.assertEqual('outcome_unknown',saved['archived_cycles'][0]['outcome'])

    def test_other_unknown_actions_are_abandoned_without_altering_inner_pending_or_claiming_success(self):
        for operation in ('harvest','breed','slaughter_attack','smelt','depot_exchange'):
            with self.subTest(operation=operation):
                self.c.save();record=json.loads(self.stage_path.read_text());record['pending']['operation']=operation
                self.stage_path.write_text(json.dumps(record));inner=self.stage/'inner.json';inner.write_text('{"pending":{"operation":"sent"},"complete":false}\n')
                before=self.stage_path.read_bytes();inner_before=inner.read_bytes();result=self.archive();dest=Path(result['archive'])
                self.assertEqual('outcome_unknown',result['outcome']);self.assertEqual(before,self.stage_path.read_bytes())
                self.assertEqual(inner_before,(dest/'cycle/harvest_store/inner.json').read_bytes())
                self.assertIsNotNone(json.loads((dest/'original-caretaker.json').read_text())['pending'])

    def test_confirmation_flag_is_required_before_any_new_file_or_coordinator(self):
        before=self.files()
        with self.assertRaisesRegex(ValueError,'acknowledge-unknown-outcome'):archive_pending(self.root,profile(),now_ms=1000)
        self.assertEqual(before,self.files())
        with patch('farm_caretaker_cli.Caretaker',side_effect=AssertionError('No coordinator')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code=main(['--game-dir',str(self.game),'--profile',str(self.profile_file),'archive-pending'])
        self.assertEqual(2,code);self.assertIn('acknowledge-unknown-outcome',json.loads(output.getvalue())['detail'])
        self.assertEqual(before,self.files())

    def test_real_running_worker_flock_rejects_without_mutating_originals(self):
        before=self.files()
        with self.c.lock_path.open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'工作锁'):self.archive()
        self.assertEqual(before,self.files())

    def test_cursor_live_job_material_lease_and_unconsumed_request_each_block_archive(self):
        cases=[{'menu':{'type':'InventoryMenu','cursor':{'item':'minecraft:potato','count':1}}},
               {'navigating':True},{'phase':'running'},{'guard_busy':True},
               {'material_task':{'process_alive':True,'occupied':True,'cancelling':False}},
               {'supervision_lease':{'kind':'materials','world_session':'new-world','revision':1}},
               {'safety_hold':{'active':True,'escaping':True}}]
        original=deepcopy(self.current)
        for change in cases:
            with self.subTest(change=change):
                self.current={**deepcopy(original),**change};self.write_current();before=self.files()
                with self.assertRaises(RuntimeError):self.archive()
                self.assertEqual(before,self.files())
        self.current=original;self.write_current()
        (self.root/'request.json').write_text(json.dumps({'id':'materials-unsent','world_session':'new-world','expires_at':3000}))
        before=self.files()
        with self.assertRaisesRegex(RuntimeError,'尚未消费'):self.archive()
        self.assertEqual(before,self.files())

    def test_same_world_requires_idle_native_state_and_no_work_lease(self):
        self.current['world_session']='w';self.write_current();result=self.archive()
        record=json.loads((Path(result['archive'])/'archive.json').read_text())
        self.assertEqual('NATIVE_IDLE_WITHOUT_WORK_LEASE',record['termination_proof']['termination_basis'])

    def test_safety_holds_remain_byte_identical_and_still_block_a_new_worker(self):
        holds={'assistant-control-hold.json':{'active':True},'safety-hold.json':{'active':True},
               'material-health-hold.json':{'active':True,'time':500}}
        for name,data in holds.items():(self.root/name).write_text(json.dumps(data))
        before={name:(self.root/name).read_bytes() for name in holds}
        self.archive()
        for name,data in before.items():self.assertEqual(data,(self.root/name).read_bytes())
        c=Caretaker(self.root,profile(),observer=lambda:deepcopy(self.current),adapter_factory=lambda *a:None)
        with self.assertRaises(CaretakerPaused):c.resume()
        self.assertEqual('SAFETY_HOLD',c.book['reason'])
        self.assertIsNone(c.book['current_cycle'])

    def test_next_explicit_start_uses_continuous_cycle_number_and_fresh_inventory(self):
        self.archive();fixture=Fixture();fixture.state=deepcopy(self.current)
        c=Caretaker(self.root,profile(),observer=lambda:deepcopy(fixture.state),adapter_factory=fixture.factory,clock=lambda:20)
        c.resume();c.tick();self.assertEqual(2,c.book['cycle']);self.assertEqual(2,c.book['current_cycle']['id'])
        self.assertEqual(17,c.book['current_cycle']['baseline']['minecraft:potato'])
        self.assertEqual('cycle-000002',Path(c.book['current_cycle']['directory']).name)
        self.assertTrue(json.loads(self.stage_path.read_text())['pending'])

    def test_confirmed_hash_cannot_archive_a_newer_book(self):
        digest=hashlib.sha256(self.c.path.read_bytes()).hexdigest();self.c.book['reason']='NEW_REASON';self.c.save();before=self.files()
        with self.assertRaisesRegex(RuntimeError,'确认后'):self.archive(expected_pending_sha256=digest)
        self.assertEqual(before,self.files())

    def test_state_change_during_preservation_leaves_original_pointer_pending(self):
        from farm_caretaker_archive import write_json as real_write
        before=self.c.path.read_bytes()
        def changed(path,data):
            real_write(path,data)
            if Path(path).name=='archive.json':
                self.current['inventory'][0]['count']=18;self.write_current()
        with patch('farm_caretaker_archive.write_json',side_effect=changed):
            with self.assertRaisesRegex(RuntimeError,'状态或原周期改变'):self.archive()
        self.assertEqual(before,self.c.path.read_bytes());self.assertTrue(json.loads(self.c.path.read_text())['pending'])

    def test_cli_archive_branch_uses_explicit_confirmation_and_never_constructs_worker(self):
        self.current['time']=int(time.time()*1000);self.write_current()
        with patch('farm_caretaker_cli.Caretaker',side_effect=AssertionError('No coordinator')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code=main(['--game-dir',str(self.game),'--profile',str(self.profile_file),'archive-pending','--acknowledge-unknown-outcome'])
        result=json.loads(output.getvalue());self.assertEqual(0,code);self.assertFalse(result['worker_started']);self.assertEqual('outcome_unknown',result['outcome'])


if __name__=='__main__':unittest.main()
