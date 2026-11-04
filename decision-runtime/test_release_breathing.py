import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from material_jobs.release_breathing import before_release
from material_jobs.protocol import JobBlocked,JobPaused

class Fake:
    def __init__(self,root):
        self.out=Path(root);self.world='w';self.task='task';self.rev=3;self.heartbeat=SimpleNamespace(id='lease')
        self.last='entry';self.native_inflight=None;self.unconfirmed_native_request=None;self.calls=[]
        self.rows=[{'pos':[1,y,3],'state':'Block{minecraft:water}[level=0]','solid':False,'block_entity':False}for y in [61,62]]
        self.state={'connected':True,'world_session':'w','control_revision':3,'pos':[1.5,61.1,3.5],
            'under_water':False,'air_supply':300,'max_air_supply':300,'health':20,'oxygen_bonus':3,
            'auto_log':True,'flight':True,'time':10,'screen':'','manual_movement':False,
            'supervision_lease':{'kind':'materials','job_session':'task','world_session':'w','id':'lease','revision':3}}
        self.move_phase='done';self.full_air=True;self.scan_bad=False;self.takeover=False
    def status(self,**kw):return copy.deepcopy(self.state)
    def checked(self,op,**kw):
        r=self.request(op,**kw)
        if r.get('phase')!='done':raise RuntimeError('native action failed')
        return r
    def request(self,op,**kw):
        self.calls.append((op,kw));self.last='r'+str(len(self.calls));self.state['time']+=1
        if op=='scan':
            n=1
            for a,b in zip(kw['min'],kw['max']):n*=b-a+1
            return {'phase':'done','world_session':self.world,'blocks':copy.deepcopy(self.rows),
                'scan_cells_read':n-(1 if self.scan_bad else 0),'scan_total_cells':n,
                'scan_start_revision':1,'scan_end_revision':1}
        if op=='navigate':
            if self.move_phase=='done':self.state.update(pos=kw['target'],under_water=False,air_supply=300 if self.full_air else 240)
            if self.takeover:self.state['manual_movement']=True
            return {'phase':self.move_phase}
        return {**self.status(),'phase':None if op=='snapshot'else'done'}

class ReleaseBreathingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.c=Fake(self.tmp.name)
    def test_incident_done_entry_with_stale_false_flag_still_surfaces(self):
        before_release(self.c);ops=[op for op,_ in self.c.calls]
        self.assertEqual(['scan','navigate','snapshot','snapshot'],ops)
        nav=self.c.calls[1][1];self.assertEqual([1.5,64.5,3.5],nav['target'])
        proof=json.loads(next(self.c.out.glob('release-breathing-*.json')).read_text())
        self.assertFalse(proof['cached_under_water']);self.assertTrue(proof['complete'])
        self.assertFalse(proof['lease_released']);self.assertFalse(proof['resource_actions_replayed'])
    def test_observed_submersion_arms_native_air_route_before_ascent(self):
        self.c.state['under_water']=True;before_release(self.c)
        self.assertEqual(['scan','air_return_set','navigate','snapshot','snapshot'],[op for op,_ in self.c.calls])
    def test_actual_dry_column_does_not_start_an_ascent(self):
        self.c.rows=[];before_release(self.c);self.assertEqual(['scan'],[op for op,_ in self.c.calls])
    def test_unknown_old_request_sends_no_new_operation(self):
        for name in ['native_inflight','unconfirmed_native_request']:
            setattr(self.c,name,{'id':'original'})
            with self.assertRaises(JobBlocked):before_release(self.c)
            self.assertEqual([],self.c.calls);setattr(self.c,name,None)
    def test_human_takeover_or_foreign_owner_sends_no_recovery_input(self):
        for key,val in [('manual_movement',True),('screen','ChatScreen'),('world_session','other')]:
            c=Fake(self.tmp.name);c.state[key]=val;before_release(c);self.assertEqual([],c.calls)
    def test_incomplete_scan_never_releases_or_navigates(self):
        self.c.scan_bad=True
        with self.assertRaises(JobBlocked):before_release(self.c)
        self.assertEqual(['scan'],[op for op,_ in self.c.calls])
    def test_partial_roof_over_the_dry_return_is_not_ignored(self):
        self.c.rows.append({'pos':[1,65,3],'state':'Block{minecraft:cobblestone_slab}[type=bottom,waterlogged=false]','solid':False,'block_entity':False})
        with self.assertRaises(JobBlocked):before_release(self.c)
        self.assertFalse(any(op=='navigate'for op,_ in self.c.calls))
    def test_known_unconfirmed_ascent_is_not_replayed(self):
        self.c.move_phase='waiting'
        with self.assertRaises(JobBlocked):before_release(self.c)
        self.assertEqual(1,sum(op=='navigate'for op,_ in self.c.calls))
    def test_takeover_after_ascent_prevents_further_cleanup(self):
        self.c.takeover=True
        with self.assertRaises(JobPaused):before_release(self.c)
        self.assertFalse(any(op=='material_job_pause'for op,_ in self.c.calls))
    def test_reduced_air_is_not_claimed_as_a_completed_return(self):
        self.c.full_air=False
        with patch('material_jobs.release_breathing.time.monotonic',side_effect=[0,7]),self.assertRaises(JobBlocked):before_release(self.c)
        proof=json.loads(next(self.c.out.glob('release-breathing-*.json')).read_text());self.assertFalse(proof['complete'])
    def test_low_air_does_not_begin_new_work_or_release(self):
        self.c.state['air_supply']=200
        with self.assertRaises(JobBlocked):before_release(self.c)
        self.assertEqual(['scan'],[op for op,_ in self.c.calls])
    def test_high_world_edge_dry_park_does_not_scan_out_of_bounds(self):
        self.c.state['pos'][1]=320;before_release(self.c);self.assertEqual([],self.c.calls)
    def test_material_release_calls_the_guard_before_native_pause(self):
        from material_client import MaterialClient,Client
        c=MaterialClient.__new__(MaterialClient);c.task='task';c.recovery_only=False
        order=[]
        with patch('material_jobs.release_breathing.before_release',side_effect=lambda owner:order.append('guard'))as guard,patch.object(Client,'request',side_effect=lambda *a,**k:order.append('native')or{'phase':'done'}):
            self.assertEqual('done',c.request('material_job_pause',release=True)['phase'])
        self.assertEqual(['guard','native'],order);guard.assert_called_once_with(c)
    def test_guard_failure_prevents_native_release(self):
        from material_client import MaterialClient,Client
        c=MaterialClient.__new__(MaterialClient);c.task='task';c.recovery_only=False
        with patch('material_jobs.release_breathing.before_release',side_effect=JobBlocked('dry state unconfirmed')),patch.object(Client,'request')as native:
            with self.assertRaises(JobBlocked):c.request('material_job_pause',release=True)
            native.assert_not_called()

if __name__=='__main__':unittest.main()
