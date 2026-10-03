"""Unknown inventory actions remain pending even when old navigation was stopped."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from farm_caretaker import Caretaker
from farm_caretaker_cli import main
from farm_caretaker_review import inspect_pending
from test_farm_caretaker import profile, state


class PendingReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name); self.root = self.game / 'config/twob2tkit/automation'
        self.c = Caretaker(self.root, profile())
        self.cycle = self.c.out / 'cycle-000001'; self.stage_dir = self.cycle / 'harvest_store'
        self.stage_dir.mkdir(parents=True)
        self.stage_path = self.stage_dir / 'stage.json'
        self.stage = {'world_session':'w', 'cycle_id':1, 'stage':'harvest_store', 'receipts':[],
                      'pending':{'operation':'fetch', 'before_time':1000, 'params':{'targets':{'minecraft:potato':5}}}}
        self.stage_path.write_text(json.dumps(self.stage))
        self.c.book.update(cycle=1, stage='harvest_store', world_session='w', reason='CONTROL_CHANGED',
            pending={'stage':'harvest_store','directory':str(self.stage_dir)},
            current_cycle={'id':1,'directory':str(self.cycle),'world_session':'w','baseline':{'minecraft:potato':134}})
        self.c.save()
        self.current = state(); self.current['time'] = 1000
        (self.root / 'status.json').write_text(json.dumps(self.current))
        self.p = self.game / 'profile.json'; self.p.write_text(json.dumps(profile()))

    def snapshot(self):
        return {str(p):p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def test_old_pending_without_exact_dispatch_and_action_baseline_is_never_adopted(self):
        backend = self.cycle / 'backend/control-002'; backend.mkdir(parents=True)
        (backend / 'events.jsonl').write_text(json.dumps({'op':'scan','phase':'done'})+'\n')
        (self.root / 'supervision-receipt-old.json').write_text(json.dumps({
            'action':'KEEP_PVE_GUARD','snapshot':{'material_air_navigation':{'outcome':'stopped'}}}))
        before = self.snapshot()
        with patch.object(Caretaker, '_observe', side_effect=AssertionError('No game client')):
            result = inspect_pending(self.root, profile(), now_ms=1000)
        self.assertFalse(result['can_resume']); self.assertFalse(result['writes_performed'])
        self.assertEqual('fetch',result['operation']); self.assertEqual(str(self.stage_path),result['stage_journal'])
        self.assertEqual({'MISSING_ACTION_BASELINE','UNCONFIRMED_CHILD_DISPATCH'}, {c['code'] for c in result['checks']})
        self.assertNotIn('inventory_before',result)
        self.assertEqual(self.stage['pending'],result['original_intent'])
        self.assertEqual(before,self.snapshot())

    def test_changed_world_and_inventory_remain_explicit_blockers(self):
        self.stage['pending']['before_counts'] = {'minecraft:potato':4}
        self.stage_path.write_text(json.dumps(self.stage))
        self.current.update(world_session='new-world',inventory=[{'slot':0,'item':'minecraft:potato','count':8}])
        (self.root / 'status.json').write_text(json.dumps(self.current))
        before=self.snapshot(); result=inspect_pending(self.root,profile(),now_ms=1000)
        codes={c['code'] for c in result['checks']}
        self.assertTrue({'WORLD_SCOPE_CHANGED','INVENTORY_CHANGED'} <= codes)
        self.assertFalse(result['can_resume']);self.assertEqual(before,self.snapshot())

    def test_same_counts_do_not_turn_unknown_fetch_into_success(self):
        self.stage['pending']['before_counts']={'minecraft:potato':4}
        self.stage_path.write_text(json.dumps(self.stage))
        result=inspect_pending(self.root,profile(),now_ms=1000)
        self.assertFalse(result['can_resume'])
        self.assertIn('UNCONFIRMED_CHILD_DISPATCH',[c['code'] for c in result['checks']])

    def test_out_and_stage_path_cannot_select_new_journal_or_external_record(self):
        with self.assertRaisesRegex(ValueError,'原记录目录'):inspect_pending(self.root,profile(),self.game/'other')
        self.c.book['pending']['directory']=str(self.game/'outside');self.c.save()
        with self.assertRaisesRegex(ValueError,'同一周期'):inspect_pending(self.root,profile())

    def test_cli_review_never_constructs_a_coordinator_or_changes_files(self):
        before=self.snapshot()
        with patch('farm_caretaker_cli.Caretaker',side_effect=AssertionError('Review must not construct or register')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code=main(['--game-dir',str(self.game),'--profile',str(self.p),'inspect-pending'])
        self.assertEqual(0,code);self.assertFalse(json.loads(output.getvalue())['can_resume'])
        self.assertEqual(before,self.snapshot())

    def test_absent_registration_is_read_only_and_reports_no_retry_permission(self):
        self.c.path.parent.parent.joinpath('registry.json').unlink();before=self.snapshot()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code=main(['--game-dir',str(self.game),'--profile',str(self.p),'inspect-pending'])
        self.assertEqual(2,code);self.assertEqual('waiting',json.loads(output.getvalue())['phase'])
        self.assertEqual(before,self.snapshot())


if __name__=='__main__':unittest.main()
