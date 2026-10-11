import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch

from material_jobs.processing import first_collection_delay,_wait_collect
from material_jobs.protocol import JobPaused


class SmeltingPollScheduleTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'batch.json'
        self.job={'world_session':'w','source':'minecraft:cobbled_deepslate',
                  'output':'minecraft:deepslate','recipe_id':'smelting/deepslate','amount':2,
                  'loaded_at':1000,'complete':False,
                  'furnaces':[{'stage':'loaded','amount':2,'pending':None}]}
        self.spec={k:self.job[k] for k in ['source','output','recipe_id']};self.spec['cooking_ticks']=200
        self.path.write_text(json.dumps(self.job));self.client=Mock(world='w')

    def test_known_batch_waits_until_recipe_estimate_then_reads_real_output(self):
        now=[0.0];checks=[];polls=[]
        def checkpoint():checks.append(now[0])
        def collect(*_):polls.append(now[0]);return True
        with patch('material_jobs.processing.time.monotonic',side_effect=lambda:now[0]),\
             patch('material_jobs.processing.time.time',side_effect=lambda:1000+now[0]),\
             patch('material_jobs.processing.time.sleep',side_effect=lambda s:now.__setitem__(0,now[0]+s)),\
             patch('material_jobs.processing.collect',side_effect=collect):
            _wait_collect(self.client,self.path,self.spec,checkpoint)
        self.assertEqual(polls,[20.0]);self.assertGreater(len(checks),20)
        self.assertEqual(json.loads(self.path.read_text()),self.job)
        self.assertFalse(self.job['complete'])

    def test_manual_pause_is_checked_before_any_scheduled_furnace_open(self):
        now=[0.0]
        def checkpoint():
            if now[0]>=1:raise JobPaused('manual takeover')
        with patch('material_jobs.processing.time.monotonic',side_effect=lambda:now[0]),\
             patch('material_jobs.processing.time.time',return_value=1000),\
             patch('material_jobs.processing.time.sleep',side_effect=lambda s:now.__setitem__(0,now[0]+s)),\
             patch('material_jobs.processing.collect') as collect:
            with self.assertRaises(JobPaused):_wait_collect(self.client,self.path,self.spec,checkpoint)
            collect.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text()),self.job)

    def test_resume_clocks_and_partial_cleanup_do_not_defer_inspection(self):
        self.assertEqual(first_collection_delay(self.job,self.spec,1010),10)
        self.assertEqual(first_collection_delay(self.job,self.spec,1025),0)
        for changes in [{'loaded_at':None},{'loaded_at':float('nan')},{'loaded_at':1100},
                        {'furnaces':[{'stage':'output_collected','amount':2}]}]:
            self.assertEqual(first_collection_delay({**self.job,**changes},self.spec,1000),0)
