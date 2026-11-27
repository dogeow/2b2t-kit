import tempfile, unittest, zipfile
from pathlib import Path

import deploy_kit


def engine(path, version):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as jar:
        jar.writestr('META-INF/MANIFEST.MF', f'Manifest-Version: 1.0\ntwob2tkit-Engine-Version: {version}\n')
        jar.writestr('dev/x.class', version)


class DeployKitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.project = root / 'project'; self.game = root / 'game'
        (self.project / 'build/libs').mkdir(parents=True)
        (self.project / 'gradle.properties').write_text('# x\nversion=2026.11.28.1\nruntime_engine_version=2026.11.28.1\n')
        (self.project / 'build/libs/twob2tkit-2026.11.28.1.jar').write_bytes(b'new-main')
        engine(self.project / 'build/runtime-engine/twob2tkit-engine.jar', '2026.11.28.1')
        (self.game / 'mods').mkdir(parents=True)
        (self.game / 'mods/twob2tkit-2026.11.27.1.jar').write_bytes(b'old-main')
        (self.game / 'mods/other-mod.jar').write_bytes(b'keep')
        engine(self.game / 'config/twob2tkit/runtime/twob2tkit-engine.jar', '2026.11.27.1')

    def tearDown(self): self.tmp.cleanup()

    def test_full_deploy_backs_up_replaces_and_leaves_one_kit_jar(self):
        report = deploy_kit.deploy(self.project, self.game, stamp='T')
        mods = sorted(p.name for p in (self.game / 'mods').iterdir())
        self.assertEqual(['other-mod.jar', 'twob2tkit-2026.11.28.1.jar'], mods)
        self.assertEqual(b'old-main', (self.game / 'mod-backups/twob2tkit-2026.11.27.1-T.jar').read_bytes())
        self.assertTrue((self.game / 'config/twob2tkit/runtime/backups/twob2tkit-engine-2026.11.27.1-T.jar').is_file())
        self.assertEqual('2026.11.28.1', deploy_kit.engine_version(self.game / 'config/twob2tkit/runtime/twob2tkit-engine.jar'))
        self.assertIn('完整重启', report['next'])
        self.assertFalse(list(self.game.rglob('.*.tmp')))

    def test_engine_only_leaves_mods_untouched(self):
        report = deploy_kit.deploy(self.project, self.game, engine_only=True, stamp='T')
        self.assertTrue((self.game / 'mods/twob2tkit-2026.11.27.1.jar').is_file())
        self.assertFalse((self.game / 'mod-backups').exists())
        self.assertIn('reload', report['next'])

    def test_dry_run_changes_nothing(self):
        report = deploy_kit.deploy(self.project, self.game, dry_run=True)
        self.assertEqual(['twob2tkit-2026.11.27.1.jar'], report['would_move_to_backups'])
        self.assertTrue((self.game / 'mods/twob2tkit-2026.11.27.1.jar').is_file())
        self.assertEqual('2026.11.27.1', deploy_kit.engine_version(self.game / 'config/twob2tkit/runtime/twob2tkit-engine.jar'))

    def test_refuses_a_stale_engine_build_before_touching_the_game(self):
        engine(self.project / 'build/runtime-engine/twob2tkit-engine.jar', '2026.11.27.9')
        with self.assertRaises(deploy_kit.DeployError):
            deploy_kit.deploy(self.project, self.game)
        self.assertTrue((self.game / 'mods/twob2tkit-2026.11.27.1.jar').is_file())

    def test_refuses_a_missing_main_jar_and_a_wrong_game_dir(self):
        (self.project / 'build/libs/twob2tkit-2026.11.28.1.jar').unlink()
        with self.assertRaises(deploy_kit.DeployError): deploy_kit.deploy(self.project, self.game)
        with self.assertRaises(deploy_kit.DeployError): deploy_kit.deploy(self.project, self.game / 'nope', engine_only=True)

    def test_same_version_reinstall_is_backed_up_first(self):
        (self.game / 'mods/twob2tkit-2026.11.27.1.jar').unlink()
        (self.game / 'mods/twob2tkit-2026.11.28.1.jar').write_bytes(b'earlier-build')
        deploy_kit.deploy(self.project, self.game, stamp='T')
        self.assertEqual(b'earlier-build', (self.game / 'mod-backups/twob2tkit-2026.11.28.1-T.jar').read_bytes())
        self.assertEqual(b'new-main', (self.game / 'mods/twob2tkit-2026.11.28.1.jar').read_bytes())


if __name__ == '__main__': unittest.main()
