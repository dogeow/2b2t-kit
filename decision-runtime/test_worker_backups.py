import os, tempfile, unittest
from pathlib import Path

from worker_backups import prune


class WorkerBackupsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.game = Path(self.tmp.name)
        self.backups = self.game / 'config/twob2tkit/backups'; self.backups.mkdir(parents=True)
        for day in range(10, 25):
            d = self.backups / f'material-worker-202610{day:02d}-120000-000000'; d.mkdir(); (d / 'a.py').write_text('x' * 100)
        (self.backups / 'before-2026.10.14.3-20261014-121332-621733').mkdir()
        (self.backups / 'material-worker-notes').mkdir()

    def tearDown(self): self.tmp.cleanup()

    def names(self): return sorted(p.name for p in self.backups.iterdir())

    def test_dry_run_lists_without_deleting(self):
        before = self.names(); report = prune(self.game, keep=10)
        self.assertEqual(5, report['remove']); self.assertEqual(500, report['remove_bytes'])
        self.assertEqual(before, self.names())

    def test_apply_keeps_the_newest_and_never_touches_other_backups(self):
        report = prune(self.game, keep=10, apply=True)
        self.assertEqual('material-worker-20261010-120000-000000', report['oldest_removed'])
        left = self.names()
        self.assertIn('before-2026.10.14.3-20261014-121332-621733', left)
        self.assertIn('material-worker-notes', left)
        self.assertEqual(10, sum(n.startswith('material-worker-2026') for n in left))
        self.assertIn('material-worker-20261024-120000-000000', left)
        self.assertNotIn('material-worker-20261014-120000-000000', left)

    def test_refuses_zero_keep_and_symlinked_folder(self):
        with self.assertRaises(ValueError): prune(self.game, keep=0)
        other = self.game / 'elsewhere'; other.mkdir()
        os.rename(self.backups, other / 'b'); os.symlink(other / 'b', self.backups)
        with self.assertRaises(ValueError): prune(self.game, keep=10, apply=True)


if __name__ == '__main__': unittest.main()
