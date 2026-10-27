"""One bounded surface-zombie observation through the existing Kit action owner.

This never sleeps until a guessed clock tick. Bright or unknown current sky
returns control for other work; finding a mob still grants no capture credit.
"""
from village_world_time import read as daylight

def observe(builder,low,high):
 state=builder.check();sky=daylight(builder.root,state)
 result={'complete':True,'world_session':state['world_session'],'daylight':sky,'candidates':[],
         'capture_credit':0,'name_credit':0,'scan_dispatched':False}
 if sky is None:return {**result,'next':'verify_daylight_or_do_other_work'}
 if sky['period']!='dark':return {**result,'next':'do_other_work_while_bright'}
 frame,_=builder.scan(low,high)
 if frame.get('world_session')!=state['world_session']or frame.get('unloaded_chunks'):
  raise RuntimeError('Surface mob survey crossed world or unloaded cells')
 result.update(scan_dispatched=True,scene=frame,daylight_after=daylight(builder.root,builder.check()))
 result['candidates']=[e for e in frame['scan_entities']if e.get('type')=='minecraft:zombie'
   and e.get('alive')is True and e.get('health')==20 and e.get('is_baby')is False
   and e.get('has_custom_name')is False and low[1]<=e['pos'][1]<=high[1]+1]
 result['next']='fresh_target_validation'if result['candidates']else'do_other_work_or_bound_another_observation'
 return result
