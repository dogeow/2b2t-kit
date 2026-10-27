from email.message import Message
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ui
from minecraft_harness import MinecraftAdapter, RULES, editor_prompt


class UITest(unittest.TestCase):
    def test_user_prompt_reaches_task_and_cannot_change_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / 'snapshot.json'
            snapshot.write_text('{}')
            prompt = '检查三名村民和床位，给出下一步。'
            adapter = MinecraftAdapter(root / 'run', snapshot, prompt)
            self.assertEqual(adapter.task_prompt('iron-farm'), prompt)
            with self.assertRaisesRegex(ValueError, 'prompt changed'):
                MinecraftAdapter(root / 'run', snapshot, '不同任务')

    def test_actual_prompt_contains_fixed_rules_and_visible_context(self):
        prompt = editor_prompt('比较诊断方案', {'context/task.md': '检查刷铁机',
                                              'harness/scripts/policy.py': 'CHECKS=["water"]'})
        self.assertIn(RULES, prompt)
        self.assertIn('比较诊断方案', prompt)
        self.assertIn('policy.py', prompt)
        self.assertIn('water', prompt)

    def test_model_requires_upload_consent_before_creating_job(self):
        with patch('ui.threading.Thread') as thread:
            with self.assertRaisesRegex(ValueError, '允许'):
                ui.start_job({'mode': 'model', 'source': 'saved', 'prompt': '检查刷铁机', 'allow_upload': False})
            thread.assert_not_called()

    def test_cross_origin_post_rejected_before_starting_any_job(self):
        handler = ui.Handler.__new__(ui.Handler)
        handler.server = SimpleNamespace(server_port=18768)
        handler.headers = Message()
        handler.headers['Host'] = '127.0.0.1:18768'
        handler.headers['Origin'] = 'https://unrelated.example'
        handler.headers['X-Harness-Token'] = ui.TOKEN
        with patch.object(handler, 'send') as send, patch('ui.start_job') as start:
            handler.do_POST()
            self.assertEqual(send.call_args.args[0], 403)
            start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
