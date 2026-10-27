import math,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from boat_towing import clear_rows,next_pilot,resumable,envelope,known_air_preflight,measured_cargo_bounds,run
class BoatTowingTests(unittest.TestCase):
    def test_low_riding_zombie_can_use_two_high_entry_but_tall_passenger_still_cannot(self):
        q={'pos':[1084.5,90.1,814.5]};b={'pos':[1080.5,90,814.5],
            'bounds':{'min':[1079.8125,90,813.8125],'max':[1081.1875,90.5625,815.1875]},
            'passengers':[{'bounds':{'min':[1080.2,89.4875,814.2],'max':[1080.8,91.4375,814.8]}}]}
        self.assertEqual(envelope(q,b,[1081.5,90.1,814.5])[1][1],91)
        b['passengers'][0]['bounds']['max'][1]=92.1375
        self.assertEqual(envelope(q,b,[1081.5,90.1,814.5])[1][1],92)
    def test_drowned_transport_requires_current_exact_bait_protection_before_any_input(self):
        q=dict(connected=True,world_session='w',manual_movement=False,screen='',health=20,food=20,guard_armed=True,guard_pve_only=True,supervision_lease=dict(kind='materials',job_session='task',world_session='w'))
        boat=dict(uuid='boat',passengers=[dict(uuid='z',type='minecraft:drowned')])
        class Client:
            world='w';task='task';root=Path('/unused')
            def status(self):return q
            def request(self,*a,**k):raise AssertionError('No unprotected movement')
        with patch('boat_towing.read_frame',return_value=dict(vehicles=[boat])),patch('protected_zombie_transport.observed_aboard',return_value=False)as protection:
            with self.assertRaisesRegex(RuntimeError,'passengers or resolved player leash changed'):
                run(Client(),'boat',['z'],[[0,70,0]],[0,70,0],Path('/unused'),lambda:None,passenger_kind='minecraft:drowned')
            protection.assert_called_once()
    def test_incident_roof_edge_is_rejected_by_full_route_kernel_before_any_flight(self):
        boat=dict(uuid='boat',pos=[.2386618732,64,0],bounds=dict(min=[-.4488381268,64,-.6875],max=[.9261618732,64.5625,.6875]),leashed=True,leash_resolved=True,leash_holder=dict(uuid='player'),passengers=[])
        for uid,x in [('a',.438662),('b',-.361338)]:boat['passengers'].append(dict(uuid=uid,type='minecraft:villager',alive=True,is_baby=False,has_custom_name=False,health=20,bounds=dict(min=[x-.3,64.1875,-.3],max=[x+.3,66.1375,.3])))
        q=dict(connected=True,world_session='w',server='s',dimension='d',player_uuid='player',manual_movement=False,screen='',health=20,food=20,guard_armed=True,guard_pve_only=True,pos=[.46088,69.67656,0],supervision_lease=dict(id='lease',kind='materials',job_session='task',world_session='w'),inventory=[])
        roof=dict(pos=[-2,67,0],state='Block{minecraft:dark_oak_planks}',passable=False,fluid=False,block_entity=False)
        with tempfile.TemporaryDirectory()as directory:
            class Client:
                root=Path(directory);world='w';task='task';server='s';anchor=q['pos'];last=None
                flight_inputs=0
                def status(self):return q
                def checked(self,op,**params):
                    self_test.assertEqual(op,'scan');cells=math.prod(params['max'][i]-params['min'][i]+1 for i in range(3));return dict(id='scan',phase='done',world_session='w',control_revision=1,scan_cells_read=cells,scan_total_cells=cells,blocks=[roof])
                def request(self,*args,**params):self.flight_inputs+=1;raise AssertionError('Unsafe roof clearance must not dispatch flight')
            self_test=self;c=Client()
            with patch('boat_towing.read_frame',return_value=dict(vehicles=[boat],leashables=[])),self.assertRaisesRegex(RuntimeError,'corridor is obstructed'):
                run(c,'boat',['a','b'],[[.46088,71.17656,0]],[.46088,64,0],Path(directory)/'trip',lambda:None)
            self.assertEqual(c.flight_inputs,0)
    def test_recovery_aligns_to_the_docking_column_before_descending(self):
        self.assertEqual(next_pilot([2,66,0],[3,64,0],[1,64,0]),[3,66,0])
    def test_only_exact_unchanged_native_preflight_refusal_can_resolve_a_pending_move(self):
        book={'world_session':'w','pending':{'op':'navigate','request_id':'r','from':[2,66,0]}}
        receipt={'id':'r','world_session':'w','phase':'error','detail':'Air-only navigation requires the current material lease and a loaded clear dry path','pos':[2,66,0]}
        state={'connected':True,'world_session':'w','last_request':'r','pos':[2,66,0]}
        error={'native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'}
        self.assertTrue(known_air_preflight(book,receipt,state,error))
        for update in ({'phase':'waiting'},{'phase':'done'},{'detail':'navigation timed out'},{'id':'other'},{'world_session':'old'},{'pos':[2,65,0]}):
            self.assertFalse(known_air_preflight(book,{**receipt,**update},state,error))
        for update in ({'pos':[3,66,0]},{'manual_movement':True},{'connected':False},{'last_request':'other'}):
            self.assertFalse(known_air_preflight(book,receipt,{**state,**update},error))
        self.assertFalse(known_air_preflight(book,receipt,state,{**error,'unconfirmed_native_request':'r'}))
    def test_resume_requires_the_original_route_world_and_no_pending_input(self):
        route=[[1,90,2]];home=[1,90,3]
        book={'world_session':'w','uuid':'b','passengers':['v'],'route':route,'home':home,'complete':False,
              'pending':None,'legs':[],'waypoint':0,'baseline_health':{'v':20}}
        self.assertTrue(resumable(book,'w','b',['v'],route,home))
        for update in ({'pending':{'request_id':'unknown'}},{'complete':True},{'world_session':'old'},
                       {'uuid':'other'},{'waypoint':1},{'route':[[9,90,2]]},{'baseline_health':{}}):
            self.assertFalse(resumable({**book,**update},'w','b',['v'],route,home))
    def test_cargo_recheck_includes_full_passenger_headroom_and_pilot_destination(self):
        q={'pos':[0,72,0]};boat={'pos':[0,66,0],'bounds':{'min':[-.6875,66,-.6875],'max':[.6875,66.5625,.6875]}}
        low,high=envelope(q,boat,[0,73.5,0])
        self.assertEqual(low,[-2,66,-2]);self.assertEqual(high,[1,75,1])
    def test_paired_passenger_and_leash_drift_include_the_actual_roof_edge_before_lifting(self):
        # Reproduction translated from the recorded pre-injury boat frame.
        boat={'pos':[.2386618732,64,0],'bounds':{'min':[-.4488381268,64,-.6875],'max':[.9261618732,64.5625,.6875]},
              'passengers':[{'bounds':{'min':[-.661338,64.1875,-.3],'max':[-.061338,66.1375,.3]}},
                            {'bounds':{'min':[.138662,64.1875,-.3],'max':[.738662,66.1375,.3]}}]}
        low,high=envelope({'pos':[.46088,69.67656,0]},boat,[.46088,71.17656,0])
        roof={'pos':[-2,67,0],'state':'Block{minecraft:dark_oak_planks}','passable':False,'fluid':False,'block_entity':False}
        self.assertTrue(all(low[i]<=roof['pos'][i]<=high[i]for i in range(3)))
        self.assertFalse(clear_rows([roof],64))
    def test_missing_or_nonfinite_passenger_boxes_fail_before_a_transport_input(self):
        b={'bounds':{'min':[0,64,0],'max':[1,65,1]},'passengers':[{'uuid':'v'}]}
        with self.assertRaises(RuntimeError):measured_cargo_bounds(b)
        b['passengers'][0]['bounds']={'min':[-2,64,0],'max':[float('inf'),66,1]}
        with self.assertRaises(RuntimeError):measured_cargo_bounds(b)
        b['passengers'][0]['bounds']={'min':[-2,64,0],'max':[-1,66,1]}
        self.assertEqual(measured_cargo_bounds(b)['min'][0],-2)
    def test_pilot_cannot_outrun_available_leash_slack_or_drop_cargo_in_large_steps(self):
        self.assertEqual(next_pilot([0,100,0],[30,100,0],[-6,100,0]),[3,100,0])
        self.assertEqual(next_pilot([0,100,0],[0,60,0],[0,94,0]),[0,98.5,0])
        with self.assertRaises(RuntimeError):next_pilot([0,100,0],[30,100,0],[-9,100,0])
    def test_safe_player_air_does_not_authorize_a_roof_or_fluid_in_the_passenger_body(self):
        def row(state,y,**values):return{'state':'Block{minecraft:'+state+'}','pos':[0,y,0],'block_entity':False,'fluid':False,'passable':True,**values}
        self.assertTrue(clear_rows([],64))
        self.assertFalse(clear_rows([row('dark_oak_planks',66,passable=False)],64))
        self.assertFalse(clear_rows([row('water',65,fluid=True)],64))
        self.assertTrue(clear_rows([row('water',63,fluid=True)],63.8))
        self.assertFalse(clear_rows([row('powder_snow',64)],64))
        self.assertTrue(clear_rows([row('dirt_path',63,passable=False)],63.9375))
        self.assertFalse(clear_rows([row('dirt_path',64,passable=False)],63.9375))
if __name__=='__main__':unittest.main()
