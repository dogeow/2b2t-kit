import copy,unittest
from material_client import Client,Handoff

class MerchantInterfaceOwnershipTests(unittest.TestCase):
    def samples(self):
        c=Client.__new__(Client);c.world='w';c.rev=7;c.task='task'
        s={'connected':True,'world_session':'w','control_revision':7,'manual_movement':False,'screen':'MerchantScreen',
           'supervision_lease':{'kind':'materials','job_session':'task','world_session':'w','revision':7},
           'menu':{'id':3,'material_owned':True,'merchant':{'protocol':1,'owned':True,'owner_task':'task','villager_uuid':'v'}}}
        return c,s
    def test_only_exact_owned_merchant_screen_is_accepted(self):
        c,s=self.samples();c.raw=lambda:s
        self.assertIs(s,c.status())
    def test_player_opened_wrong_actor_or_foreign_merchant_never_becomes_owned(self):
        for change in ('menu','actor','task','protocol','lease','owned'):
            c,s=self.samples()
            if change=='menu':s['menu']['material_owned']=False
            elif change=='actor':s['menu']['merchant']['villager_uuid']=''
            elif change=='task':s['menu']['merchant']['owner_task']='foreign'
            elif change=='protocol':s['menu']['merchant']['protocol']=2
            elif change=='lease':s['supervision_lease']['job_session']='foreign'
            else:s['menu']['merchant']['owned']=False
            c.raw=lambda:s
            with self.assertRaises(Handoff):c.status()

if __name__=='__main__':unittest.main()
