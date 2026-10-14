import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from material_jobs.recorded_storage_access import Access,bind
from material_jobs.protocol import JobBlocked


class RecordedStorageAccessTest(unittest.TestCase):
    def client(self):
        q={'health':20,'food':20,'under_water':False,'guard_armed':True,
           'guard_pve_only':True,'manual_movement':False,'safety_hold':{},
           'world_session':'world','inventory':[{'item':'minecraft:poppy','count':2}],
           'supervision_lease':{'world_session':'world','job_session':'task','kind':'materials'}}
        return SimpleNamespace(world='world',task='task',status=lambda **kw:q),q

    def test_reuses_client_and_allows_real_transfer_inventory_changes(self):
        with tempfile.TemporaryDirectory()as t:
            c,q=self.client();a=bind(c,{},Path(t),lambda:None)
            self.assertIs(c,a.core);a.status()
            q['inventory'][0]['count']=0
            self.assertEqual(0,a.status()['inventory'][0]['count'])
            self.assertEqual(a.open,c.registered_depot_opener)
            self.assertEqual(a.exit,c.registered_depot_exit)

    def test_changed_owner_and_manual_input_are_not_bypassed(self):
        with tempfile.TemporaryDirectory()as t:
            c,q=self.client();a=Access(c,{},Path(t),lambda:None)
            q['supervision_lease']['job_session']='foreign'
            with self.assertRaises(JobBlocked):a.status()
            q['supervision_lease']['job_session']='task';q['manual_movement']=True
            with self.assertRaises(Exception):a.status()

    def test_different_client_cannot_borrow_geometry(self):
        with tempfile.TemporaryDirectory()as t:
            c,q=self.client();a=Access(c,{},Path(t),lambda:None)
            with self.assertRaises(JobBlocked):a.open(object(),[1,65,1])


if __name__=='__main__':unittest.main()
