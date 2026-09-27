import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
import zipfile

import material_worker_release as release


class WorkerReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'decision-runtime'
        self.source.mkdir()
        (self.source / 'material_jobs_cli.py').write_text('from helper import available\n')
        (self.source / 'material_jobs_backend.py').write_text('from package.ops import value\ndef create_backend(**kwargs): return value\n')
        (self.source / 'helper.py').write_text('available=True\n')
        (self.source / 'package').mkdir()
        (self.source / 'package' / '__init__.py').write_text('')
        (self.source / 'package' / 'ops.py').write_text('value=1\n')
        (self.source / 'requirements.txt').write_text('httpx==0.28.1\n')
        self.bundle = self.root / 'worker.zip'

    def build(self):
        return release.build(self.source,self.bundle)

    def test_source_only_repeatable_bundle_excludes_credentials_tests_cache_and_state(self):
        for name in ['typesafe.key','config.json','test_secret.py','.env','set_key.py']:
            (self.source / name).write_text('private\n')
        for directory in ['__pycache__','tests','cases','state']:
            (self.source / directory).mkdir()
            (self.source / directory / 'private.py').write_text('secret=True\n')
        first=self.build();second=release.build(self.source,self.root/'again.zip')
        self.assertEqual(first['sha256'],second['sha256'])
        files=release.verify(self.bundle)
        self.assertEqual(set(files),{'material_jobs_cli.py','material_jobs_backend.py','helper.py','package/__init__.py','package/ops.py','requirements.txt','worker-manifest.json'})
        self.assertTrue(release.check_imports(self.bundle)['passed'])

    def test_missing_backend_cannot_ship_as_working_entry(self):
        (self.source/'material_jobs_backend.py').unlink()
        with self.assertRaisesRegex(ValueError,'entry point is missing'):
            self.build()

    def test_bad_syntax_and_embedded_credential_are_refused_without_printing_value(self):
        (self.source/'helper.py').write_text('broken = [\n')
        with self.assertRaises(SyntaxError):self.build()
        fake='apikey_'+'a'*32+'_'+'b'*64
        (self.source/'helper.py').write_text('key='+repr(fake)+'\n')
        with self.assertRaises(ValueError) as error:self.build()
        self.assertNotIn(fake,str(error.exception))

    def test_symlinked_source_is_never_copied(self):
        (self.source/'helper.py').unlink()
        external=self.root/'private.py';external.write_text('private=True\n')
        (self.source/'helper.py').symlink_to(external)
        with self.assertRaisesRegex(ValueError,'symlink'):self.build()

    def test_imports_are_checked_from_archive_not_source_checkout(self):
        (self.source/'material_jobs_backend.py').write_text('import missing_material_helper\n')
        self.build()
        with self.assertRaisesRegex(RuntimeError,'missing_material_helper'):
            release.check_imports(self.bundle)

    def test_import_check_cannot_read_live_credentials(self):
        private=self.root/'secret.key';private.write_text('not-a-real-key')
        (self.source/'material_jobs_backend.py').write_text('from pathlib import Path\nPath('+repr(str(private))+').read_text()\n')
        self.build()
        with self.assertRaisesRegex(RuntimeError,'external operation'):release.check_imports(self.bundle)

    def test_import_check_cannot_open_network(self):
        (self.source/'material_jobs_backend.py').write_text("import socket\nsocket.create_connection(('127.0.0.1', 1))\n")
        self.build()
        with self.assertRaisesRegex(RuntimeError,'external operation'):release.check_imports(self.bundle)

    def test_changed_payload_and_path_traversal_fail_verification(self):
        self.build();files=release.verify(self.bundle)
        files['helper.py']=b'changed=True\n'
        for extra in [None,'../escape.py']:
            with zipfile.ZipFile(self.bundle,'w') as archive:
                for name,data in files.items():archive.writestr(name,data)
                if extra:archive.writestr(extra,b'')
            with self.assertRaises(ValueError):release.verify(self.bundle)

    def test_explicit_deployment_is_idempotent_backs_up_previous_and_copies_no_game_state(self):
        self.build();game=self.root/'game'
        first=release.install(self.bundle,game,running=lambda:False)
        destination=Path(first['installed'])
        self.assertTrue((destination/'material_jobs_cli.py').is_file())
        self.assertTrue(release.install(self.bundle,game,running=lambda:False)['unchanged'])
        (self.source/'helper.py').write_text('available=False\n');self.build()
        second=release.install(self.bundle,game,running=lambda:False)
        self.assertEqual((Path(second['backup'])/'helper.py').read_text(),'available=True\n')
        self.assertEqual((destination/'helper.py').read_text(),'available=False\n')
        self.assertFalse((game/'mods').exists());self.assertFalse((game/'config'/'twob2tkit.json').exists())

    def test_running_or_newly_started_worker_prevents_deployment(self):
        self.build();game=self.root/'game'
        with self.assertRaisesRegex(RuntimeError,'running'):release.install(self.bundle,game,running=lambda:True)
        results=iter([False,True])
        with self.assertRaisesRegex(RuntimeError,'started during staging'):release.install(self.bundle,game,running=lambda:next(results))
        self.assertFalse((game/'config'/'twob2tkit'/'material-worker').exists())

    def test_failed_directory_swap_restores_previous_worker(self):
        self.build();game=self.root/'game'
        first=release.install(self.bundle,game,running=lambda:False)
        (self.source/'helper.py').write_text('available=False\n');self.build()
        original=Path.rename
        def fail_stage(path,destination):
            if path.name.startswith('.material-worker-stage-'):raise OSError('simulated rename failure')
            return original(path,destination)
        with patch.object(Path,'rename',fail_stage):
            with self.assertRaises(OSError):release.install(self.bundle,game,running=lambda:False)
        self.assertEqual((Path(first['installed'])/'helper.py').read_text(),'available=True\n')

    def test_unknown_process_probe_result_fails_closed(self):
        with patch.object(release.subprocess,'run') as run:
            run.return_value.returncode=2
            with self.assertRaisesRegex(RuntimeError,'Cannot determine'):release.worker_running()

    def test_installer_records_actual_python_without_putting_machine_path_in_bundle(self):
        self.build();game=self.root/'game'
        result=release.install(self.bundle,game,python=sys.executable,running=lambda:False)
        self.assertEqual(sys.executable+'\n',(Path(result['installed'])/'runtime-python.txt').read_text())
        self.assertNotIn('runtime-python.txt',release.verify(self.bundle))
        self.assertTrue(release.check_imports(self.bundle)['passed'])

    def test_same_source_bundle_updates_runtime_path_and_backs_up_old_configuration(self):
        self.build();game=self.root/'game'
        old=self.root/'venv old python';new=self.root/'venv new python'
        old.symlink_to(sys.executable);new.symlink_to(sys.executable)
        first=release.install(self.bundle,game,python=old,running=lambda:False)
        second=release.install(self.bundle,game,python=new,running=lambda:False)
        self.assertFalse(second.get('unchanged',False))
        self.assertEqual(str(old)+'\n',(Path(second['backup'])/'runtime-python.txt').read_text())
        self.assertEqual(str(new)+'\n',(Path(first['installed'])/'runtime-python.txt').read_text())
        self.assertTrue(release.install(self.bundle,game,python=new,running=lambda:False)['unchanged'])

    def test_relative_multiline_and_nonexecutable_runtime_paths_are_rejected(self):
        for path in ['relative/python',str(self.root)+'/python\n/other','/'+'x'*4096]:
            with self.assertRaises(ValueError):release.runtime_python_bytes(path)
        file=self.root/'not-executable';file.write_text('x');file.chmod(0o600)
        with self.assertRaises(ValueError):release.runtime_python_bytes(file)


if __name__=='__main__':unittest.main()
