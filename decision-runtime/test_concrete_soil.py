import unittest
from concrete_soil import resolve,recover

POWDER='minecraft:white_concrete_powder';SOLID='minecraft:white_concrete'
def state(powder,solid):return {'health':20,'inventory':[{'item':POWDER,'count':powder},{'item':SOLID,'count':solid}]}
class SoilTest(unittest.TestCase):
    def test_only_natural_full_dirt_grass_change_is_accepted(self):
        row={'pos':[1,61,1],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False}
        self.assertEqual(row['state'],resolve([row],[1,61,1],'Block{minecraft:dirt}'))
        with self.assertRaises(RuntimeError):resolve([{**row,'state':'Block{minecraft:chest}','block_entity':True}],[1,61,1],'Block{minecraft:dirt}')
    def test_only_unspent_remainder_is_placed_after_recovering_existing_solid(self):
        class Client:
            powder=97;solid=22;residual=True;actions=[];pose="stand"
            def status(self):return state(self.powder,self.solid)
            def checked(self,*args,**kwargs):pass
            def request(self,op,**params):
                if op=='scan':return {'blocks':[{'pos':[1,61,1],'state':'Block{minecraft:dirt}','solid':True}]+([{'pos':[1,62,1],'state':'Block{minecraft:white_concrete}'}] if self.residual else [])}
                if self.pose!='stand':raise AssertionError('Must return from the pickup pit before placing again')
                self.actions.append(params['target_count'])
                if self.residual:self.residual=False;self.solid+=1;self.pose='pit'
                else:self.powder-=params['target_count'];self.solid+=params['target_count']
                return {'phase':'done'}
        c=Client();result,_=recover(c,{'phase':'waiting','detail':'支撑面发生变化'},state(100,20),[1,61,1],'Block{minecraft:grass_block}[snowy=false]',POWDER,SOLID,8,prepare=lambda expected:setattr(c,'pose','stand'))
        self.assertEqual('done',result['phase']);self.assertEqual([1,5],c.actions)
        self.assertEqual((92,28),(c.powder,c.solid))
    def test_drop_arriving_during_scan_is_counted_without_replaying_powder(self):
        class Client:
            scanned=False;actions=[]
            def status(self):return state(92,28 if self.scanned else 27)
            def request(self,op,**params):
                self.actions.append(op)
                if op!='scan':raise AssertionError('No more powder may be placed')
                self.scanned=True
                return {'blocks':[{'pos':[1,61,1],'state':'Block{minecraft:dirt}','solid':True}]}
        c=Client();result,_=recover(c,{'phase':'waiting','detail':'支撑面发生变化'},state(100,20),[1,61,1],'Block{minecraft:grass_block}[snowy=false]',POWDER,SOLID,8)
        self.assertEqual('done',result['phase']);self.assertEqual(['scan'],c.actions)
    def test_timeout_with_verified_partial_output_only_places_unspent_remainder(self):
        class Client:
            powder=93;solid=27;actions=[]
            def status(self):return state(self.powder,self.solid)
            def checked(self,*args,**kwargs):pass
            def request(self,op,**params):
                if op=='scan':return {'blocks':[{'pos':[1,61,1],'state':'Block{minecraft:dirt}','solid':True}]}
                self.actions.append(params['target_count']);self.powder-=params['target_count'];self.solid+=params['target_count'];return {'phase':'done'}
        c=Client();r,_=recover(c,{'phase':'waiting','detail':'服务器未确认挖除'},state(100,20),[1,61,1],'Block{minecraft:dirt}',POWDER,SOLID,8)
        self.assertEqual('done',r['phase']);self.assertEqual([1],c.actions);self.assertEqual((92,28),(c.powder,c.solid))
    def test_timeout_without_consumption_is_not_replayed(self):
        class Client:
            def status(self):return state(100,20)
            def request(self,op,**params):
                if op!='scan':raise AssertionError('No ambiguous placement replay')
                return {'blocks':[{'pos':[1,61,1],'state':'Block{minecraft:dirt}','solid':True}]}
        original={'phase':'waiting','detail':'服务器未确认放置'}
        self.assertEqual(original,recover(Client(),original,state(100,20),[1,61,1],'Block{minecraft:dirt}',POWDER,SOLID,8)[0])
    def test_unrelated_stop_does_not_restart_game_actions(self):
        class Client:
            def status(self):raise AssertionError('Do not treat a hostile pause as soil change')
        r={'phase':'waiting','detail':'concrete paused for health or nearby hostile'}
        self.assertEqual(r,recover(Client(),r,{},[1,61,1],'Block{minecraft:dirt}',POWDER,SOLID,8)[0])
if __name__=='__main__':unittest.main()
