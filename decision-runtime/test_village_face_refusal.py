import json,tempfile,unittest
from unittest.mock import patch
from kit_runtime.journal import write_json
from test_village_queue import VillageQueueTests

class FaceRefusalTests(unittest.TestCase):
 def fixture(self,directory):
  q,d,e=VillageQueueTests().air_refusal(directory);command=json.loads((q.out/'command.json').read_text());command['op']='interact';write_json(q.out/'command.json',command);reply=json.loads((d/'result.json').read_text());reply['detail']='Target interaction face is occluded or out of reach';write_json(d/'result.json',reply);e.update(op='interact',detail=reply['detail']);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');return q,d,e
 def test_preserves_receipt_and_only_observes(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e=self.fixture(directory);original=(d/'result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_refused_interaction_face()
   self.assertEqual(['snapshot'],[x['op']for x in sent]);self.assertEqual(original,(d/'result.json').read_bytes())
 def test_unknown_or_changed_inventory_is_not_released(self):
  for mode in ['unknown','inventory']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,e=self.fixture(directory)
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    else:e['inventory_delta']={'minecraft:torch':-1};(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
    with self.assertRaises(RuntimeError):q.observe_refused_interaction_face()

class BucketFaceRefusalTests(FaceRefusalTests):
 def fixture(self,directory):
  q,d,e=super().fixture(directory);command=json.loads((q.out/'command.json').read_text());command['op']='bucket_place';write_json(q.out/'command.json',command)
  reply=json.loads((d/'result.json').read_text());reply['detail']='Bucket support face is occluded or outside normal reach';write_json(d/'result.json',reply)
  e.update(op='bucket_place',detail=reply['detail']);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
  q.observe_refused_interaction_face=q.observe_refused_bucket_face
  return q,d,e

class BucketOccupancyRefusalTests(BucketFaceRefusalTests):
 def fixture(self,directory):
  q,d,e=super().fixture(directory);reply=json.loads((d/'result.json').read_text());reply['detail']='Bucket target contains a currently loaded entity';write_json(d/'result.json',reply)
  e['detail']=reply['detail'];(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');q.observe_refused_interaction_face=q.observe_refused_bucket_occupancy
  return q,d,e

class MiningReachRefusalTests(FaceRefusalTests):
 def fixture(self,directory):
  q,d,e=super().fixture(directory);command=json.loads((q.out/'command.json').read_text());command['op']='mine_block';write_json(q.out/'command.json',command)
  reply=json.loads((d/'result.json').read_text());reply['detail']='Mining target out of reach';write_json(d/'result.json',reply);e.update(op='mine_block',detail=reply['detail']);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');q.observe_refused_interaction_face=q.observe_refused_mining_reach
  return q,d,e
class CollectionPathRefusalTests(FaceRefusalTests):
 def fixture(self,directory):
  q,d,e=super().fixture(directory);command=json.loads((q.out/'command.json').read_text());command['op']='collect_item';write_json(q.out/'command.json',command)
  reply=json.loads((d/'result.json').read_text());reply.update(phase='waiting',detail='No loaded collision-free route to this depot; no ceiling is broken');write_json(d/'result.json',reply);e.update(op='collect_item',phase='waiting',detail=reply['detail']);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');q.observe_refused_interaction_face=q.observe_refused_collection_path
  return q,d,e
 def test_moved_collector_is_not_a_preflight_refusal(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e=self.fixture(directory);e['position_after']=[5,64,5];(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
   with self.assertRaises(RuntimeError):q.observe_refused_collection_path()
class ControlledReleaseDecorationTests(FaceRefusalTests):
 def fixture(self,directory):
  q,d,e=super().fixture(directory);cmd=json.loads((q.out/'command.json').read_text());cmd.update(op='mine_block',params={'controlled_water_release':True});write_json(q.out/'command.json',cmd);r=json.loads((d/'result.json').read_text());r['detail']='Controlled release cannot replace decorations or waterlog blocks';write_json(d/'result.json',r);e.update(op='mine_block',detail=r['detail']);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');q.observe_refused_interaction_face=q.observe_controlled_release_decoration_refusal;return q,d,e
 def test_ordinary_mining_never_uses_this_observation(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e=self.fixture(directory);cmd=json.loads((q.out/'command.json').read_text());cmd['params']['controlled_water_release']=False;write_json(q.out/'command.json',cmd)
   with self.assertRaises(RuntimeError):q.observe_controlled_release_decoration_refusal()
class ControlledReleaseContainmentTests(ControlledReleaseDecorationTests):
 def fixture(self,directory):
  q,d,e=super().fixture(directory);r=json.loads((d/'result.json').read_text());r['detail']='Released water could escape the declared enclosure';write_json(d/'result.json',r);e['detail']=r['detail'];(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');q.observe_refused_interaction_face=q.observe_controlled_release_containment_refusal;return q,d,e
if __name__=='__main__':unittest.main()


class ProtectedEmptyLecternRefusalTests(FaceRefusalTests):
 def fixture(self,directory):
  q,d,e=super().fixture(directory);command=json.loads((q.out/'command.json').read_text());command.update(op='mine_block',params={'expected_state':'Block{minecraft:lectern}[facing=north,has_book=false,powered=false]','expected_villager_uuid':'v','expected_quote_opening':'o','expected_offers_fingerprint':'f'});write_json(q.out/'command.json',command);r=json.loads((d/'result.json').read_text());r['detail']='Block entities and containers are protected';write_json(d/'result.json',r);e.update(op='mine_block',detail=r['detail']);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');q.observe_refused_interaction_face=q.observe_protected_empty_lectern;return q,d,e
 def test_a_general_container_refusal_cannot_be_used_as_a_lectern_intent(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e=self.fixture(directory);cmd=json.loads((q.out/'command.json').read_text());cmd['params']['expected_state']='Block{minecraft:chest}';write_json(q.out/'command.json',cmd)
   with self.assertRaises(RuntimeError):q.observe_protected_empty_lectern()
