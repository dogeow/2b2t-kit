import contextlib, io, json, tempfile, time, unittest, zipfile
from pathlib import Path
from unittest.mock import patch

from status_summary import summarize


class StatusSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.game = Path(self.tmp.name)
        (self.game / 'mods').mkdir(); (self.game / 'config/twob2tkit/runtime').mkdir(parents=True)
        (self.game / 'config/twob2tkit/automation').mkdir(parents=True)

    def tearDown(self): self.tmp.cleanup()

    def install(self, kit='2026.11.27.2', engine='2026.11.27.1'):
        (self.game / 'mods' / f'twob2tkit-{kit}.jar').write_bytes(b'')
        with zipfile.ZipFile(self.game / 'config/twob2tkit/runtime/twob2tkit-engine.jar', 'w') as jar:
            jar.writestr('META-INF/MANIFEST.MF', f'Manifest-Version: 1.0\ntwob2tkit-Engine-Version: {engine}\n')

    def state(self, **extra):
        base = {'time': 1_000_000, 'connected': True, 'kit_version': '2026.11.27.2', 'runtime_version': '2026.11.27.1',
                'server': 'simpcraft.com', 'dimension': 'minecraft:overworld', 'pos': [1, 64, 2], 'health': 20.0,
                'food': 18, 'phase': 'running', 'op': 'navigate', 'detail': 'x', 'gravel': {}, 'craft_protocol': 3}
        base.update(extra); return base

    def test_connected_summary_keeps_only_decision_fields(self):
        self.install()
        out = summarize(self.game, self.state(), now=1_000.5)
        self.assertTrue(out['live']); self.assertEqual([], out['notes'])
        self.assertEqual({'server': 'simpcraft.com', 'dimension': 'minecraft:overworld', 'pos': [1, 64, 2],
                          'health': 20.0, 'food': 18}, out['player'])
        self.assertNotIn('craft_protocol', json.dumps(out))

    def test_recent_hurt_includes_seconds_ago(self):
        self.install()
        out = summarize(self.game, self.state(recent_attacker='僵尸', recent_hurt_at=990_000), now=1_000)
        self.assertEqual({'recent_attacker': '僵尸', 'recent_hurt_at': 990_000, 'seconds_ago': 10}, out['recent_hurt'])

    def test_material_task_states_get_the_right_next_step(self):
        self.install()
        paused = summarize(self.game, self.state(material_task={'id': 'm1', 'state': 'paused'}), now=1_000)
        self.assertIn('materials resume --job-id m1', ' '.join(paused['notes']))
        blocked = summarize(self.game, self.state(material_task={'id': 'm2', 'state': 'blocked', 'detail': '控制权已变化'}), now=1_000)
        self.assertIn('不能 resume', ' '.join(blocked['notes'])); self.assertEqual('控制权已变化', blocked['material_task']['detail'])
        running = summarize(self.game, self.state(material_task={'id': 'm3', 'state': 'gathering'}), now=1_000)
        self.assertEqual([], running['notes'])

    def test_reports_when_installed_versions_are_newer_than_running(self):
        self.install(kit='2026.11.27.2', engine='2026.11.27.1')
        out = summarize(self.game, self.state(kit_version='2026.11.26.1', runtime_version='2026.11.25.4'), now=1_000)
        self.assertIn('需要完整重启游戏', ' '.join(out['notes']))
        self.assertIn('/twob2tkit reload', ' '.join(out['notes']))

    def test_stale_file_extra_mod_jar_and_active_safety_hold_are_flagged(self):
        self.install(); (self.game / 'mods/twob2tkit-2026.11.26.1.jar').write_bytes(b'')
        out = summarize(self.game, self.state(safety_hold={'active': True, 'reason': '低血量紧急撤离', 'health': 9}), now=1_060)
        notes = ' '.join(out['notes'])
        self.assertFalse(out['live']); self.assertIn('已过期', notes); self.assertIn('2 个 Kit 主包', notes)
        self.assertEqual('低血量紧急撤离', out['safety_hold']['reason']); self.assertIn('安全锁', notes)
        self.assertIsNone(out['versions']['kit_installed'])

    def test_disconnected_state_has_no_player_block(self):
        self.install()
        out = summarize(self.game, self.state(connected=False, screen='DisconnectedScreen'), now=1_000)
        self.assertNotIn('player', out); self.assertEqual('DisconnectedScreen', out['screen'])

    def test_cli_status_is_read_only(self):
        import kit_cli
        self.install()
        (self.game / 'config/twob2tkit/automation/status.json').write_text(json.dumps(self.state(time=int(time.time() * 1000))))
        buf = io.StringIO()
        with patch('kit_cli.send') as send, contextlib.redirect_stdout(buf):
            self.assertEqual(0, kit_cli.main(['--game-dir', str(self.game), 'status']))
        send.assert_not_called()
        self.assertTrue(json.loads(buf.getvalue())['connected'])


if __name__ == '__main__': unittest.main()
