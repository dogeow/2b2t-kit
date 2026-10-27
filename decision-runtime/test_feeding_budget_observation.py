import copy,unittest
from feeding_budget_observation import accounted_budget
class FoodBudgetTests(unittest.TestCase):
 def fixture(self):
  command={'action':'feed_village_founders','quotas':{'adult':2}};rows=[];events=[]
  for i,uid in enumerate(['adult','baby']):
   rows.append({'target':'adult','actual_collector':uid,'debit_times':[100+i*10,101+i*10],'native_request':str(i),'server_receipt':{'kind':'pickup_entities_unresolved','source_join':'fresh_same_world_generation_item_id_uuid','source_entity_id':i,'amount':1,'collector':{'uuid':uid,'type':'minecraft:villager'},'joined_source':{'id':i,'uuid':'drop'+str(i),'type':'minecraft:item','stack':{'item':'minecraft:bread','count':1}}}})
   events.append({'request_id':str(i),'world_session':'w','params':{'task_session':'t','expected_uuid':'adult'},'op':'villager_bread_drop','phase':'done','inventory_delta':{'minecraft:bread':-1},'health_before':20,'health_after':20,'revision_after':8})
  result={'world_session':'w','required':command['quotas'],'complete':False,'pending':None,'pending_food':None,'receipts':rows,'delivered':{'adult':1},'other_villager_deliveries':{'baby':1},'remaining':{'adult':1},'bread_actual':1};state={'inventory':[{'slot':0,'item':'minecraft:bread','count':1}],'last_request':'1','control_revision':8,'health':20,'screen':'','manual_movement':False,'movement_keys':{}};return command,result,events,state
 def test_baby_pickup_is_accounted_but_not_promoted_to_an_adult_quota(self):self.assertTrue(accounted_budget(*self.fixture(),'w','t'))
 def test_missing_duplicate_or_unsettled_receipts_remain_blocked(self):
  for mode in ['pending','missing','duplicate','adult_credit','stock','native','world','keys']:
   with self.subTest(mode=mode):
    c,r,e,s=copy.deepcopy(self.fixture())
    if mode=='pending':r['pending_food']={'uuid':'x'}
    if mode=='missing':r['receipts'].pop()
    if mode=='duplicate':r['receipts'][1]['server_receipt']['joined_source']['uuid']='drop0'
    if mode=='adult_credit':r['delivered']['adult']=2
    if mode=='stock':r['bread_actual']=0
    if mode=='native':e[1]['phase']='waiting'
    if mode=='world':e[1]['world_session']='other'
    if mode=='keys':s['movement_keys']['forward']=True
    self.assertFalse(accounted_budget(c,r,e,s,'w','t'))
if __name__=='__main__':unittest.main()
