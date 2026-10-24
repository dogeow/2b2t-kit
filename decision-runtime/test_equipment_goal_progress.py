from copy import deepcopy
import unittest
from equipment_goal_progress import summary


class ProgressTests(unittest.TestCase):
    def fixture(self):
        target={'key':'shovel','item':'minecraft:diamond_shovel','enchantments':{'minecraft:efficiency':5,'minecraft:mending':1}}
        item={'item':target['item'],'count':1,'enchantments':[{'id':k,'level':v}for k,v in target['enchantments'].items()]}
        return {'completed_equipment':[{'key':'shovel','item':item,'proof':'real-operation.json'}]}, {'targets':[target]}
    def test_final_count_requests_audit_and_does_not_mark_goal_complete(self):
        project,acceptance=self.fixture();before=deepcopy(project);result=summary(project,acceptance)
        self.assertEqual(result['done'],1);self.assertEqual(result['phase'],'逐件进行最终实机核验')
        self.assertEqual(project,before);self.assertNotIn('complete',result)
    def test_duplicates_and_missing_highest_enchantment_cannot_inflate_display(self):
        project,acceptance=self.fixture();project['completed_equipment']*=2
        with self.assertRaises(ValueError):summary(project,acceptance)
        project,acceptance=self.fixture();project['completed_equipment'][0]['item']['enchantments'][0]['level']=4
        with self.assertRaises(ValueError):summary(project,acceptance)


if __name__=='__main__':unittest.main()
