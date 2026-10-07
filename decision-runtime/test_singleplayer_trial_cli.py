import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from singleplayer_trial_cli import call


class TrialCliTest(unittest.TestCase):
    def game(self,root,**changes):
        game=Path(root);p=game/'config/twob2tkit/automation';p.mkdir(parents=True)
        state={'time':int(time.time()*1000),'singleplayer_trial_api_protocol':1,'connected':True,
               'server':'singleplayer','world_id':str(game/'saves/fresh'),
               'world_session':'session','control_revision':4,**changes}
        (p/'status.json').write_text(json.dumps(state));return game
    def test_server_and_stale_status_never_write_start(self):
        for change in ({'server':'simpcraft.com'},{'time':1},{'singleplayer_trial_api_protocol':0}):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as tmp:
                game=self.game(tmp,**change)
                with self.assertRaises(RuntimeError):call(game,'start')
                self.assertFalse((game/'config/twob2tkit/singleplayer-trial/api-request.json').exists())
    def test_current_world_and_revision_are_scoped(self):
        with tempfile.TemporaryDirectory()as tmp:
            game=self.game(tmp);folder=game/'config/twob2tkit/singleplayer-trial'
            def acknowledge(_):
                r=json.loads((folder/'api-request.json').read_text());self.assertEqual(('session',4),(r['world_session'],r['expected_revision']))
                self.assertEqual(str(game/'saves/fresh'),r['world_id'])
                (folder/('api-reply-'+r['id']+'.json')).write_text(json.dumps({'id':r['id'],'phase':'done'}))
            with patch('singleplayer_trial_cli.time.sleep',side_effect=acknowledge):self.assertEqual('done',call(game,'start')['phase'])
    def test_unconfirmed_previous_command_is_not_replayed(self):
        with tempfile.TemporaryDirectory()as tmp:
            game=self.game(tmp);folder=game/'config/twob2tkit/singleplayer-trial';folder.mkdir()
            p=folder/'api-request.json';original=json.dumps({'id':'prior'});p.write_text(original)
            with self.assertRaisesRegex(RuntimeError,'unconfirmed'):call(game,'start')
            self.assertEqual(original,p.read_text())
    def test_open_and_create_do_not_replace_a_running_world(self):
        with tempfile.TemporaryDirectory()as tmp:
            game=self.game(tmp)
            for command in ('create_world','open_world'):
                with self.assertRaises(RuntimeError):call(game,command,world_id=str(game/'saves/other'))


if __name__=='__main__':unittest.main()
