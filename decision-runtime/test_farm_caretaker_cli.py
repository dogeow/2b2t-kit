"""CLI lifecycle forwarding stays local; no Minecraft instance is touched."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from farm_caretaker_cli import main
from test_farm_caretaker import profile

class CliTests(unittest.TestCase):
    def invoke(self,action,caretaker):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'profile.json';p.write_text(json.dumps(profile()))
            with patch('farm_caretaker_cli.Caretaker',return_value=caretaker) as factory,contextlib.redirect_stdout(io.StringIO()):
                result=main(['--game-dir',folder,'--profile',str(p),action])
                return result,factory
    def test_status_does_not_start_or_observe_a_game_client(self):
        c=Mock();c.status.return_value={'enabled':False};result,_=self.invoke('status',c)
        self.assertEqual(0,result);c.status.assert_called_once();c.run.assert_not_called();c.resume.assert_not_called()
    def test_pause_and_stop_only_submit_control(self):
        for action in ('pause','stop'):
            c=Mock();c.command.return_value={'id':'x','action':action}
            self.assertEqual(0,self.invoke(action,c)[0]);c.command.assert_called_once_with(action);c.run.assert_not_called()
    def test_run_uses_locked_worker_entry(self):
        c=Mock();c.run.return_value={'ai_calls':0}
        self.assertEqual(0,self.invoke('run',c)[0]);c.run.assert_called_once_with(resume=False);c.resume.assert_not_called()
    def test_resume_running_worker_submits_without_mutating_its_state(self):
        c=Mock();c.worker_running.return_value=True;c.command.return_value={'id':'x','action':'resume'}
        self.assertEqual(0,self.invoke('resume',c)[0]);c.command.assert_called_once_with('resume');c.run.assert_not_called()
    def test_resume_stopped_worker_starts_an_explicit_checked_local_worker(self):
        c=Mock();c.worker_running.return_value=False;c.run.return_value={'ai_calls':0}
        self.assertEqual(0,self.invoke('resume',c)[0]);c.run.assert_called_once_with(resume=True)
    def test_invalid_policy_error_is_reported_without_a_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'profile.json';p.write_text('{}')
            with patch('farm_caretaker_cli.Caretaker',side_effect=ValueError('invalid')) as factory,contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(2,main(['--profile',str(p),'run']))
                self.assertEqual('WAIT_CONTROL',json.loads(output.getvalue())['code']);factory.assert_called_once()

if __name__=='__main__':unittest.main()
