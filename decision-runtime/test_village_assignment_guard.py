import unittest,json,tempfile
from pathlib import Path
from village_assignment_guard import uncontained_adults

class AssignmentGuardTests(unittest.TestCase):
    def case(self):
        box={'min':[1,2,3],'max_exclusive':[2,5,6]};home={'min':[0,0,0],'max_exclusive':[10,10,10]}
        policy={'world_session':'w','adult_assignment_bounds':{'trader':box},'shared_adult_bounds':{'founder':home}}
        state={'world_session':'w','loaded_villagers':{'villagers':[{'uuid':'trader','is_baby':False,'pos':[1.5,2.8,4.5]},{'uuid':'founder','is_baby':False,'pos':[5,2,5]}]}}
        return state,policy,home
    def test_trader_and_shared_founder_are_allowed(self):self.assertEqual([],uncontained_adults(*self.case()))
    def test_growth_becomes_a_blocker_while_a_baby_is_allowed(self):
        s,p,h=self.case();child={'uuid':'child','is_baby':True,'pos':[5,2,5]};s['loaded_villagers']['villagers'].append(child)
        self.assertEqual([],uncontained_adults(s,p,h));child['is_baby']=False;self.assertEqual(['child'],uncontained_adults(s,p,h))
    def test_displaced_trader_is_detected_even_outside_home(self):
        s,p,h=self.case();s['loaded_villagers']['villagers'][0]['pos']=[15,2,5];self.assertEqual(['trader'],uncontained_adults(s,p,h))
    def test_unloaded_traders_and_unrelated_wild_adults_are_not_declared_loose(self):
        s,p,h=self.case();s['loaded_villagers']['villagers']=[{'uuid':'wild','is_baby':False,'pos':[50,2,5]}];self.assertEqual([],uncontained_adults(s,p,h))
    def test_world_changes_or_incomplete_positions_require_new_evidence(self):
        for change in ('world','position','bounds'):
            s,p,h=self.case()
            if change=='world':s['world_session']='new'
            if change=='position':s['loaded_villagers']['villagers'][0]['pos']=[float('nan'),2,5]
            if change=='bounds':p['adult_assignment_bounds']['trader']['max_exclusive']=[2,5]
            with self.subTest(change=change),self.assertRaises(RuntimeError):uncontained_adults(s,p,h)
    def test_legacy_projects_without_assignment_map_keep_existing_gate(self):self.assertEqual([],uncontained_adults({}, {}, {}))
    def test_queue_blocks_all_workstation_entrypoints_for_a_new_adult_despite_old_true_flag(self):
        from village_queue import VillageQueue
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);out=root/'owner';out.mkdir();s,p,h=self.case();s.update(screen='',hand={'item':'minecraft:lectern'})
            s['loaded_villagers']['villagers'].append({'uuid':'new-grown','is_baby':False,'pos':[5,2,5]});p.update(all_contained_verified=True,new_workstations_prohibited_until_gate_passes=True)
            (root/'project-state.json').write_text(json.dumps({'workstation_installation_gate':p,'active_village_bounds':{'min':[0,0,0],'max':[9,9,9]}}));table=root/'stage.json';table.write_text(json.dumps({'expected':[{'item':'minecraft:lectern'}]}))
            q=VillageQueue.__new__(VillageQueue);q.world='w';q.out=out;q.closing_menu=None;q.status=lambda **kw:s;calls=[];q._dispatch=lambda *args:calls.append(args)or{'phase':'done'}
            for action,params in [('native',{'op':'interact','params':{'expected_hand':'minecraft:lectern'}}),('native',{'op':'professional_print','params':{}}),('build_village_stage',{'table':str(table)})]:
                with self.subTest(action=action),self.assertRaisesRegex(RuntimeError,'new-grown'):q._send(action,**params)
            self.assertFalse(calls)
            q._send('native',op='interact',params={'expected_hand':'minecraft:cobblestone'})
            self.assertEqual(1,len(calls))

class ContainmentWaitTests(unittest.TestCase):
    def case(self):return AssignmentGuardTests().case()
    def timer(self):
        clock=[0.0]
        def pause(seconds):clock[0]+=seconds
        return lambda:clock[0],pause
    def test_transient_displacement_requires_new_contained_observation(self):
        import copy
        from village_assignment_guard import wait_for_containment
        good,policy,home=self.case();bad=copy.deepcopy(good);bad['loaded_villagers']['villagers'][0]['pos']=[15,2,5];clock,pause=self.timer();calls=[]
        def read():calls.append(1);return good
        state,missing=wait_for_containment(read,policy,home,bad,clock=clock,pause=pause)
        self.assertIs(state,good);self.assertEqual(missing,[]);self.assertEqual(len(calls),1)
    def test_persistent_escape_is_still_rejected_after_bounded_wait(self):
        from village_assignment_guard import wait_for_containment
        bad,policy,home=self.case();bad['loaded_villagers']['villagers'][0]['pos']=[15,2,5];clock,pause=self.timer();state,missing=wait_for_containment(lambda:bad,policy,home,bad,clock=clock,pause=pause)
        self.assertEqual(missing,['trader']);self.assertLessEqual(clock(),2)
    def test_owner_or_world_failure_during_wait_is_not_swallowed(self):
        from village_assignment_guard import wait_for_containment
        bad,policy,home=self.case();bad['loaded_villagers']['villagers'][0]['pos']=[15,2,5];clock,pause=self.timer()
        def failed():raise RuntimeError('owner lost')
        with self.assertRaisesRegex(RuntimeError,'owner lost'):wait_for_containment(failed,policy,home,bad,clock=clock,pause=pause)
    def test_contained_state_is_not_delayed(self):
        from village_assignment_guard import wait_for_containment
        state,policy,home=self.case()
        def failed():raise AssertionError('no read needed')
        self.assertEqual(wait_for_containment(failed,policy,home,state)[1],[])

if __name__=='__main__':unittest.main()
