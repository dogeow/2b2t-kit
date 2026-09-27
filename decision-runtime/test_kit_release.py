import tempfile
import zipfile
from pathlib import Path
import unittest
from unittest.mock import patch

from kit_release import install,sha256,version_from_gradle


class KitReleaseTest(unittest.TestCase):
    @patch('kit_release.minecraft_running',return_value=False)
    def test_backups_and_replaces_only_one_kit_jar(self, _):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);repo=root/'repo';game=root/'game'
            (repo/'build/libs').mkdir(parents=True)
            (repo/'gradle.properties').write_text('version=1.9.95\n')
            source=repo/'build/libs/twob2tkit-1.9.95.jar'
            with zipfile.ZipFile(source,'w') as archive:archive.writestr('runtime/twob2tkit-engine.jar',b'new-engine')
            (game/'mods').mkdir(parents=True)
            old=game/'mods/twob2tkit-1.9.94.jar';old.write_bytes(b'old-jar')
            (game/'config').mkdir()
            (game/'config/twob2tkit.json').write_text('{"gravelLimit":0}')
            self.assertEqual('1.9.95',version_from_gradle(repo))
            result=install(repo,game,'1.9.95')
            self.assertEqual(sha256(source),result['sha256'])
            self.assertEqual([source.name],[p.name for p in (game/'mods').glob('twob2tkit-*.jar')])
            self.assertEqual(b'old-jar',(Path(result['backup'])/old.name).read_bytes())
            self.assertTrue((Path(result['backup'])/'twob2tkit.json').exists())
            self.assertEqual(b'new-engine',Path(result['runtime']).read_bytes())

    @patch('kit_release.minecraft_running',return_value=False)
    def test_same_host_version_still_replaces_a_stale_external_engine(self,_):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);repo=root/'repo';game=root/'game';(repo/'build/libs').mkdir(parents=True);(game/'mods').mkdir(parents=True)
            source=repo/'build/libs/twob2tkit-1.9.95.jar'
            with zipfile.ZipFile(source,'w') as archive:archive.writestr('runtime/twob2tkit-engine.jar',b'current-engine')
            (game/'mods'/source.name).write_bytes(source.read_bytes())
            runtime=game/'config/twob2tkit/runtime/twob2tkit-engine.jar';runtime.parent.mkdir(parents=True);runtime.write_bytes(b'old-engine')
            result=install(repo,game,'1.9.95')
            self.assertEqual(b'current-engine',runtime.read_bytes());self.assertEqual(b'old-engine',(Path(result['backup'])/runtime.name).read_bytes())
    @patch('kit_release.minecraft_running',return_value=False)
    def test_failed_host_write_rolls_back_the_engine_and_preserves_old_host(self,_):
        import kit_release
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);repo=root/'repo';game=root/'game';(repo/'build/libs').mkdir(parents=True);(game/'mods').mkdir(parents=True)
            source=repo/'build/libs/twob2tkit-1.9.95.jar'
            with zipfile.ZipFile(source,'w') as archive:archive.writestr('runtime/twob2tkit-engine.jar',b'new-engine')
            old=game/'mods/twob2tkit-1.9.94.jar';old.write_bytes(b'old-host')
            runtime=game/'config/twob2tkit/runtime/twob2tkit-engine.jar';runtime.parent.mkdir(parents=True);runtime.write_bytes(b'old-engine')
            original=kit_release.atomic_bytes
            def write(path,data):
                if path==game/'mods'/source.name:raise OSError('simulated host write failure')
                return original(path,data)
            with patch('kit_release.atomic_bytes',side_effect=write):
                with self.assertRaises(OSError):install(repo,game,'1.9.95')
            self.assertEqual(b'old-host',old.read_bytes());self.assertEqual(b'old-engine',runtime.read_bytes());self.assertEqual(1,len(list((game/'mods').glob('twob2tkit-*.jar'))))

    @patch('kit_release.minecraft_running',return_value=True)
    def test_refuses_to_replace_mod_while_game_runs(self, _):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError,'still running'):
                install(Path(directory),Path(directory),'1.9.95')


if __name__=='__main__':unittest.main()

class ProcessInspectionTest(unittest.TestCase):
    def test_inspection_error_is_not_treated_as_a_stopped_game(self):
        from types import SimpleNamespace
        from kit_release import minecraft_running
        with patch('kit_release.subprocess.run',return_value=SimpleNamespace(returncode=2)):
            with self.assertRaisesRegex(RuntimeError,'installation refused'):minecraft_running()
