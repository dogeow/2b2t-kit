from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest
from keeper_history_scope import load,matches
from test_librarian_duplicate_reset import DuplicateResetTest
class Tests(unittest.TestCase):
 def fixture(self,root,name='minecraft:fire_aspect',level=2):
  args=DuplicateResetTest().fixture(name,level);m,t,locked,proofs,state=args;proof=proofs[name];proof.update(world_session='old',immutable_quote_result='old-owner/quote/result.json');quote=proof['merchant'];quote.update(protocol=1,owned=True,owner_task='old-task',observation_scope='current_server_received_merchant_menu_not_trade_completion')
  state.update(world_session='new',server='simpcraft.com',dimension='minecraft:overworld',account_name='likunyan');context=dict(connected=True,world_session='old',server='simpcraft.com:25565',dimension='minecraft:overworld',account_name='likunyan');owner=Path(root)/'old-owner';(owner/'quote').mkdir(parents=True);(owner/'actual-before.json').write_text(json.dumps(context));(owner/'quote/result.json').write_text(json.dumps({'world_session':'old','phase':'done','menu':{'merchant':quote}}));return args,proof,context
 def test_exact_historical_quote_is_bound_without_rewriting_or_new_attestation(self):
  from librarian_duplicate_reset import reset_allowed
  with tempfile.TemporaryDirectory()as d:
   args,p,ctx=self.fixture(d);old=deepcopy(p);cert=load(d,p,args[-1]);self.assertTrue(matches(cert,p,args[-1]));self.assertEqual(old,p);self.assertFalse(reset_allowed(*args));self.assertTrue(reset_allowed(*args,keeper_history_scopes={'minecraft:fire_aspect':cert}))
 def test_another_server_dimension_account_or_original_world_cannot_rebase_history(self):
  for k,v in [('server','other.example'),('dimension','minecraft:the_nether'),('account_name','another'),('world_session','wrong')]:
   with tempfile.TemporaryDirectory()as d:
    args,p,ctx=self.fixture(d);ctx[k]=v;(Path(d)/'old-owner/actual-before.json').write_text(json.dumps(ctx));self.assertIsNone(load(d,p,args[-1]))
 def test_changed_or_pending_quote_cannot_supply_history(self):
  for mode in ['pending','different_quote','unowned','unpaid','wrong_world']:
   with tempfile.TemporaryDirectory()as d:
    args,p,ctx=self.fixture(d)
    if mode=='pending':p['pending']='unknown'
    else:
     path=Path(d)/'old-owner/quote/result.json';r=json.loads(path.read_text())
     if mode=='different_quote':r['menu']['merchant']['trader_xp']=2
     if mode=='unowned':r['menu']['merchant']['owned']=False;p['merchant']['owned']=False
     if mode=='unpaid':r['menu']['merchant']['trader_xp']=0;p['merchant']['trader_xp']=0
     if mode=='wrong_world':r['world_session']='wrong'
     path.write_text(json.dumps(r))
    self.assertIsNone(load(d,p,args[-1]))
 def test_cached_certificate_does_not_authorize_changed_quote_or_current_scope(self):
  with tempfile.TemporaryDirectory()as d:
   args,p,ctx=self.fixture(d);cert=load(d,p,args[-1]);p['merchant']['trader_xp']=4;self.assertFalse(matches(cert,p,args[-1]))
  with tempfile.TemporaryDirectory()as d:
   args,p,ctx=self.fixture(d);cert=load(d,p,args[-1]);args[-1]['world_session']='another';self.assertFalse(matches(cert,p,args[-1]))
 def test_history_does_not_allow_missing_injured_baby_or_different_keeper(self):
  from librarian_duplicate_reset import reset_allowed
  for mode in ['missing','injured','baby','same_uid']:
   with tempfile.TemporaryDirectory()as d:
    args,p,ctx=self.fixture(d);cert=load(d,p,args[-1])
    if mode=='missing':args[-1]['loaded_villagers']['villagers']=[]
    if mode=='injured':args[-1]['loaded_villagers']['villagers'][0]['health']=19
    if mode=='baby':args[-1]['loaded_villagers']['villagers'][0]['is_baby']=True
    if mode=='same_uid':args[0]['villager_uuid']='keeper'
    self.assertFalse(reset_allowed(*args,keeper_history_scopes={'minecraft:fire_aspect':cert}))
 def test_native_seven_book_guard_still_requires_fresh_native_attestation(self):
  from librarian_duplicate_reset import reset_allowed
  with tempfile.TemporaryDirectory()as d:
   args,p,ctx=self.fixture(d,'minecraft:unbreaking',3);cert=load(d,p,args[-1]);self.assertIsNotNone(cert);self.assertFalse(reset_allowed(*args,keeper_history_scopes={'minecraft:unbreaking':cert}))
if __name__=='__main__':unittest.main()
