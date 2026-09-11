import json,tempfile,unittest
from pathlib import Path
from kit_skills.library import SkillManager
from kit_skills.catalog import export_catalog
from kit_skills.learning import learn_transaction
from test_skills import episode,req

class CatalogTest(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.m=SkillManager(self.root/'state');self.out=self.root/'catalog.json'
    def tearDown(self):self.m.close();self.temp.cleanup()
    def test_all_skills_are_exported_not_only_top_five(self):
        for i in range(36):
            s,_=episode();s['name']='skill_'+str(i);s['title']='自动技能 '+str(i);self.m.add_new_skill(s)
        self.assertEqual(export_catalog(self.m,self.out),36)
        data=json.loads(self.out.read_text());self.assertEqual(len(data['skills']),36)
    def test_new_skill_and_verification_status_appear_without_manual_catalog_edits(self):
        s,e=episode();self.m.add_new_skill(s);export_catalog(self.m,self.out);self.assertEqual(json.loads(self.out.read_text())['skills'][0]['status'],'candidate')
        for i in range(2):
            s,e=episode(req(str(i)));learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        export_catalog(self.m,self.out);entry=json.loads(self.out.read_text())['skills'][0]
        self.assertEqual(entry['status'],'verified');self.assertEqual(entry['successful_runs'],2);self.assertEqual(entry['origin'],'observed')
    def test_only_latest_version_is_shown_with_its_own_evidence(self):
        for i in range(2):
            s,e=episode(req(str(i)));learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        s['description']='新版本，需要重新验证';self.m.add_new_skill(s);export_catalog(self.m,self.out)
        rows=json.loads(self.out.read_text())['skills'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['version'],2);self.assertEqual(rows[0]['successful_runs'],0);self.assertEqual(rows[0]['status'],'candidate')
    def test_ui_catalog_never_contains_raw_request_or_inventory(self):
        s,e=episode();learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after']);export_catalog(self.m,self.out)
        text=self.out.read_text();self.assertNotIn('last_request',text);self.assertNotIn('simpcraft.com',text);self.assertNotIn('"inventory"',text)
        self.assertEqual(list(self.root.glob('*.tmp')),[])
if __name__=='__main__':unittest.main()
