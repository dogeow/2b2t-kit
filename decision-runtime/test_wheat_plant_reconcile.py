import copy
import unittest
from wheat_plant_reconcile import prove,HOST,HOST_CLASS_SHA,REJECTION
from potato_farm import _key


class Tests(unittest.TestCase):
    def setUp(self):
        pos=[4,64,8];rows=[{'slot':i,'item':'minecraft:air','count':0}for i in range(43)]
        rows[5].update(item='minecraft:wheat_seeds',count=10)
        hand={'item':'minecraft:wheat_seeds','count':10}
        self.book={'world_session':'world','recent_hurt_at':1,'cells':{_key(pos):{'harvest':{'native_mining_confirmed':True,'remaining_count':0}}},
            'pending':{'operation':'plant','pos':pos,'expected_state':'Block{minecraft:farmland}[moisture=7]',
                'receipt':{'id':'one','phase':'error','detail':REJECTION,'time':10},'before_inventory':rows,
                'before_counts':{'minecraft:wheat_seeds':10},'hand_before':hand}}
        self.reply={'id':'one','phase':'error','detail':REJECTION,'time':10,'kit_version':HOST,
            'world_session':'world','dimension':'minecraft:overworld','control_revision':7,'inventory':rows,'hand':hand}
        self.event={'request_id':'one','op':'interact','phase':'error','detail':REJECTION,
            'params':{'pos':pos,'face':'up','expected_hand':'minecraft:wheat_seeds','expected_state':'Block{minecraft:farmland}[moisture=7]','task_session':'task'},
            'inventory_delta':{},'revision_before':7,'revision_after':7,'position_before':[5,66,9],'position_after':[5,66,9]}
        self.current={'world_session':'world','control_revision':7,'health':20,'recent_hurt_at':1,'screen':'',
            'manual_movement':False,'inventory':rows,'supervision_lease':{'job_session':'task'}}
        self.host={'kit_version':HOST,'class_sha256':HOST_CLASS_SHA}
    def test_exact_pre_use_rejection_has_zero_seed_debit_and_does_not_credit_planting(self):
        result=prove(self.book,self.reply,self.event,self.current,self.host)
        self.assertEqual('rejected_without_use',result['outcome']);self.assertEqual(0,result['seed_debit'])
        self.assertTrue(result['original_attempt_not_done'])
    def test_unknown_host_generic_error_mutation_or_foreign_scope_never_grants_recovery(self):
        for target,changes in [('reply',{'phase':'waiting'}),('reply',{'detail':'unknown'}),
                ('current',{'world_session':'other'}),('current',{'recent_hurt_at':2}),
                ('event',{'inventory_delta':{'minecraft:wheat_seeds':-1}}),('host',{'class_sha256':'unknown'})]:
            values={k:copy.deepcopy(getattr(self,k))for k in ('book','reply','event','current','host')}
            values[target].update(changes)
            with self.assertRaises(RuntimeError):prove(**values)
