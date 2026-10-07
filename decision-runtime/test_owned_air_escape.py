import unittest
from types import SimpleNamespace
from owned_air_escape import blocks_segment,side_candidates,wait_known_idle


def solid(x,y,z):return {'pos':[x,y,z],'passable':False,'fluid':False}


class CanopyEscapeTest(unittest.TestCase):
    def test_block_outside_body_corridor_does_not_block_side_flight(self):
        self.assertFalse(blocks_segment(solid(33,69,882),[32.5,69,882.5],[24.5,69,882.5]))
        self.assertTrue(blocks_segment(solid(31,70,882),[32.5,69,882.5],[24.5,69,882.5]))

    def test_single_pad_below_canopy_needs_side_flight_without_walking_floor(self):
        rows=[solid(x,75,z)for x in range(25,41)for z in range(874,891)]
        rows.append(solid(32,68,882))
        plan=side_candidates(rows,[32.5,69,882.5],130)
        self.assertEqual([24.5,69,882.5],plan[0][1])
        self.assertEqual([24.5,130,882.5],plan[0][2])

    def test_fluid_or_solid_corridor_preserves_all_blocks_and_returns_no_route(self):
        rows=[solid(x,70,z)for x in range(24,42)for z in range(874,891)]
        self.assertEqual([],side_candidates(rows,[32.5,69,882.5],130))
        self.assertTrue(blocks_segment({'pos':[31,69,882],'passable':True,'fluid':True},[32.5,69,882.5],[30.5,69,882.5]))

    def test_escape_budget_rejects_unbounded_routes(self):
        with self.assertRaises(ValueError):side_candidates([],[32.5,69,882.5],130,radius=9)

    def idle_client(self,changed_owner=False,unknown=False):
        states=[{'world_session':'w','control_revision':5,'pending_scan':{},
                 'supervision_lease':{'id':'h','job_session':'t','kind':'materials','revision':5}},
                {'world_session':'w','control_revision':5,'pending_scan':None,
                 'supervision_lease':{'id':'other' if changed_owner else 'h','job_session':'t','kind':'materials','revision':5}}]
        c=SimpleNamespace(last='r',task='t',world='w',rev=5,heartbeat=SimpleNamespace(id='h'),
                          native_inflight=None,unconfirmed_native_request={'id':'r'} if unknown else None,
                          last_terminal_evidence={'request_id':'r','task_session':'t','world_session':'w','revision_after':5,'phase':'done'})
        c.status=lambda:states.pop(0)
        return c

    def test_completed_scan_waits_for_same_owner_publication_without_another_request(self):
        c=self.idle_client()
        state=wait_known_idle(c,idle_predicate=lambda c,s:s['pending_scan'] is None and s['supervision_lease']['id']=='h')
        self.assertIsNone(state['pending_scan'])

    def test_changed_owner_or_unknown_result_cannot_start_escape(self):
        for c in(self.idle_client(changed_owner=True),self.idle_client(unknown=True)):
            with self.assertRaises(RuntimeError):wait_known_idle(c,idle_predicate=lambda c,s:False)


if __name__=='__main__':unittest.main()
