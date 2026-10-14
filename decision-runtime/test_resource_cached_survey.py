import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch
from material_jobs.resource_cached_survey import slices, wait_ready, rejected_unowned_admission


class CachedGeologySurveyTest(unittest.TestCase):
    def test_healthy_idle_parking_is_bound_to_its_exact_previous_owner(self):
        first={'time':100,'world_session':'w','control_revision':3,'pos':[0,160,0],
               'detail':'parking','health':20,'food':20,
               'supervision_lease':{'kind':'parking','world_session':'w','revision':3,'job_session':'previous'}}
        request={'context':{'server':'test','dimension':'minecraft:overworld'}}
        job=Mock();job.state={}
        with tempfile.TemporaryDirectory()as tmp, \
                patch('material_jobs.resource_cached_survey.read_fresh',return_value=first), \
                patch('material_jobs.resource_cached_survey.WaitingIntent',return_value=job), \
                patch('material_jobs.resource_cached_survey.StationaryResume')as watcher:
            watcher.return_value.poll.return_value=True
            self.assertEqual(first,wait_ready(Path(tmp),request,Path(tmp)/'waiting'))
        self.assertEqual('previous',job.state['native_task_session'])

    def test_only_matching_rejected_startup_can_wait_for_new_admission(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp)/'automation';root.mkdir();attempt=Path(tmp)/'attempt';(attempt/'control').mkdir(parents=True)
            rid='materials-'+'a'*12;task='materials-'+'b'*16
            ready={'world_session':'w','control_revision':3}
            current={**ready,'last_request':rid,'manual_movement':True}
            req={'id':rid,'task_session':task,'op':'material_session','world_session':'w','expected_revision':3}
            reply={'id':rid,'phase':'error','detail':'Material session cannot acquire control',**ready}
            (root/'request.json').write_text(json.dumps(req))
            manifest=attempt/'control'/('run-manifest-'+task+'.json');manifest.write_text(json.dumps({'task_session':task,'world_session':'w'}))
            reply_path=root/('reply-'+rid+'.json');reply_path.write_text(json.dumps(reply))
            with patch('material_jobs.resource_cached_survey.read_fresh',return_value=current):
                self.assertTrue(rejected_unowned_admission(root,attempt,ready))
                reply_path.unlink();self.assertFalse(rejected_unowned_admission(root,attempt,ready))
                reply_path.write_text(json.dumps({**reply,'phase':'done'}));self.assertFalse(rejected_unowned_admission(root,attempt,ready))
                reply_path.write_text(json.dumps(reply));manifest.write_text(json.dumps({'task_session':'foreign','world_session':'w'}));self.assertFalse(rejected_unowned_admission(root,attempt,ready))

    def test_new_stop_all_ends_wait_without_native_dispatch(self):
        first={'time':100,'world_session':'w','control_revision':3,'pos':[0,64,0],
               'detail':'idle','health':20,'food':20}
        stopped={**first,'time':101,'control_revision':4,'detail':'工具箱停止全部'}
        request={'context':{'server':'test','dimension':'minecraft:overworld'}}
        with tempfile.TemporaryDirectory()as tmp, \
                patch('material_jobs.resource_cached_survey.read_fresh',side_effect=[first,stopped]), \
                patch('material_jobs.resource_cached_survey.WaitingIntent'), \
                patch('material_jobs.resource_cached_survey.StationaryResume')as watcher:
            with self.assertRaisesRegex(RuntimeError,'New user stop-all'):
                wait_ready(Path(tmp),request,Path(tmp)/'waiting')
        watcher.return_value.poll.assert_not_called()

    def test_whole_tile_is_read_in_bounded_nonoverlapping_height_slices(self):
        boxes=slices({'tile':[760928,796912]},-64,96)
        self.assertEqual(3,len(boxes))
        self.assertEqual([760928,-64,796912],boxes[0][0])
        self.assertEqual([760943,96,796927],boxes[-1][1])
        self.assertEqual(16*16*161,sum((b[1][1]-b[0][1]+1)*256 for b in boxes))
        self.assertTrue(all(hi[1]-lo[1]<64 for lo,hi in boxes))

    def test_invalid_coordinates_and_world_heights_are_rejected_before_control(self):
        for candidate,low,high in (({'tile':[1]},-64,96),({'tile':[1.,2]},-64,96),
                                  ({'tile':[1,2]},-65,96),({'tile':[1,2]},96,64),
                                  ({'tile':[1,2]},-64,320)):
            with self.assertRaises(ValueError):slices(candidate,low,high)


if __name__=='__main__':unittest.main()
