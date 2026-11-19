import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import experience_bottles
from kit_runtime.journal import write_json


class ExperienceBottlesTest(unittest.TestCase):
    def test_previous_pending_batch_prevents_new_intent_in_a_different_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "previous.json"
            write_json(old, {"complete": False, "pending": {"id": "original"}})
            write_json(root / "experience-bottle-active.json", {"journal": str(old)})
            with self.assertRaisesRegex(RuntimeError, "Previous bottle batch is unresolved"):
                experience_bottles.consume(SimpleNamespace(root=root), 1, root / "new")
            self.assertEqual(json.loads(old.read_text())["pending"], {"id": "original"})
            self.assertFalse((root / "experience-bottle-intent.json").exists())

    def test_admission_stops_before_dispatch_when_not_grounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = {"pos": [0, 64, 0], "inventory": [], "on_ground": False}
            with patch.object(experience_bottles, "wait_exact_idle_terminal", return_value=state):
                with self.assertRaisesRegex(RuntimeError, "Grounded guarded owner"):
                    experience_bottles.consume(SimpleNamespace(root=root), 1, root)
            self.assertFalse((root / "experience-bottle-intent.json").exists())
