import copy
import unittest
from material_jobs.wheat_reconnect_repair import historical_removal
from material_jobs.protocol import JobBlocked


class HistoricalRemovalTest(unittest.TestCase):
    def setUp(self):
        self.receipt={'id':'materials-old','world_session':'old','phase':'done','server_confirmed':True,
            'outcome_pending':False,'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
            'server_update_seen':True,'server_observed_state':'Block{minecraft:air}',
            'native_sequence':36,'server_ack_sequence':36,'mining_target':[27,65,70]}
        self.book={'world_session':'old','pending':{'operation':'await_loot','native_mining_confirmed':True,
            'crop_removed':True,'pos':[27,64,70],'native_mining_receipt':copy.deepcopy(self.receipt)}}
        self.reply={**self.receipt,'player_uuid':'player','server':'simpcraft.com:25565','dimension':'minecraft:overworld'}
        self.state={'world_session':'new','player_uuid':'player','server':'simpcraft.com','dimension':'minecraft:overworld'}

    def test_exact_historical_server_removal_can_authorize_only_current_cell_inspection(self):
        before=copy.deepcopy(self.book)
        pending,pos=historical_removal(self.book,self.reply,self.state)
        self.assertEqual([27,64,70],pos);self.assertEqual('await_loot',pending['operation'])
        self.assertEqual(before,self.book)

    def test_unknown_mining_planting_or_other_player_cannot_authorize_repair(self):
        cases=[('book',{'pending':{**self.book['pending'],'operation':'plant'}}),
               ('book',{'pending':{**self.book['pending'],'native_mining_confirmed':False}}),
               ('reply',{'server_confirmed':False}),('reply',{'outcome_pending':True}),
               ('reply',{'server_ack_sequence':35}),('reply',{'mining_target':[28,65,70]}),
               ('state',{'player_uuid':'other'}),('state',{'world_session':'old'}),
               ('state',{'server':'another.server'})]
        for target,change in cases:
            values={'book':copy.deepcopy(self.book),'reply':copy.deepcopy(self.reply),'state':copy.deepcopy(self.state)}
            values[target].update(change)
            with self.subTest(target=target,change=change),self.assertRaises(JobBlocked):historical_removal(**values)


if __name__=='__main__':unittest.main()
