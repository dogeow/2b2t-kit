import copy
import json
from pathlib import Path
import tempfile
import unittest

from material_jobs.progress import MaterialProgress, quantities_summary


class MaterialProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.request = {'id': 'job', 'mode': 'projection', 'targets': {}, 'context': {
            'world_session': 'w', 'server': 'simpcraft.com', 'dimension': 'minecraft:overworld'}}
        self.status = {'id': 'job', 'state': 'gathering', 'terminal': False,
                       'native_task_session': 'task', 'done': 8966, 'total': 16512,
                       'phase': '采集加工材料', 'updated_at': 10000}
        self.inflight = {'job_id': 'job', 'operation': 'run_pipeline',
                         'args': ['minecraft:mud_bricks', 128, 'absolute_backpack_total'],
                         'output_targets': {'minecraft:mud_bricks': 128}}
        self.state = {'connected': True, 'world_session': 'w', 'server': 'simpcraft.com:25565',
                      'dimension': 'minecraft:overworld', 'manual_movement': False,
                      'control_revision': 7, 'time': 10000,
                      'supervision_lease': {'kind': 'materials', 'world_session': 'w',
                                            'job_session': 'task', 'revision': 7},
                      'inventory': [{'slot': 0, 'item': 'minecraft:mud_bricks', 'count': 26}],
                      'warehouse_stock_hint': {'minecraft:mud_bricks': 900}}
        self.names = lambda item: {'minecraft:mud_bricks': '泥砖', 'minecraft:wheat': '小麦'}.get(item, item)
        self.publisher = MaterialProgress(self.request, self.root, self.root, name=self.names)
        self.write()

    def write(self):
        (self.root / 'status.json').write_text(json.dumps(self.status))
        (self.root / 'inflight.json').write_text(json.dumps(self.inflight))

    def read(self):
        return json.loads((self.root / 'job-progress.json').read_text())

    def test_pipeline_shows_carried_output_and_separate_verified_map_count(self):
        self.publisher.publish(self.state, now=10)
        p = self.read()
        self.assertEqual(('制作 泥砖', 26, 128, '地图 8966/16512'),
                         (p['title'], p['done'], p['total'], p['phase']))
        self.assertEqual('task', p['task_session'])
        self.assertEqual(7, p['control_revision'])

    def test_inventory_can_fall_and_does_not_accumulate_planned_or_depot_stock(self):
        self.publisher.publish(self.state, now=10)
        self.state['inventory'][0]['count'] = 6
        self.state['inventory'].append({'slot': 40, 'item': 'minecraft:mud_bricks', 'count': 64})
        self.publisher.publish(self.state, now=10.3)
        self.assertEqual(6, self.read()['done'])

    def test_revision_tracks_same_owned_lease_during_native_actions(self):
        self.publisher.publish(self.state, now=10)
        self.state['control_revision'] = 8
        self.state['supervision_lease']['revision'] = 8
        self.publisher.publish(self.state, now=10.3)
        self.assertEqual(8, self.read()['control_revision'])

    def test_disconnected_manual_wrong_task_world_stale_or_terminal_hide(self):
        cases = [('connected', False), ('manual_movement', True), ('world_session', 'other'),
                 ('time', 2000), ('supervision_lease', {'kind': 'materials', 'world_session': 'w',
                    'job_session': 'other', 'revision': 7}),
                 ('supervision_lease', {'kind': 'parking', 'world_session': 'w',
                    'job_session': 'task', 'revision': 7})]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.publisher.publish(self.state, now=10)
                changed = copy.deepcopy(self.state)
                changed[key] = value
                self.publisher.publish(changed, now=10.3)
                self.assertFalse((self.root / 'job-progress.json').exists())
                self.publisher.last_read = 0
        for key, value in [('terminal', True), ('state', 'paused'), ('id', 'other'), ('updated_at', 0)]:
            with self.subTest(status=key):
                self.publisher.publish(self.state, now=10)
                old = self.status[key]
                self.status[key] = value
                self.write()
                self.publisher.publish(self.state, now=10.3)
                self.assertFalse((self.root / 'job-progress.json').exists())
                self.status[key] = old
                self.write()
                self.publisher.last_read = 0

    def test_build_and_foreign_pending_use_parent_count(self):
        for pending in [None, {'job_id': 'other', **{k: v for k, v in self.inflight.items() if k != 'job_id'}}]:
            self.assertEqual(('地图施工', 8966, 16512, '采集加工材料'),
                quantities_summary(self.request, self.status, pending, self.state, self.names))

    def test_depot_pipeline_never_credits_carried_stock_as_depot_progress(self):
        self.inflight['args'][2] = 'approved_depot_total'
        self.assertEqual('地图施工', quantities_summary(
            self.request, self.status, self.inflight, self.state, self.names)[0])

    def test_item_target_and_finish_do_not_touch_task_journal(self):
        self.request.update(mode='item', targets={'minecraft:wheat': 50})
        self.state['inventory'] = [{'slot': 0, 'item': 'minecraft:wheat', 'count': 10}]
        (self.root / 'inflight.json').unlink()
        original = (self.root / 'status.json').read_bytes()
        self.publisher.publish(self.state, now=10)
        self.assertEqual(('获取 小麦', 10, 50), (self.read()['title'], self.read()['done'], self.read()['total']))
        self.publisher.close()
        self.assertFalse((self.root / 'job-progress.json').exists())
        self.assertEqual(original, (self.root / 'status.json').read_bytes())

    def test_malformed_optional_display_cannot_interrupt_material_work(self):
        (self.root / 'inflight.json').write_text('{')
        self.publisher.publish(self.state, now=10)
        self.assertFalse((self.root / 'job-progress.json').exists())


if __name__ == '__main__':
    unittest.main()
