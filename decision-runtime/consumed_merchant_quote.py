"""Observe a repeated-opening refusal without authorizing another purchase."""
from villager_trading import combined
from material_plan import quantities
DETAIL='Reopen this trader for a fresh server quote before another purchase; no selection sent'

def observable(command,error,previous,state,event,world,task,*,journal_exists,unknown_exists):
 menu=state.get('menu')or{};info=menu.get('merchant')or{};receipts=previous.get('receipts')or[]
 if not receipts:return False
 return(command.get('action')=='merchant_buy_one'and type(command.get('index'))is int
  and error.get('type')=='RuntimeError'and error.get('error')==DETAIL
  and error.get('native_inflight')is None and error.get('unconfirmed_native_request')is None
  and not journal_exists and not unknown_exists
  and previous.get('complete')is True and previous.get('pending')is None
  and previous.get('world_session')==state.get('world_session')==world
  and info.get('protocol')==1 and info.get('owned')is True and info.get('owner_task')==task
  and info.get('villager_uuid')==previous.get('uuid')and bool(previous.get('opening_request_id'))
  and info.get('opening_request_id')==previous['opening_request_id']
  and menu.get('type')=='MerchantMenu'and menu.get('id')==info.get('menu_id')
  and menu.get('cursor',{}).get('count')==0 and 0<=command['index']<len(info.get('offers',[]))
  and combined(state)==quantities(previous.get('after',{}))==quantities(previous.get('expected_after',{}))
  and error.get('last_request')==state.get('last_request')==receipts[-1].get('id')
  and event.get('request_id')==state.get('last_request')and event.get('phase')=='done'
  and event.get('world_session')==world and event.get('params',{}).get('task_session')==task
  and event.get('revision_after')==state.get('control_revision')
  and event.get('health_before')==event.get('health_after')==state.get('health')==20
  and state.get('manual_movement')is False and state.get('screen')=='MerchantScreen'
  and state.get('supervision_lease',{}).get('job_session')==task
  and not any(state.get(k)for k in ('navigating','native_material_busy','pending_scan')))
