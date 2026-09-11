import tempfile,unittest
from pathlib import Path
from kit_skills.library import SkillManager
from kit_skills.learning import learn_transaction
from kit_skills.planning import goal_request,compile_plan
from kit_skills.model import verify_episode
from test_skills import episode,req

class PlanningTest(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.m=SkillManager(Path(self.temp.name))
    def tearDown(self):self.m.close();self.temp.cleanup()
    def test_unknown_goal_keeps_actual_capability_boundary(self):
        r=goal_request(self.m,'制作铁镐',{})
        self.assertEqual(r['input']['verified_skills'],[]);self.assertNotIn('craft',r['input']['kit_capabilities'])
        with self.assertRaises(ValueError):compile_plan(self.m,{'goal':'制作铁镐','steps':[],'missing_capabilities':['craft']})
    def test_verified_skill_is_compiled_without_execution(self):
        for i in range(2):
            s,e=episode(req(str(i)));learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        r=compile_plan(self.m,{'goal':'前往施工点','steps':[{'skill':'navigate_to_worksite','version':1,'parameters':{'target':[4,64,0],'arrival':1,'seconds':20}}],'missing_capabilities':[]})
        self.assertFalse(r['executed']);self.assertEqual(r['sequence'][0]['steps'][0]['args']['target'],[4,64,0])
    def test_superseding_request_cannot_fake_a_previous_success(self):
        s,e=episode();e['after']['last_request']='different'
        self.assertFalse(verify_episode(s,e)[0])
    def test_goal_context_contains_relevant_failure_lessons(self):
        self.m.lesson({'reason':'采集原木时背包已满，先整理库存'})
        r=goal_request(self.m,'采集原木',{})
        self.assertEqual(len(r['input']['relevant_experiences']),1)
if __name__=='__main__':unittest.main()
