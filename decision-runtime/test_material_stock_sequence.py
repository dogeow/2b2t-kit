import unittest
from material_jobs.stock_sequence import task_observation

class NativeStockSequenceTests(unittest.TestCase):
    def setUp(self):
        self.reply={'observed_at':10000,'material_task':{'id':'new'}}
        self.rows=[{'slot':i,'item':'minecraft:air','count':0}for i in range(43)]
        self.rows[0]={'slot':0,'item':'minecraft:poppy','count':3}

    def test_start_receipt_may_precede_the_next_status_without_replaying_start(self):
        s={'time':10001,'material_task':{'id':'previous','state':'completed'}}
        self.assertEqual('propagating',task_observation(s,self.reply,'previous','minecraft:poppy',3))
        s['time']=13001
        with self.assertRaises(RuntimeError):task_observation(s,self.reply,'previous','minecraft:poppy',3)

    def test_a_different_player_task_does_not_get_the_old_status_grace(self):
        with self.assertRaises(RuntimeError):
            task_observation({'time':10001,'material_task':{'id':'player'}},self.reply,'previous','minecraft:poppy',3)

    def test_complete_stock_requires_control_release_and_actual_main_inventory(self):
        s={'inventory':self.rows,'material_task':{'id':'new','state':'completed','occupied':False,'process_alive':False}}
        self.assertEqual('confirmed',task_observation(s,self.reply,'previous','minecraft:poppy',3))
        s['material_task']['occupied']=True
        self.assertEqual('waiting',task_observation(s,self.reply,'previous','minecraft:poppy',3))
        s['material_task']['occupied']=False;s['inventory'][0]['count']=2
        with self.assertRaises(RuntimeError):task_observation(s,self.reply,'previous','minecraft:poppy',3)

    def test_a_stopped_native_process_never_starts_the_next_task(self):
        with self.assertRaises(RuntimeError):
            task_observation({'material_task':{'id':'new','state':'gathering','process_alive':False}},self.reply,'previous','minecraft:poppy',3)

    def test_host_reap_wait_after_process_exit_is_still_occupied(self):
        s={'material_task':{'id':'new','state':'crafting','process_alive':False,'occupied':True}}
        self.assertEqual('waiting',task_observation(s,self.reply,'previous','minecraft:poppy',3))

if __name__=='__main__':unittest.main()
