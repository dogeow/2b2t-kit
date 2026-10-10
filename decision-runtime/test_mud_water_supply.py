import unittest
from types import SimpleNamespace
from material_jobs.mud_water_supply import fill
from material_jobs.protocol import JobBlocked

class Client:
    def __init__(self,water=0,source='Block{minecraft:water}[level=0]',error=None):
        self.water=water;self.source=source;self.error=error;self.calls=[]
        self.pos=[43.5,63.1,879.5]
    def status(self):
        return {'pos':self.pos,'inventory':[{'slot':0,'item':'minecraft:water_bucket'if self.water else'minecraft:bucket','count':1}]}
    def checked(self,op,**params):
        self.calls.append((op,params))
        if op=='navigate':self.pos=list(params['target'])
        if op=='scan':return {'phase':'done','blocks':[{'state':self.source}]}
        if op=='bucket_fill':
            if self.error:raise self.error
            self.water=1
        return {'phase':'done'}

class Tests(unittest.TestCase):
    def backend(self,c):
        return SimpleNamespace(ensure_client=lambda:c,checkpoint=lambda:None,profile={'mud_bucket_source':{
            'authorized':True,'renewing_source_server_verified':True,'pos':[43,62,880],
            'approach':[43.5,63.1,879.5],'expected_state':'Block{minecraft:water}[level=0]'}})
    def test_already_carried_water_requires_no_game_action(self):
        c=Client(water=1);self.assertFalse(fill(self.backend(c),1)['new_use']);self.assertEqual([],c.calls)
    def test_unregistered_or_changed_source_never_uses_a_bucket(self):
        c=Client();b=self.backend(c);b.profile['mud_bucket_source']['authorized']=False
        with self.assertRaises(JobBlocked):fill(b,1)
        self.assertEqual([],c.calls)
        c=Client(source='Block{minecraft:air}')
        with self.assertRaises(JobBlocked):fill(self.backend(c),1)
        self.assertFalse(any(op=='bucket_fill'for op,_ in c.calls))
    def test_one_native_fill_keeps_the_source_and_confirms_actual_inventory(self):
        c=Client();r=fill(self.backend(c),1);self.assertTrue(r['source_still_renewed'])
        self.assertTrue(r['farm_water_untouched']);self.assertEqual(1,sum(op=='bucket_fill'for op,_ in c.calls))
    def test_unknown_bucket_result_is_never_repeated(self):
        c=Client(error=RuntimeError('unknown original result'))
        with self.assertRaisesRegex(RuntimeError,'unknown'):fill(self.backend(c),1)
        self.assertEqual(1,sum(op=='bucket_fill'for op,_ in c.calls))
    def test_adjacent_higher_floor_uses_horizontal_leg_before_sandbank_descent(self):
        c=Client();c.pos=[42.26,64,878.5]
        fill(self.backend(c),1)
        moves=[p['target']for op,p in c.calls if op=='navigate']
        self.assertEqual([[43.5,64,879.5],[43.5,63.1,879.5]],moves)
    def test_source_regeneration_is_observed_without_a_second_bucket_use(self):
        c=Client();original=c.checked;reads=[0]
        def delayed(op,**params):
            reply=original(op,**params)
            if op=='scan'and c.water:
                reads[0]+=1
                if reads[0]==1:reply['blocks']=[]
            return reply
        c.checked=delayed
        result=fill(self.backend(c),1)
        self.assertTrue(result['source_still_renewed']);self.assertEqual(2,reads[0])
        self.assertEqual(1,sum(op=='bucket_fill'for op,_ in c.calls))

if __name__=='__main__':unittest.main()
