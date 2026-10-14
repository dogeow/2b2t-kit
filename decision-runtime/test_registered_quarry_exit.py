import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from material_jobs.registered_quarry_exit import candidates,path_to_shaft,leave
from material_jobs.protocol import JobBlocked
from test_material_jobs_acquisition import block


class Fake:
    world='w'
    def __init__(self,out):
        self.out=Path(out);self.actions=[];self.rows=[];self.partial=False;self.drift=False;self.mutate=False
        self.state={'world_session':'w','server':'example:25565','dimension':'minecraft:overworld',
                    'pos':[8.5,10.,.5],'health':20,'food':20,'guard_armed':True,'guard_pve_only':True,
                    'flight':True,'air_only_navigation_protocol':2,'manual_movement':False}
    def status(self):return copy.deepcopy(self.state)
    def request(self,op,**args):
        self.actions.append((op,args))
        if op=='scan':
            if self.partial:return {'world_session':'w','phase':'waiting','blocks':[]}
            rows=[r for r in self.rows if all(args['min'][i]<=r['pos'][i]<=args['max'][i]for i in range(3))]
            if self.mutate and any(op=='navigate'for op,_ in self.actions):rows+= [block(tuple(map(int,self.state['pos'])),'water',fluid=True)]
            return {'phase':'done','world_session':'w','blocks':rows}
        if op=='navigate':
            if not self.drift:self.state['pos']=list(args['target'])
            return {'phase':'done'}
        raise AssertionError(op)


def hint():return{'min':[0,-10,0],'max':[1,-1,1],'shaft':{'min':[0,0,0],'max':[1,20,1]},
                  'surface_y':20,'source':'natural_survey','world_session':'w'}
def profile():return{'server':'example','dimension':'minecraft:overworld','quarry_exit_hints':[hint()]}


class ExitTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.c=Fake(self.tmp.name)
    def settled(self,c,target=None,*a,**k):return c.status()
    def run_exit(self):
        with patch('material_jobs.navigation.settled_state',side_effect=self.settled):return leave(self.c,profile())
    def test_nearby_old_coordinates_give_no_clearance_credit_and_use_fresh_scan(self):
        self.assertTrue(self.run_exit());self.assertEqual([1.5,23.,.5],self.c.state['pos'])
        notes=list(self.c.out.glob('registered-quarry-exit-*.json'));self.assertEqual(1,len(notes))
        d=json.loads(notes[0].read_text());self.assertTrue(d['complete']);self.assertEqual(0,d['clearance_credit'])
        self.assertGreater(sum(op=='scan'for op,_ in self.c.actions),3)
        self.assertEqual(2,sum(op=='navigate'for op,_ in self.c.actions))
    def test_incomplete_or_blocked_column_never_moves(self):
        self.c.partial=True
        with self.assertRaises(JobBlocked):self.run_exit()
        self.assertFalse(any(op=='navigate'for op,_ in self.c.actions))
        self.c.partial=False;self.c.actions=[]
        self.c.rows=[block((x,15,z),'water',fluid=True)for x in(0,1)for z in(0,1)]
        with self.assertRaises(JobBlocked):self.run_exit()
        self.assertFalse(any(op=='navigate'for op,_ in self.c.actions))
    def test_foreign_world_distant_and_nonregistered_hint_do_not_scan(self):
        for change in ({'world_session':'old'},{'source':'unknown'}):
            p=profile();p['quarry_exit_hints'][0].update(change);self.assertFalse(leave(self.c,p))
        self.c.state['pos']=[40.5,10,.5];self.assertFalse(leave(self.c,profile()));self.assertFalse(self.c.actions)
    def test_prepare_travel_uses_registered_exit_only_without_current_owned_quarry(self):
        from types import SimpleNamespace
        from material_jobs_backend import Backend
        backend=SimpleNamespace(close_owned_menu=lambda:None,ensure_client=lambda:self.c,
                                leave_registered_workbench=lambda:False,out=self.c.out,profile=profile())
        with patch('material_jobs_backend.leave_quarry',return_value=False),\
             patch('material_jobs.construction_access.recover_pending'),\
             patch('material_jobs.registered_quarry_exit.leave',return_value=True)as registered,\
             patch('material_jobs_backend.leave_projection'):
            Backend.prepare_travel(backend);registered.assert_called_once_with(self.c,backend.profile)
        with patch('material_jobs_backend.leave_quarry',return_value=True),\
             patch('material_jobs.construction_access.recover_pending'),\
             patch('material_jobs.registered_quarry_exit.leave')as registered,\
             patch('material_jobs_backend.leave_projection'):
            Backend.prepare_travel(backend);registered.assert_not_called()
    def test_done_without_arrival_leaves_pending_and_does_not_replay(self):
        self.c.drift=True
        with self.assertRaises(JobBlocked):self.run_exit()
        self.assertEqual(1,sum(op=='navigate'for op,_ in self.c.actions))
        d=json.loads(next(self.c.out.glob('registered-quarry-exit-*.json')).read_text())
        self.assertIsNotNone(d['pending']);self.assertFalse(d['complete'])
    def test_changed_corridor_after_known_first_move_sends_no_ascent(self):
        self.c.mutate=True
        with self.assertRaises(JobBlocked):self.run_exit()
        self.assertEqual(1,sum(op=='navigate'for op,_ in self.c.actions))
    def test_3d_air_path_follows_existing_lower_corridor_and_keeps_bends(self):
        rows=[block((4,y,0),'stone')for y in(10,11)]
        rows += [block((x,12,z),'stone')for x in range(2,11)for z in range(-2,3)]
        # Close side detours, leaving an existing lower opening beneath the wall.
        rows += [block((4,y,z),'stone')for z in(-2,-1,1,2)for y in range(6,17)]
        route=path_to_shaft(rows,[],[8.5,10,.5],hint()['shaft'],20,[-2,6,-2],[10,16,3])
        self.assertTrue(any(p[1]<10 for p in route));self.assertGreaterEqual(len(route),3)
        self.assertTrue(all(abs(b[0]-a[0])+abs(b[1]-a[1])+abs(b[2]-a[2])<=30 for a,b in zip(route,route[1:])))
    def test_wall_with_no_air_route_never_becomes_an_excavation(self):
        rows=[block((4,y,z),'stone')for y in range(6,17)for z in range(-2,4)]
        with self.assertRaises(JobBlocked):path_to_shaft(rows,[],[8.5,10,.5],hint()['shaft'],20,[-2,6,-2],[10,16,3])


if __name__=='__main__':unittest.main()
