import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_client import Client, MaterialClient, Handoff, credit_interface_pause


def state(**changes):
    result = dict(world_session='world', control_revision=40, connected=True,
                  screen='', manual_movement=False, health=20,
                  server='simpcraft.com', dimension='minecraft:overworld',
                  pos=[1, 2, 3], time=1, inventory=[],
                  interface_pause_protocol=1, interface_paused=False)
    result.update(changes)
    return result


class InterfacePauseTest(unittest.TestCase):
    def client(self, root, samples):
        client = Client.__new__(Client)
        client.root = client.out = root
        client.world = 'world'
        client.rev = 40
        client.anchor = [1, 2, 3]
        client.owned = False
        client.last = None
        client.raw = lambda **kwargs: next(samples)
        return client

    def test_status_waits_through_chat_sign_book_advancements_and_kit_then_resumes_same_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            seen = []
            samples = iter([state(screen=screen, interface_paused=True)
                            for screen in ('ChatScreen', 'SignEditScreen', 'BookEditScreen',
                                           'AdvancementsScreen', 'KitHudScreen')]
                           + [state()])
            client = self.client(Path(temp), samples)
            original = client.raw
            client.raw = lambda **kwargs: seen.append(original(**kwargs)) or seen[-1]
            with patch('material_client.time.sleep') as sleep:
                final = client.status()
            self.assertEqual(final['screen'], '')
            self.assertEqual(client.rev, 40)
            self.assertEqual(sleep.call_count, 5)
            self.assertEqual(len(seen), 6, 'Heartbeat-aware raw observation continues during every interface wait')
            self.assertFalse((client.root / 'request.json').exists())

    def test_actual_material_raw_touches_heartbeat_and_observes_health_during_ui_wait(self):
        with tempfile.TemporaryDirectory() as temp:
            client = MaterialClient.__new__(MaterialClient)
            client.root = client.out = Path(temp)
            client.world = 'world'; client.task = 'task'; client.rev = 40
            client.heartbeat = Mock(); client.job_progress = None
            samples = [state(screen='ChatScreen', interface_paused=True),
                       state(screen='BookEditScreen', interface_paused=True, health=19), state()]
            with patch.object(Client, 'raw', side_effect=samples), patch('material_client.time.sleep'):
                self.assertEqual(client.status()['screen'], '')
            self.assertEqual(client.heartbeat.touch.call_count, 3)
            self.assertIsNotNone(client.health_exit_evidence)
            client.heartbeat.close.assert_not_called()

    def test_real_manual_takeover_disconnect_and_foreign_revision_still_preempt_ui_wait(self):
        for changed in (dict(manual_movement=True), dict(connected=False),
                        dict(control_revision=41), dict(world_session='another')):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temp:
                client = self.client(Path(temp), iter([state(screen='ChatScreen', interface_paused=True, **changed)]))
                with self.assertRaises(Handoff):
                    client.status()

    def test_low_health_and_explicit_stop_do_not_wait_for_interface_close(self):
        with tempfile.TemporaryDirectory() as temp:
            client = self.client(Path(temp), iter([state(screen='ChatScreen', interface_paused=True, health=13)]))
            with patch('material_client.time.sleep') as sleep:
                self.assertEqual(client.status()['health'], 13)
            sleep.assert_not_called()
            class StopClient(Client):
                def raw(self):
                    current = state(screen='ChatScreen', interface_paused=True)
                    request = self.root / 'request.json'
                    if request.exists():
                        request = json.loads(request.read_text())
                        current.update(id=request['id'], last_request=request['id'], phase='stopped', control_revision=42)
                    return current
            stop = StopClient.__new__(StopClient)
            stop.__dict__.update(client.__dict__)
            del stop.raw
            self.assertEqual(stop.request('stop')['phase'], 'stopped')
            self.assertEqual(stop.rev, 42)

    def test_long_inflight_chat_preserves_the_one_request_and_credits_only_interface_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            elapsed = [0.0]
            class Fake(Client):
                def __init__(self):
                    self.root = self.out = root
                    self.world = 'world'; self.rev = 40; self.anchor = [1, 2, 3]
                    self.owned = False; self.last = None; self.polls = 0; self.ids = set()
                def raw(self):
                    current = state()
                    request = root / 'request.json'
                    if request.exists():
                        request = json.loads(request.read_text())
                        self.ids.add(request['id']); self.polls += 1; elapsed[0] += 2
                        current.update(id=request['id'], last_request=request['id'], control_revision=41,
                                       phase='running', screen='ChatScreen', interface_paused=True,
                                       guard_busy=True)
                        if self.polls == 152:
                            current.update(phase='done', screen='', interface_paused=False, guard_busy=False)
                    return current
            with patch('material_client.time.monotonic', side_effect=lambda: elapsed[0]), patch('material_client.time.sleep'):
                client = Fake()
                result = client.request('navigate', target=[4, 2, 3], seconds=1)
            self.assertEqual(result['phase'], 'done')
            self.assertEqual(client.rev, 41)
            self.assertEqual(client.polls, 152)
            self.assertEqual(len(client.ids), 1, 'Opening chat cannot cause a replay or second movement request')
            event = json.loads((root / 'events.jsonl').read_text())
            self.assertEqual(event['interface_pause_ms'], 302000)
            self.assertEqual(event['guard_pause_ms'], 0, 'UI and food/combat time must not receive duplicate credits')

    def test_container_controls_and_older_hosts_never_gain_passive_screen_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            for sample in (state(screen='MerchantScreen'),
                           state(screen='ChatScreen', interface_pause_protocol=0, interface_paused=True)):
                client = self.client(Path(temp), iter([sample]))
                with self.assertRaises(Handoff):client.status()
        self.assertEqual((100, 0), credit_interface_pause(100, 0, 20, state(screen='InventoryScreen')))
        self.assertEqual((500, 400), credit_interface_pause(100, 0, 400, state(screen='ChatScreen', interface_paused=True)))


if __name__ == '__main__':
    unittest.main()
