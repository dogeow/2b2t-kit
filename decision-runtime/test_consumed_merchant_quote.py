from pathlib import Path
import json,unittest
from consumed_merchant_quote import observable
class Tests(unittest.TestCase):
 def fixture(self):
  f=json.loads((Path(__file__).parent/'test_fixtures/consumed-merchant-quote.json').read_text());return [f[k]for k in ['command','error','previous','state','event']]+[f['state']['world_session'],f['state']['supervision_lease']['job_session']]
 def okay(self,a,**kw):return observable(*a,journal_exists=kw.get('journal_exists',False),unknown_exists=kw.get('unknown_exists',False))
 def test_completed_trade_with_returnable_payment_is_observable(self):self.assertTrue(self.okay(self.fixture()))
 def test_any_new_transaction_or_unknown_native_input_remains_fenced(self):
  self.assertFalse(self.okay(self.fixture(),journal_exists=True));self.assertFalse(self.okay(self.fixture(),unknown_exists=True));a=self.fixture();a[2]['pending']='output_click';self.assertFalse(self.okay(a))
 def test_changed_quote_or_inventory_is_not_admitted(self):
  a=self.fixture();a[3]['menu']['merchant']['opening_request_id']='other';self.assertFalse(self.okay(a))
  a=self.fixture();a[3]['menu']['slots'][0]['count']-=1;self.assertFalse(self.okay(a))
 def test_wrong_last_input_or_owner_is_rejected(self):
  a=self.fixture();a[4]['request_id']='new';self.assertFalse(self.okay(a))
  a=self.fixture();a[3]['menu']['merchant']['owner_task']='other';self.assertFalse(self.okay(a))
if __name__=='__main__':unittest.main()
