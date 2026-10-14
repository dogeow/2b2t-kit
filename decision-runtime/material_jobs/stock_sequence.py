"""Explicit stock preparation through the existing native task API, then one map.

This observer never drives a second action controller or retries a submitted
start. Each next task requires real inventory and the prior native task's
confirmed control release. Unknown starts and player task changes stay recorded.
"""
import argparse
import json
from pathlib import Path
import time

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_plan import inventory_counts
from material_task_client import MaterialTaskClient
from .projection_continuation import run as continue_projection


def task_observation(state, reply, previous_id, item, count):
    task=state.get('material_task')or{}
    expected=reply['material_task']['id']
    if task.get('id')!=expected:
        # A start acknowledgement can precede the next status publication.
        # Only the exact previous task gets this short read-only grace period.
        if (task.get('id')==previous_id and type(state.get('time'))is int
                and type(reply.get('observed_at'))is int
                and state['time']<=reply['observed_at']+3000):
            return 'propagating'
        raise RuntimeError('Native material task changed; yield to current player work')
    if task.get('state')in('blocked','failed','cancelled'):
        raise RuntimeError(task.get('detail')or'Native stock task did not complete')
    if task.get('state')=='completed' and task.get('occupied')is False and task.get('process_alive')is False:
        rows=state.get('inventory')
        if (not isinstance(rows,list) or len(rows)!=43
                or {r.get('slot')for r in rows}!=set(range(43))
                or inventory_counts(state).get(item,0)<count):
            raise RuntimeError('Native task completion lacks exact actual carried target')
        return 'confirmed'
    # The host polls the progress file every500ms. A worker can exit between
    # polls while its occupied handle still awaits host reap/final-state read.
    # That is control cleanup, never permission to start the next task.
    if (task.get('process_alive')is False and task.get('occupied')is not True
            and task.get('state') not in ('completed','paused')):
        raise RuntimeError('Native stock process stopped; retain its receipts')
    return 'waiting'


def run(root, plan, request, out):
    if (not isinstance(plan,list) or not 1<=len(plan)<=16
            or any(not isinstance(r,dict)or set(r)!={'item','count'}
                   or not isinstance(r['item'],str)or not r['item'].startswith('minecraft:')
                   or type(r['count'])is not int or not 1<=r['count']<=2304 for r in plan)):
        raise ValueError('Explicit bounded stock sequence required')
    root=Path(root);out=Path(out);out.mkdir(exist_ok=False)
    first=read_fresh(root);world=first['world_session']
    book={'schema':1,'world_session':world,'plan':plan,'completed_steps':[],
          'pending':None,'map_complete':False,'starts_replayed':False}
    write_json(out/'state.json',book)

    def current():
        s=read_fresh(root)
        if (s.get('connected')is not True or s.get('world_session')!=world
                or s.get('safety_hold',{}).get('active')
                or s.get('projection_selection',{}).get('key')!=request['projection_key']):
            raise RuntimeError('Original world, selected map or health safety changed')
        return s

    try:
        for index,step in enumerate(plan):
            s=current()
            if s.get('material_task',{}).get('occupied'):
                raise RuntimeError('Another native task still owns the player')
            while s.get('manual_movement')or s.get('screen'):
                time.sleep(.25);s=current()
            if s.get('health')!=20 or s.get('food',0)<18:
                raise RuntimeError('Stock preparation needs current healthy work reserve')
            previous=(s.get('material_task')or{}).get('id')
            book['pending']={'stage':'start','index':index,**step,'previous_task':previous}
            write_json(out/'state.json',book)
            reply=MaterialTaskClient(root).start_item(step['item'],step['count'])
            book['pending'].update(stage='native_task_wait',reply=reply)
            write_json(out/'state.json',book)
            print('NATIVE_STOCK_TASK',reply['material_task']['id'],step['item'],step['count'],flush=True)
            while True:
                s=current();phase=task_observation(s,reply,previous,step['item'],step['count'])
                if phase=='confirmed':break
                time.sleep(.25)
            proof={'index':index,**step,'task_id':reply['material_task']['id'],
                   'time':s['time'],'world_session':world,'health':s['health'],'food':s['food'],
                   'actual_carried_count':inventory_counts(s)[step['item']],
                   'native_process_and_control_released':True,'map_placement_credit':0}
            write_json(out/('stock-%02d.json'%index),proof)
            book['completed_steps'].append(proof);book['pending']=None
            write_json(out/'state.json',book)
        result=continue_projection(root,request,out/'full-map')
        book['map_result']=result;book['construction_complete']=result.get('state')=='completed'
        book['map_complete']=False;book['final_filled_map_verification_required']=True
        write_json(out/'result.json',book);return book
    except Exception as error:
        book.update(state='blocked',detail=str(error),old_native_receipts_retained=True)
        write_json(out/'result.json',book)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('automation','plan','request','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.automation,json.loads(a.plan.read_text()),json.loads(a.request.read_text()),a.out)

if __name__=='__main__':main()
