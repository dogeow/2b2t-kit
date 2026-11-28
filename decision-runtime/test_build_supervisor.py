import copy
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from build_supervisor import allowed,fingerprint,routine_supply_choice

def snapshot():
    return {'connected':True,'server':'test.example','world_session':'world1','dimension':'minecraft:overworld',
            'bridge_version':3,'supervision_protocol':1,'control_revision':2,'health':20,'food':20,'screen':'','guard_busy':False,
            'phase':'done','last_request':'before','pos':[0,64,0],
            'inventory':[{'slot':i,'item':'minecraft:air','count':0} for i in range(36)],
            'professional_printer':{'waiting_for_server':False},
            'build_job':{'active':True,'session':'job1','placement_key':'plot1','phase':'打印中','outcome':'running',
                         'matched':10,'total':100,'loading':False,'queue_settled':True,'auto_move':True,'material_deficits':{},'blocked_blocks':0}}
class Log:
    def __init__(self):self.events=[];self.handoffs=[];self.outcomes=[]
    def event(self,kind,**data):self.events.append((kind,data))
    def learned(self,*args):return None
    def handoff(self,*args):self.handoffs.append(args)
    def outcome(self,*args):self.outcomes.append(args)


class BuildHelperTests(unittest.TestCase):
    def test_usable_supply_resumes_without_asking_model_to_give_up(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:stone_bricks':272})
        s['inventory'][0]={'slot':0,'item':'minecraft:stone_bricks','count':64}
        self.assertEqual(routine_supply_choice(s,allowed(s)),'resume_after_supply')
        s['build_job']['outcome']='manual_stop';self.assertIsNone(routine_supply_choice(s,allowed(s)))

    def test_missing_planks_with_logs_offers_real_recipe_recovery(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:oak_planks':8})
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_log','count':2}
        self.assertIn('craft_planks',allowed(s));self.assertNotIn('resume_after_supply',allowed(s))
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_planks','count':8}
        self.assertNotIn('craft_planks',allowed(s));self.assertIn('resume_after_supply',allowed(s))
        s['build_job']['outcome']='manual_stop';self.assertEqual(allowed(s),{})
    def test_depot_is_offered_only_with_native_protocol_and_authorized_candidates(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:oak_planks':8})
        self.assertNotIn('fetch_supply',allowed(s))
        s.update(supply_protocol=1,supply_candidates=[{'key':'known','recorded_items':{'minecraft:oak_log':4}}])
        self.assertIn('fetch_supply',allowed(s))
        s['build_job']['outcome']='manual_stop';self.assertNotIn('fetch_supply',allowed(s))
    def test_full_inventory_builds_with_carried_materials_before_fetching_or_crafting(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:oak_planks':5,'minecraft:glass':2})
        s['inventory']=[{'slot':i,'item':'minecraft:dirt','count':64} for i in range(36)]
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_log','count':64}
        s['inventory'][1]={'slot':1,'item':'minecraft:glass','count':20}
        s.update(supply_protocol=1,supply_candidates=[{'key':'box','recorded_items':{'minecraft:oak_planks':3}}])
        options=allowed(s);self.assertIn('resume_after_supply',options);self.assertNotIn('craft_planks',options);self.assertNotIn('fetch_supply',options)
        s['inventory'][2]={'slot':2,'item':'minecraft:air','count':0};self.assertIn('craft_planks',allowed(s))
    def test_blocked_route_can_craft_new_materials_but_cannot_loop_on_unchanged_stock(self):
        s=snapshot();s['build_job'].update(active=False,outcome='blocked',supply_wait=True,supply_resume_ready=False,material_needs={'minecraft:oak_planks':5,'minecraft:glass':2})
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_log','count':10}
        s['inventory'][1]={'slot':1,'item':'minecraft:glass','count':20}
        self.assertIn('craft_planks',allowed(s));self.assertNotIn('resume_after_supply',allowed(s))
        s['build_job']['supply_resume_ready']=True;self.assertIn('resume_after_supply',allowed(s))
        s['build_job']['outcome']='manual_stop';self.assertEqual(allowed(s),{})
    def test_recipe_proposal_respects_output_capacity(self):
        from build_supervisor import compact
        s=snapshot();s['build_job'].update(material_needs={'minecraft:oak_planks':68})
        s['inventory']=[{'slot':i,'item':'minecraft:dirt','count':64} for i in range(36)]
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_planks','count':60,'max_stack':64}
        s['inventory'][1]={'slot':1,'item':'minecraft:oak_log','count':5,'max_stack':64}
        self.assertEqual(compact(s)['recipe_plan']['output_count'],4)
        self.assertFalse(compact(s)['recipe_plan']['covers_current_deficit'])
    def test_knowledge_from_a_different_kit_release_requires_new_validation(self):
        s=snapshot();s['kit_version']='1.9.44';a,_=fingerprint(s);s['kit_version']='1.9.45';b,_=fingerprint(s);self.assertNotEqual(a,b)
    def test_default_port_does_not_split_the_same_server_learning_scope(self):
        s=snapshot();a,_=fingerprint(s);s['server']='TEST.EXAMPLE:25565';b,_=fingerprint(s);self.assertEqual(a,b)
    def test_server_queue_forbids_replanning(self):
        s=snapshot();s['build_job']['queue_settled']=False
        self.assertNotIn('rescan',allowed(s));self.assertNotIn('replan',allowed(s));self.assertIn('wait',allowed(s))

class SafetyLeaseTests(unittest.TestCase):

    def test_close_signals_native_parking_instead_of_leaving_player_idle(self):
        from build_supervisor import SafetyHeartbeat
        with tempfile.TemporaryDirectory() as tmp:
            h=SafetyHeartbeat(tmp,'w');h.start();h.attached=True;h.close()
            beat=json.loads((Path(tmp)/('supervision-heartbeat-'+h.id+'.json')).read_text())
            self.assertTrue(beat['finished']);self.assertEqual(beat['world_session'],'w')
    def test_hung_loop_does_not_keep_player_online_forever(self):
        from build_supervisor import SafetyHeartbeat
        with tempfile.TemporaryDirectory() as tmp:
            h=SafetyHeartbeat(tmp,'w');h.last_poll=time.monotonic()-20;h.start()
            h.thread.join(timeout=3);self.assertFalse(h.thread.is_alive());h.close()

if __name__=='__main__':unittest.main()
