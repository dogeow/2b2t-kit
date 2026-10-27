import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from material_jobs.bottle_source_guard import clear_drowned,REFUSAL
from material_jobs.protocol import JobBlocked


class Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.q={'world_session':'w','pos':[8.5,64.05,75.5],'health':20,'food':20,'flight':True,
            'guard_armed':True,'guard_pve_only':True,'kill_aura':True,'guard_busy':False,'screen':'',
            'manual_movement':False,'under_water':False,'recent_hurt_at':1,'entities':[],
            'inventory':[{'slot':0,'item':'minecraft:glass_bottle','count':1}]}
        self.mob={'uuid':'enemy','type':'minecraft:drowned','pos':[8.8,61,75.5],'health':20,
                  'hostile':True,'alive':True,'has_custom_name':False,'visible':True}
        self.scans=0;self.calls=[]
        self.c=SimpleNamespace(world='w',task='t',last='rejected',out=Path(t.name),native_inflight=None,
            unconfirmed_native_request=None,status=lambda **kw:copy.deepcopy(self.q),
            last_terminal_evidence={'op':'bottle_fill','phase':'error','detail':REFUSAL,
                'request_id':'rejected','world_session':'w','task_session':'t'})
        def checked(op,**kw):
            self.calls.append((op,kw))
            if op=='scan':
                self.scans+=1;return{'phase':'done','world_session':'w','scan_entities':[self.mob]if self.scans==1 else[]}
            if op=='navigate':self.q['pos']=kw['target']
            return{'phase':'done'}
        self.c.checked=checked
        self.b=SimpleNamespace(ensure_client=lambda:self.c,checkpoint=lambda:None,
            profile={'mud_bucket_source':{'pos':[6,62,75],'approach':[8.5,64.2,75.5]}})
    def run_clearance(self):return clear_drowned(self.b,copy.deepcopy(self.q),sleep=lambda _:None)
    def test_one_proved_pre_dispatch_refusal_uses_normal_aura_and_rechecks_envelope(self):
        self.assertTrue(self.run_clearance());self.assertEqual(2,self.scans)
        self.assertEqual(['scan','select_item','navigate','scan','navigate'],[op for op,_ in self.calls])
        self.assertFalse(any(op in('bottle_fill','mine_block','stop')for op,_ in self.calls))
    def test_unknown_bottle_outcome_never_starts_combat_or_retry(self):
        self.c.last_terminal_evidence['phase']='waiting'
        self.assertFalse(self.run_clearance());self.assertFalse(self.calls)
    def test_caged_piglin_is_never_a_clearance_target(self):
        self.mob['type']='minecraft:zombified_piglin'
        self.assertFalse(self.run_clearance());self.assertEqual(['scan'],[op for op,_ in self.calls])
    def test_health_change_blocks_clearance(self):
        self.q['health']=19
        self.assertFalse(self.run_clearance());self.assertFalse(self.calls)
    def test_unconfirmed_original_request_has_no_combat_authority(self):
        self.c.native_inflight={'request_id':'unknown'}
        self.assertFalse(self.run_clearance());self.assertFalse(self.calls)
