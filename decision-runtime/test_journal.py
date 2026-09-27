import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json


class JournalTest(unittest.TestCase):
    def test_replaces_whole_record_and_leaves_no_staging_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            write_json(path, {'stage': 'planned'})
            write_json(path, {'stage': '确认', 'count': 118})
            self.assertEqual({'stage': '确认', 'count': 118}, json.loads(path.read_text()))
            self.assertEqual([path], list(Path(folder).iterdir()))

    def test_failure_before_replace_preserves_last_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            write_json(path, {'stage': 'planned'})
            for operation in ('fsync', 'replace'):
                with self.subTest(operation=operation), patch('kit_runtime.journal.os.' + operation, side_effect=OSError('disk failure')):
                    with self.assertRaises(OSError):
                        write_json(path, {'stage': 'loaded'})
                self.assertEqual({'stage': 'planned'}, json.loads(path.read_text()))
                self.assertEqual([path], list(Path(folder).iterdir()))

    def test_invalid_record_does_not_truncate_existing_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            write_json(path, {'stage': 'loaded'})
            with self.assertRaises(TypeError):
                write_json(path, {'stage': object()})
            self.assertEqual({'stage': 'loaded'}, json.loads(path.read_text()))
            self.assertEqual([path], list(Path(folder).iterdir()))


if __name__ == '__main__':
    unittest.main()
