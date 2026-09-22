import copy,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from decisions import DecisionError,validated_answer,walk_target,validate_local_scene,execute_walk

class Tests(unittest.TestCase):
    def state(self):
        return {'server':'singleplayer','dimension':'minecraft:overworld','connected':True,'screen':'','health':20,'guard_busy':False,'phase':'idle','pos':[0,64,0],'last_request':'a','movement_keys':{}}
    def plan(self):return {'origin':[0,64,0],'targets':{'blue':[4,64,0]}}
    def answer(self):return {'choice':'blue','confidence':.95,'elapsed_ms':100}
    def test_only_offered_choices_and_probabilities_are_accepted(self):
        r={'answers':{'action':{'type':'choice','choice':'blue','confidence':.9,'probabilities':{'blue':.9,'wait':.1}}}}
        self.assertEqual('blue',validated_answer(r,{'blue':'go','wait':'stop'})['choice'])
        r['answers']['action']['choice']='run_shell'
        with self.assertRaises(DecisionError):validated_answer(r,{'blue':'go','wait':'stop'})
    def test_nonfinite_or_unbalanced_probabilities_fail(self):
        for value in [float('nan'),float('inf'),-.1,2]:
            r={'answers':{'action':{'type':'choice','choice':'blue','confidence':.9,'probabilities':{'blue':value,'wait':.1}}}}
            with self.assertRaises(DecisionError):validated_answer(r,{'blue':'','wait':''})
    def test_multiplayer_or_bad_health_menu_and_manual_takeover_cannot_execute(self):
        for change in [{'server':'simpcraft.com'},{'health':10},{'screen':'ChatScreen'},{'guard_busy':True},{'movement_keys':{'forward':True}},{'phase':'running'},{'connected':False}]:
            after={**self.state(),**change}
            with self.assertRaises(DecisionError):validate_local_scene(self.state(),after)
    def test_no_stale_decisions_or_unbounded_waypoints(self):
        for answer in [{**self.answer(),'elapsed_ms':1501}]:
            with self.assertRaises(DecisionError):walk_target(self.plan(),answer,self.state(),self.state())
        for change in [{'pos':[2,64,0]},{'last_request':'someone-else'}]:
            with self.assertRaises(DecisionError):walk_target(self.plan(),self.answer(),self.state(),{**self.state(),**change})
        for target in [[8,64,0],[4,70,0],[float('nan'),64,0]]:
            with self.assertRaises(DecisionError):walk_target({'origin':[0,64,0],'targets':{'blue':target}},self.answer(),self.state(),self.state())
    def test_low_confidence_and_wait_do_not_control_the_game(self):
        self.assertIsNone(walk_target(self.plan(),{**self.answer(),'confidence':.4},self.state(),self.state()))
        self.assertIsNone(walk_target(self.plan(),{**self.answer(),'choice':'wait'},self.state(),self.state()))
    def test_valid_predefined_local_waypoint_is_selected(self):
        self.assertEqual([4,64,0],walk_target(self.plan(),self.answer(),self.state(),self.state()))
    def test_kit_completion_in_status_file_does_not_require_a_reply_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def live(_):
                req=root/'request.json'
                if not req.exists():return self.state()
                r=json.loads(req.read_text())
                return {**self.state(),'id':r['id'],'last_request':r['id'],'phase':'done','pos':[4,64,0]}
            with patch('decisions.status',side_effect=live):
                result=execute_walk(self.plan(),self.answer(),self.state(),root)
            self.assertTrue(result['verified']);self.assertFalse(list(root.glob('reply-*')))
if __name__=='__main__':unittest.main()
