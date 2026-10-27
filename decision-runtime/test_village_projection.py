import unittest
import tempfile,json
from pathlib import Path
from unittest.mock import Mock,patch
from collections import Counter
from types import SimpleNamespace
from village_projection import verify,floor_work_pose
from material_jobs.projection_spatial_cache import native_content_hash

class VillageProjectionTests(unittest.TestCase):
    def test_floor_stance_centres_the_cells_with_clearance_and_never_combines_layers(self):
        pose=floor_work_pose([[10,64,20],[11,64,20],[12,64,20]])
        self.assertEqual([11.5,20.5],[pose[0],pose[2]]);self.assertGreater(pose[1]-65,1.1)
        for positions in([],[[10,64,20],[10,65,20]],[[10,64,20],[10,64,20]]):
            with self.assertRaises(ValueError):floor_work_pose(positions)
    def test_finished_stage_restores_original_32_counter_progress_without_claiming_traders_done(self):
        from village_projection import build
        row={'pos':[1,67,2],'state':'Block{minecraft:dark_oak_planks}','item':'minecraft:dark_oak_planks'}
        table={'bounds':{'min':[1,67,2],'max':[1,67,2]},'expected':[row]}
        model={**table,'model_schema':1,'loaded_chunks_verified':True,'loaded_server_chunks_verified':True,'total':1,'content_hash':native_content_hash([row]),'placement_key':'new'}
        before={'placement_key':'new','total':1,'matched':0,'mismatches':[{'pos':row['pos'],'kind':'missing'}]}
        after={'placement_key':'new','total':1,'matched':1,'mismatches':[],'loaded_server_chunks_verified':True}
        c=Mock();c.world='world';original=SimpleNamespace(total=32,done=0);c.job_progress=original;c.request.return_value={'projection_model':model}
        c.start_progress.side_effect=lambda *a,**k:setattr(c,'job_progress',SimpleNamespace(total=1,done=0))
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory);(p/'table.json').write_text(json.dumps(table))
            with patch('goal_workflow.audit',side_effect=[before,after,after]),patch('goal_workflow.build_phase',return_value=after),patch('village_projection.inventory_counts',side_effect=[Counter({'minecraft:dark_oak_planks':1}),Counter()]),patch('village_projection.time.sleep'):
                result=build(c,p/'table.json',p,lambda:{},'roof')
        self.assertTrue(result['complete']);self.assertIs(c.job_progress,original)
        self.assertEqual((32,0),(c.job_progress.total,c.job_progress.done));c.start_progress.assert_called_once_with('村民交易中心·roof',1,done=0)
    def test_native_model_reads_without_a_phase_are_accepted_before_any_build_input(self):
        from village_projection import build
        rows=[{'pos':[1,67,2],'state':'Block{minecraft:dark_oak_planks}','item':'minecraft:dark_oak_planks'}]
        table={'bounds':{'min':[1,67,2],'max':[1,67,2]},'expected':rows}
        model={**table,'model_schema':1,'loaded_chunks_verified':True,'loaded_server_chunks_verified':True,'total':1,'content_hash':native_content_hash(rows),'placement_key':'new'}
        c=Mock();c.request.return_value={'projection_model':model}
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory);(p/'table.json').write_text(json.dumps(table))
            with patch('goal_workflow.audit',side_effect=RuntimeError('audit boundary reached'))as audit:
                with self.assertRaisesRegex(RuntimeError,'audit boundary reached'):build(c,p/'table.json',p,lambda:{},'roof')
                audit.assert_called_once()
        c.checked.assert_not_called();c.request.assert_called_once_with('projection_model')
    def test_a_previous_or_changed_projection_cannot_be_used_for_the_new_build_stage(self):
        rows=[{'pos':[1,67,2],'state':'Block{minecraft:dark_oak_planks}','item':'minecraft:dark_oak_planks'}]
        table={'bounds':{'min':[1,67,2],'max':[1,67,2]},'expected':rows}
        model={**table,'model_schema':1,'loaded_chunks_verified':True,'loaded_server_chunks_verified':True,'total':1,'content_hash':native_content_hash(rows),'placement_key':'new'}
        self.assertEqual(verify(model,table),'new')
        for change in ({'loaded_server_chunks_verified':False},{'total':2},{'expected':[]},{'content_hash':'0'*64},
                       {'bounds':{'min':[2,67,2],'max':[2,67,2]}}):
            with self.assertRaises(RuntimeError):verify({**model,**change},table)

if __name__=='__main__':unittest.main()
