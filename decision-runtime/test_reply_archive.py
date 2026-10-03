import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reply_archive import archive, restore, pack


class ReplyArchiveTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.now = 2000000

    def reply(self, rid='old', **extra):
        p = self.root / ('reply-' + rid + '.json')
        p.write_text(json.dumps({'id': rid, 'blocks': [{'pos': [1,2,3], 'state': 'Block{minecraft:stone}'}], **extra}))
        os.utime(p, (self.now - 10 * 86400,) * 2)
        return p

    def test_dry_run_does_not_remove_and_verified_archive_restores_exact_bytes(self):
        p = self.reply(); raw = p.read_bytes()
        self.assertEqual(1, archive(self.root, now=self.now)['files'])
        self.assertTrue(p.exists()); self.assertFalse(p.with_suffix('.json.gz').exists())
        result = archive(self.root, apply=True, now=self.now)
        self.assertEqual(1, result['files']); self.assertFalse(p.exists())
        self.assertEqual(raw, gzip.decompress(p.with_suffix('.json.gz').read_bytes()))
        restore(self.root, p.name)
        self.assertEqual(raw, p.read_bytes())
        with self.assertRaises(ValueError): restore(self.root, p.name)

    def test_current_pending_and_completed_referenced_receipts_remain_plain(self):
        for rid in ('current', 'pending', 'complete'): self.reply(rid)
        (self.root/'status.json').write_text(json.dumps({'last_request':'current'}))
        child=self.root/'jobs';child.mkdir()
        (child/'journal.json').write_text(json.dumps({'pending':{'request_id':'pending'}, 'receipt':'reply-complete.json'}))
        self.assertEqual(0, archive(self.root, apply=True, now=self.now)['files'])
        self.assertEqual(3, len(list(self.root.glob('reply-*.json'))))

    def test_mutation_unknown_malformed_and_recent_records_are_never_archived(self):
        self.reply('mutate', phase='done'); self.reply('unknown', pending=True)
        self.reply('incomplete', scan_complete=False)
        recent=self.reply('recent');os.utime(recent,(self.now,)*2)
        (self.root/'reply-invalid.json').write_text('{')
        self.assertEqual(0, archive(self.root, apply=True, now=self.now)['files'])

    def test_changed_original_is_retained_and_no_archive_committed(self):
        p=self.reply();raw=p.read_bytes();metadata=p.stat()
        p.write_bytes(raw+b' ')
        with self.assertRaises(ValueError):pack(p,raw,metadata)
        self.assertTrue(p.exists());self.assertFalse(p.with_suffix('.json.gz').exists())
        self.assertFalse(list(self.root.glob('.reply-archive-*')))

    def test_verification_failure_retains_original(self):
        p=self.reply();raw=p.read_bytes();metadata=p.stat()
        with patch('reply_archive.digest',side_effect=['different','hash']):
            with self.assertRaises(ValueError):pack(p,raw,metadata)
        self.assertEqual(raw,p.read_bytes());self.assertFalse(p.with_suffix('.json.gz').exists())

    def test_kit_cli_routes_offline_without_game_state_or_actions(self):
        import kit_cli
        with patch('reply_archive.main',return_value=0) as call:
            self.assertEqual(0,kit_cli.main(['--game-dir','/game','replies','--days','7','--apply']))
        self.assertEqual(['--root','/game/config/twob2tkit/automation','--days','7','--max-files','2000','--apply'],call.call_args.args[0])

    def test_io_failure_and_batch_limit_are_safe(self):
        p=self.reply('a');self.reply('b')
        with patch('reply_archive.gzip.GzipFile',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):archive(self.root,apply=True,now=self.now)
        self.assertTrue(p.exists())
        self.assertEqual(1,archive(self.root,apply=True,max_files=1,now=self.now)['files'])
        self.assertEqual(1,len(list(self.root.glob('reply-*.json'))))
        with self.assertRaises(ValueError):restore(self.root,'../reply-a.json')


if __name__=='__main__':unittest.main()
