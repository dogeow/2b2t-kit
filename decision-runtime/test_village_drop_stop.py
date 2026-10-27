import json
from unittest.mock import patch
import tempfile
import unittest
from test_village_queue import VillageQueueTests
from kit_runtime.journal import write_json


class DropStopTests(unittest.TestCase):
    def test_drop_guard_stop_authorizes_only_snapshot_with_no_goal_credit(self):
        with tempfile.TemporaryDirectory()as directory:
            q,d,event,state=VillageQueueTests().stopped_walk(directory)
            result=json.loads((d/'result.json').read_text());result['detail']='unsafe drop ahead; choose another walking waypoint'
            write_json(d/'result.json',result);event['detail']=result['detail'];(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
            original=(d/'result.json').read_bytes();sent=[]
            def owner(path,value):
                write_json(path,value)
                if path.name=='command.json':
                    sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
            with patch('village_queue.write_json',side_effect=owner):q.observe_stopped_walk()
            self.assertEqual([v['op']for v in sent],['snapshot']);self.assertEqual((d/'result.json').read_bytes(),original)


if __name__=='__main__':unittest.main()
