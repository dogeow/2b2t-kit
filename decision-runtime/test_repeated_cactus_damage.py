import copy,unittest
from material_jobs.repeated_cactus_damage import RepeatedCactusDamage


def state(hurt=1000):
    return {'connected':True,'world_session':'w','manual_movement':False,'screen':'',
            'time':hurt+100,'recent_hurt_at':hurt,'recent_attacker':'仙人掌','health':20,
            'control_revision':3,'pos':[10.4,71.9,20.5],
            'supervision_lease':{'id':'lease','kind':'materials','job_session':'task',
                                 'world_session':'w','revision':3}}


class DamageTest(unittest.TestCase):
    def setUp(self):self.p=RepeatedCactusDamage('w','task','lease')
    def test_regenerated_full_health_does_not_hide_two_distinct_hits(self):
        self.assertFalse(self.p.observe(state()))
        self.assertTrue(self.p.observe(state(14000)))
        self.assertEqual([1000,14000],[h['hurt_at']for h in self.p.hits])
    def test_repeated_read_of_one_hit_is_not_repeated_damage(self):
        for _ in range(30):self.assertFalse(self.p.observe(state()))
    def test_stale_damage_or_a_new_mob_hit_is_not_cactus_failure(self):
        s=state();s['time']=10000;self.assertFalse(self.p.observe(s))
        self.assertFalse(self.p.observe(state(11000)))
        s=state(12000);s['recent_attacker']='骷髅';self.assertFalse(self.p.observe(s))
        self.assertFalse(self.p.observe(state(13000)))
    def test_manual_world_lease_revision_and_interface_handoffs_cannot_trigger_logout(self):
        for kind in ('manual','world','lease','task','revision','screen'):
            with self.subTest(kind=kind):
                p=RepeatedCactusDamage('w','task','lease');p.observe(state())
                s=state(2000)
                if kind=='manual':s['manual_movement']=True
                if kind=='world':s['world_session']='new'
                if kind=='lease':s['supervision_lease']['id']='other'
                if kind=='task':s['supervision_lease']['job_session']='other'
                if kind=='revision':s['control_revision']=4
                if kind=='screen':s['screen']='InventoryScreen'
                self.assertFalse(p.observe(s));self.assertEqual([],p.hits)
    def test_distant_or_reversed_hurt_timestamps_do_not_accumulate(self):
        self.p.observe(state(10000));self.assertFalse(self.p.observe(state(50000)))
        self.assertFalse(self.p.observe(state(49000)));self.assertEqual([],self.p.hits)


if __name__=='__main__':unittest.main()
