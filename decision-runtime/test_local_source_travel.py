import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace

from material_client import Handoff
from material_jobs.protocol import JobBlocked
from material_jobs.local_source_travel import approach


class LocalSourceTravelTest(unittest.TestCase):
    def client(self):
        s={'pos':[0.5,70.2,.5]}
        c=SimpleNamespace(world='w',native_inflight=None,status=lambda:s)
        c.checked=Mock(side_effect=lambda op,**kw:s.update(pos=kw['target']))
        return c,s

    def test_nearby_source_keeps_local_work_height(self):
        c,s=self.client();target=[16.5,72.2,.5]
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.local_source_travel.move',side_effect=lambda *a,**kw:s.update(pos=target))as move,\
             patch('material_jobs.local_source_travel._travel')as travel,\
             patch('material_jobs.local_source_travel.settled_state',side_effect=lambda c,*a:c.status()):
            result=approach(c,target,out,lambda:None)
        self.assertEqual('nearby_scanned_air',result['mode']);move.assert_called_once();travel.assert_not_called();c.checked.assert_not_called()

    def test_only_unsent_local_planning_can_fall_back_to_local_terrain_clearance(self):
        c,s=self.client();target=[16.5,72.2,.5]
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.local_source_travel.move',side_effect=JobBlocked('no connected air')),\
             patch('material_jobs.local_source_travel._travel',side_effect=lambda c,p,*a,**kw:s.update(pos=p))as travel,\
             patch('material_jobs.local_source_travel.settled_state',side_effect=lambda c,*a:c.status()):
            result=approach(c,target,out,lambda:None)
        self.assertEqual(76.2,travel.call_args.args[1][1]);self.assertTrue(result['local_planning_no_movement'])
        self.assertEqual('local_terrain_clearance',result['mode'])

    def test_unknown_or_partial_local_move_never_dispatches_another_route(self):
        c,s=self.client()
        def partial(c,target,out,**kw):
            Path(out).mkdir();(Path(out)/'local-air-path.json').write_text('{"pending":{"request_id":"original"}}')
            raise JobBlocked('original movement unconfirmed')
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.local_source_travel.move',side_effect=partial),\
             patch('material_jobs.local_source_travel._travel')as travel,self.assertRaises(JobBlocked):
            approach(c,[16.5,72.2,.5],out,lambda:None)
        travel.assert_not_called();c.checked.assert_not_called()

    def test_handoff_never_triggers_fallback(self):
        c,s=self.client()
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.local_source_travel.move',side_effect=Handoff('user takeover')),\
             patch('material_jobs.local_source_travel._travel')as travel,self.assertRaises(Handoff):
            approach(c,[16.5,72.2,.5],out,lambda:None)
        travel.assert_not_called();c.checked.assert_not_called()

if __name__=='__main__':unittest.main()
