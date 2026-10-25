import copy,json,tempfile,unittest
from pathlib import Path
from furnace_glass_click import signature,execute
class FurnaceGlassClickTest(unittest.TestCase):
 def fixture(self):
  from test_owned_furnace_origin import OwnedFurnaceOriginTest
  c,r,e,s=OwnedFurnaceOriginTest().fixture();s['menu']['slots']=[{'item':'minecraft:air','count':0}for _ in range(39)];s['menu']['slots'][2]={'item':'minecraft:glass','count':18};p={'menu_id':7,'slot':2,'expected_item':'minecraft:glass','expected_count':18,'expected_cursor':'minecraft:air','expected_cursor_count':0,'kind':'quick_move','button':0};return c,r,e,s,p
 def test_only_glass_output_is_admitted(self):
  *_,s,p=self.fixture();self.assertTrue(signature(s,p,'w'))
  for mode in ['fuel','input','cursor','count','world','health','menu']:
   c,r,e,a,b=copy.deepcopy(self.fixture())
   if mode=='fuel':b['slot']=1
   elif mode=='input':a['menu']['slots'][0]['count']=1
   elif mode=='cursor':a['menu']['cursor']['count']=1
   elif mode=='count':b['expected_count']=17
   elif mode=='world':a['world_session']='other'
   elif mode=='health':a['health']=19
   else:a['menu']['type']='ChestMenu'
   with self.subTest(mode=mode),self.assertRaises(ValueError):signature(a,b,'w')
 def test_proven_late_origin_allows_one_exact_click_and_restores_fence(self):
  with tempfile.TemporaryDirectory()as t:
   c,r,e,s,p=self.fixture();root=Path(t);c['id']='cmd';(root/'command.json').write_text(json.dumps(c));(root/'cmd').mkdir();(root/'cmd/result.json').write_text(json.dumps(r));(root/'control').mkdir();(root/'control/events.jsonl').write_text(json.dumps(e)+'\n')
   class Q:
    out=root;world='w';lease={'id':'l','job_session':'t'}
    def status(self):return s
    def native(self,op,**kw):self.called=(op,kw);raise RuntimeError('readback unavailable')
   q=Q()
   with self.assertRaisesRegex(RuntimeError,'readback unavailable'):execute(q,p,max_glass_total=68)
   self.assertEqual(('slot_click',p),q.called);self.assertIsNone(q._furnace_glass_click)
   with self.assertRaises(ValueError):execute(q,p,max_glass_total=17)
if __name__=='__main__':unittest.main()
