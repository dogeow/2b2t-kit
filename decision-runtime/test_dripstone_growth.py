import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from material_jobs.dripstone_growth import growth_column
from material_jobs.protocol import JobBlocked

def row(y,name,props=''):
    return {'pos':[1,y,3],'state':'Block{minecraft:'+name+'}'+props,
            'fluid':name=='water','block_entity':False}

def tip(y,thickness):
    return row(y,'pointed_dripstone','[thickness='+thickness+',vertical_direction=down,waterlogged=false]')

class GrowthColumnTest(unittest.TestCase):
    def test_actual_settled_eye_can_use_center_when_bottom_ray_hits_upward_neighbor(self):
        from types import SimpleNamespace
        from material_jobs import dripstone_growth as module
        partner=tip(68,'tip_merge');partner['state']=partner['state'].replace('vertical_direction=down','vertical_direction=up')
        c=SimpleNamespace(status=lambda:{'pos':[2.5,67.04,3.5]})
        with patch('material_jobs.navigation._air_scan',return_value=[tip(69,'tip'),partner]):
            self.assertIsNone(module.actual_mining_face(c,tip(69,'tip'),'down'))
    def test_long_clear_descent_keeps_turns_but_avoids_three_block_stops(self):
        from types import SimpleNamespace
        from material_jobs import dripstone_growth as module
        from material_jobs.local_air_path import plan as real_plan
        paths=[];c=SimpleNamespace(status=lambda:{'pos':[2.5,90.2,3.5]})
        def record(*args,**kwargs):
            path=real_plan(*args,**kwargs);paths.append(path);return path
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.navigation._air_scan',return_value=[tip(69,'tip')]),\
             patch('material_jobs.local_air_path.plan',side_effect=record),patch('material_jobs.local_air_path.move')as movement,\
             patch('material_jobs.navigation.settled_state'):
            self.assertEqual('down',module.access(c,tip(69,'tip'),d))
        self.assertLessEqual(len(paths[0]),5);self.assertEqual(8,movement.call_args.kwargs['max_straight'])
    def test_access_uses_proved_lower_air_and_down_face_without_generic_depot_movement(self):
        from types import SimpleNamespace
        from material_jobs import dripstone_growth as module
        c=SimpleNamespace(status=lambda:{'pos':[2.5,67.2,3.5]})
        with tempfile.TemporaryDirectory()as d,patch.object(module,'approach_faces')as depot,\
             patch('material_jobs.navigation._air_scan',return_value=[tip(69,'tip')]),patch('material_jobs.local_air_path.plan',return_value=[]),\
             patch('material_jobs.local_air_path.move')as movement,patch('material_jobs.navigation.settled_state'):
            self.assertEqual('down',module.access(c,tip(69,'tip'),d));depot.assert_not_called()
            self.assertEqual([2.5,67.2,3.5],movement.call_args.args[1])
    def farm(self):return [row(71,'dripstone_block'),row(72,'water','[level=0]')]
    def test_blocked_adjacent_columns_can_use_a_proved_lower_diagonal_without_mining_terrain(self):
        from types import SimpleNamespace
        from material_jobs import dripstone_growth as module
        c=SimpleNamespace(status=lambda:{'pos':[2.5,65.2,3.5]})
        def plan(rows,start,target,*a,**kw):
            if abs(target[0]-1.5)<=1 and abs(target[2]-3.5)<=1:raise JobBlocked('blocked adjacent body')
            return [target]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.navigation._air_scan',return_value=[tip(67,'tip')]),\
             patch('material_jobs.local_air_path.plan',side_effect=plan),patch('material_jobs.local_air_path.move')as movement,\
             patch('material_jobs.navigation.settled_state'),patch.object(module,'approach_faces')as depot:
            self.assertEqual('down',module.access(c,tip(67,'tip'),d))
            self.assertGreaterEqual(max(abs(movement.call_args.args[1][0]-1.5),abs(movement.call_args.args[1][2]-3.5)),2)
            depot.assert_not_called()
    def test_clear_body_column_with_occluded_mining_ray_is_not_selected(self):
        from types import SimpleNamespace
        from material_jobs import dripstone_growth as module
        c=SimpleNamespace(status=lambda:{'pos':[3.5,65.2,3.5]})
        rows=[tip(67,'tip'),{'pos':[2,66,3],'state':'Block{minecraft:dirt}'}]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.navigation._air_scan',return_value=rows),\
             patch('material_jobs.local_air_path.plan',return_value=[]),patch('material_jobs.local_air_path.move')as movement,\
             patch('material_jobs.navigation.settled_state'):
            self.assertEqual('down',module.access(c,tip(67,'tip'),d))
            self.assertNotEqual([3.5,65.2,3.5],movement.call_args.args[1])
    def test_three_segments_choose_lowest_and_preserve_root(self):
        result=growth_column(self.farm()+[tip(70,'base'),tip(69,'frustum'),tip(68,'tip')],[1,70,3],60)
        self.assertEqual([1,68,3],result['next']['pos']);self.assertEqual(3,len(result['chain']))
    def test_one_segment_never_mined(self):
        self.assertIsNone(growth_column(self.farm()+[tip(70,'tip')],[1,70,3],60)['next'])
    def test_root_touching_an_upward_stalagmite_remains_an_unmined_root(self):
        partner=tip(69,'tip_merge');partner['state']=partner['state'].replace('vertical_direction=down','vertical_direction=up')
        column=growth_column(self.farm()+[tip(70,'tip_merge'),partner],[1,70,3],60)
        self.assertIsNone(column['next']);self.assertEqual(1,len(column['chain']))
        partner['state']=partner['state'].replace('waterlogged=false','waterlogged=true')
        with self.assertRaises(JobBlocked):growth_column(self.farm()+[tip(70,'tip_merge'),partner],[1,70,3],60)
    def test_merged_lower_tip_uses_visible_side_without_crossing_upward_partner(self):
        from types import SimpleNamespace
        from material_jobs import dripstone_growth as module
        partner=tip(68,'tip_merge');partner['state']=partner['state'].replace('vertical_direction=down','vertical_direction=up')
        target=tip(69,'tip_merge');c=SimpleNamespace(status=lambda:{'pos':[1.5,67.2,2.5]})
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.navigation._air_scan',return_value=[target,partner]),\
             patch('material_jobs.local_air_path.plan',return_value=[]),patch('material_jobs.local_air_path.move'),\
             patch('material_jobs.navigation.settled_state'):
            self.assertIsNone(module.access(c,target,d))
    def test_known_farm_volume_is_scanned_once_for_access_options(self):
        from types import SimpleNamespace
        from material_jobs import dripstone_growth as module
        c=SimpleNamespace(status=lambda:{'pos':[2.5,80.2,3.5]})
        bounds={'min':[-3,60,-3],'max':[6,90,9]}
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.navigation._air_scan',return_value=[tip(69,'tip')])as scan,\
             patch('material_jobs.local_air_path.plan',return_value=[]),patch('material_jobs.local_air_path.move')as movement,\
             patch('material_jobs.navigation.settled_state'):
            self.assertEqual('down',module.access(c,tip(69,'tip'),d,bounds=bounds))
        self.assertEqual(1,scan.call_count);self.assertEqual(bounds,movement.call_args.kwargs['scan_bounds'])
    def test_gap_cannot_use_disconnected_lower_tip(self):
        with self.assertRaises(JobBlocked):growth_column(self.farm()+[tip(70,'frustum'),tip(68,'tip')],[1,70,3],60)
    def test_sulfur_upward_and_waterlogged_refused(self):
        for change in ('sulfur_spike','vertical_direction=up','waterlogged=true'):
            b=tip(70,'tip');b['state']=b['state'].replace('pointed_dripstone',change)if change=='sulfur_spike'else b['state'].replace(change.split('=')[0]+'='+('down'if 'vertical' in change else'false'),change)
            with self.assertRaises(JobBlocked):growth_column(self.farm()+[b],[1,70,3],60)
    def test_source_water_and_support_required(self):
        for rows in ([row(71,'dark_oak_planks'),row(72,'water','[level=0]')],[row(71,'dripstone_block'),row(72,'water','[level=1]')]):
            with self.assertRaises(JobBlocked):growth_column(rows+[tip(70,'tip')],[1,70,3],60)

    def client(self,directory,unconfirmed=False):
        from test_dry_clay_columns import Fake
        c=Fake(Path(directory));c.pos=[2.5,66.2,3.5];c.counts={'minecraft:pointed_dripstone':0};c.blocks={tuple(b['pos']):b for b in self.farm()+[tip(70,'base'),tip(69,'frustum'),tip(68,'tip')]}
        c.set_progress=lambda **kw:None;original=c.request
        def request(op,**kw):
            if op!='mine_block':return original(op,**kw)
            c.calls.append((op,kw));c.last='mine-'+str(len(c.calls))
            c.blocks.pop(tuple(kw['pos']));higher=c.blocks[(1,kw['pos'][1]+1,3)]
            higher['state']=tip(kw['pos'][1]+1,'tip')['state'];c.counts['minecraft:pointed_dripstone']+=1
            return {'id':c.last,'world_session':c.world,'phase':'done','server_confirmed':True,
                    'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
                    'native_sequence':2,'server_ack_sequence':1 if unconfirmed else 2}
        c.request=request;return c

    def test_live_loop_mines_bottom_up_then_never_replays_completed_journal(self):
        from material_jobs import dripstone_growth as module
        with tempfile.TemporaryDirectory()as directory,patch.object(module,'access',return_value='down'):
            c=self.client(directory);out=Path(directory)/'harvest'
            result=module.harvest(c,[[1,70,3]],60,out,lambda:None)
            self.assertEqual([[1,68,3],[1,69,3]],[kw['pos']for op,kw in c.calls if op=='mine_block'])
            self.assertEqual(2,result['actual_gained']);self.assertIn((1,70,3),c.blocks)
            with self.assertRaises(JobBlocked):module.harvest(c,[[1,70,3]],60,out,lambda:None)
    def test_unreachable_column_is_deferred_before_any_mining(self):
        from material_jobs import dripstone_growth as module
        from work_access import ApproachUnavailable
        with tempfile.TemporaryDirectory()as directory,patch.object(module,'access',side_effect=ApproachUnavailable('no clear side')):
            c=self.client(directory);result=module.harvest(c,[[1,70,3]],60,Path(directory)/'harvest',lambda:None)
            self.assertTrue(result['complete']);self.assertEqual(0,result['actual_gained']);self.assertIsNone(result['pending'])
            self.assertFalse(result['deferred_columns'][0]['mining_sent'])
            self.assertFalse(any(op=='mine_block'for op,_ in c.calls))
    def test_two_deferred_columns_keep_distinct_access_receipts_without_overwriting(self):
        from material_jobs import dripstone_growth as module
        from work_access import ApproachUnavailable
        with tempfile.TemporaryDirectory()as directory:
            c=self.client(directory);seen=[]
            for b in list(c.blocks.values()):
                other={**b,'pos':[4,b['pos'][1],3]};c.blocks[tuple(other['pos'])]=other
            def access(c,tip,out,**kwargs):
                out.mkdir(parents=True,exist_ok=False);seen.append(out)
                raise ApproachUnavailable('Known route blocked before mining')
            with patch.object(module,'access',side_effect=access):
                result=module.harvest(c,[[1,70,3],[4,70,3]],60,Path(directory)/'harvest',lambda:None)
            self.assertEqual(2,len(set(seen)));self.assertEqual(2,len(result['deferred_columns']))
            self.assertEqual(0,result['actual_gained']);self.assertFalse(any(op=='mine_block'for op,_ in c.calls))
    def test_exact_native_pre_send_rejection_is_deferred_without_false_unknown_or_replay(self):
        from material_jobs import dripstone_growth as module
        with tempfile.TemporaryDirectory()as directory,patch.object(module,'access',return_value='down'):
            c=self.client(directory);original=c.request
            def request(op,**kw):
                if op!='mine_block':return original(op,**kw)
                c.calls.append((op,kw));c.last='known-rejected'
                return {'id':c.last,'world_session':c.world,'op':op,'mining_target':kw['pos'],
                        'phase':'waiting','detail':'mining target is occluded','native_sequence':-1,'server_ack_sequence':-1,
                        'server_confirmed':False,'outcome_pending':False,'server_update_seen':False}
            c.request=request
            result=module.harvest(c,[[1,70,3]],60,Path(directory)/'harvest',lambda:None)
            self.assertTrue(result['complete']);self.assertIsNone(result['pending']);self.assertEqual(0,result['actual_gained'])
            self.assertEqual(1,len([1 for op,kw in c.calls if op=='mine_block']))
            shared=next((Path(directory)/'dripstone-growth-intents').glob('*.json'))
            self.assertLess(shared.stat().st_size,16384);self.assertIsNone(json.loads(shared.read_text())['pending'])
            self.assertIn((1,68,3),c.blocks)
    def test_new_random_growth_before_mining_defers_only_that_column_without_mining(self):
        from material_jobs import dripstone_growth as module
        with tempfile.TemporaryDirectory()as directory:
            c=self.client(directory)
            def access(*args,**kwargs):
                c.blocks[(1,68,3)]=tip(68,'frustum');c.blocks[(1,67,3)]=tip(67,'tip');return'down'
            with patch.object(module,'access',side_effect=access):
                result=module.harvest(c,[[1,70,3]],60,Path(directory)/'harvest',lambda:None)
            self.assertTrue(result['complete']);self.assertEqual(0,result['actual_gained']);self.assertIsNone(result['pending'])
            self.assertFalse(any(op=='mine_block'for op,_ in c.calls))

    def test_missing_sequence_ack_keeps_original_intent_and_does_not_mine_next(self):
        from material_jobs import dripstone_growth as module
        with tempfile.TemporaryDirectory()as directory,patch.object(module,'access',return_value='down'):
            c=self.client(directory,True);out=Path(directory)/'harvest'
            with self.assertRaises(JobBlocked):module.harvest(c,[[1,70,3]],60,out,lambda:None)
            self.assertEqual(1,sum(op=='mine_block'for op,_ in c.calls))
            self.assertEqual([1,68,3],json.loads((out/'growth-harvest.json').read_text())['pending']['pos'])
            with self.assertRaisesRegex(JobBlocked,'across jobs'):
                module.harvest(c,[[1,70,3]],60,Path(directory)/'another-job',lambda:None)

    def test_air_pickup_uses_fresh_drop_height_and_exact_gain_without_remine(self):
        from material_jobs import dripstone_growth as module
        with tempfile.TemporaryDirectory()as directory:
            c=self.client(directory);drop={'type':'minecraft:item','uuid':'floating','pos':[1.125,62.4,3.6],
                                          'stack':{'item':module.ITEM,'count':1}};c.drops=[drop]
            c.pos=[1.5,66.2,3.5]
            def pick(client,original,before,*a,**kw):
                self.assertEqual('floating',original['uuid']);self.assertEqual(module.ITEM,kw['item'])
                self.assertEqual(0,before);client.counts[module.ITEM]+=1;client.drops=[];return True
            with patch('material_jobs.dry_hover_harvest.pickup',side_effect=pick):
                self.assertTrue(module.collect_from_air(c,drop,Path(directory)/'air',c.status))
            self.assertFalse(any(op=='mine_block'for op,_ in c.calls))

if __name__=='__main__':unittest.main()
