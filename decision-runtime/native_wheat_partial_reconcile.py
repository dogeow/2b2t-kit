"""Retire a stopped partial visit only when every sent crop action ACKed.

The original visit remains incomplete. Current mature crops may have regrown;
this proof never identifies or replays an alleged remaining per-cell subset.
"""
from copy import deepcopy
from math import prod
from material_plan import inventory_counts
from potato_farm import _properties
from native_wheat_zero_input_disconnect import HOST_HASHES

CLASSIFICATION='all_sent_wheat_actions_acknowledged_partial_visit'
REASON='native planter stopped: 已停止：原耕地内没有可种或可收位置；不翻耕草地、泥土或覆盖装饰'

def prove(book,receipt,error,frames,hashes):
    pending=book.get('pending')or{};cells=book.get('cells')or[];world=book.get('world_session')
    batch=receipt.get('planter_material_batch')or{};n=batch.get('harvest_sent');lease=receipt.get('supervision_lease')or{}
    if(hashes!=HOST_HASHES or not world or book.get('complete')is not False or book.get('inventory_credit')!=0
       or pending.get('operation')!='planter_wheat_batch' or pending.get('soils')!=cells
       or not 1<=len(cells)<=16 or len({tuple(p)for p in cells})!=len(cells)
       or receipt.get('phase')!='waiting' or receipt.get('detail')!=REASON
       or receipt.get('world_session')!=world or not receipt.get('id')
       or error.get('last_request')!=receipt['id'] or error.get('error')!=REASON
       or 'native_inflight'not in error or error['native_inflight']is not None
       or 'unconfirmed_native_request'not in error or error['unconfirmed_native_request']is not None
       or batch.get('protocol')!=1 or batch.get('total')!=len(cells)
       or batch.get('grain_before')!=book['inventory_before'].get('minecraft:wheat',0)
       or type(n)is not int or not 0<n<len(cells)
       or any(type(batch.get(k))is not int or batch[k]!=n for k in('removed_confirmed','plant_sent','replanted_confirmed'))
       or batch.get('cells_server_confirmed')is not False
       or {tuple(p)for p in batch.get('crop_positions',[])}!={(p[0],p[1]+1,p[2])for p in cells}
       or len(batch.get('crop_positions',[]))!=len(cells)
       or lease.get('kind')!='materials' or not lease.get('id')or not lease.get('job_session')
       or lease.get('world_session')!=world or len(frames)!=2):
        raise RuntimeError('Stopped partial wheat inputs are not all independently acknowledged')
    scope=book['scope'];volume=prod(b-a+1 for a,b in zip(scope['scan_min'],scope['scan_max']))
    last=receipt['time'];stock=None;times=[]
    for f in frames:
        current=dict(inventory_counts(f));rows={tuple(r['pos']):r for r in f.get('blocks',[])}
        if(f.get('phase')!='done' or f.get('connected')is not True or f.get('world_session')!=world
           or f.get('health')!=20 or f.get('screen')!='' or f.get('manual_movement')is not False
           or f.get('planter_active')is not False or f.get('navigating')is not False or f.get('guard_busy')is not False
           or f.get('native_material_busy') or(f.get('safety_hold')or{}).get('active')or f.get('health_recovery_hold')
           or f.get('planter_material_batch')!=batch or f.get('runtime_generation')!=receipt.get('runtime_generation')
           or any((f.get('supervision_lease')or{}).get(k)!=lease.get(k)for k in('id','kind','job_session','world_session'))
           or f.get('control_revision')!=receipt.get('control_revision')
           or f.get('scan_start_revision')!=receipt.get('control_revision')or f.get('scan_end_revision')!=receipt.get('control_revision')
           or f.get('scan_cells_read')!=volume or f.get('scan_total_cells')!=volume or f.get('unloaded_chunks',0)
           or type(f.get('time'))is not int or f['time']<=last or f.get('menu',{}).get('cursor',{}).get('count')!=0
           or stock is not None and current!=stock
           or current.get('minecraft:wheat',0)<book['inventory_before'].get('minecraft:wheat',0)
           or current.get('minecraft:wheat_seeds',0)<4
           or {k:v for k,v in current.items()if k not in('minecraft:wheat','minecraft:wheat_seeds')}
              !={k:v for k,v in book['inventory_before'].items()if k not in('minecraft:wheat','minecraft:wheat_seeds')}
           or any(_properties(rows.get(tuple(p),{}),'farmland','moisture',7)is None
                  or _properties(rows.get((p[0],p[1]+1,p[2]),{}),'wheat','age',7)is None for p in cells)):
            raise RuntimeError('Current stopped crop scope or conserved inventory is unproved')
        last=f['time'];stock=current;times.append(last)
    return {'schema':1,'classification':CLASSIFICATION,'request_id':receipt['id'],'world_session':world,
            'host_hashes':deepcopy(hashes),'original_pending':deepcopy(pending),'original_cells':deepcopy(cells),
            'original_scope_complete':False,'all_sent_actions_acknowledged':True,'confirmed_crop_cycles':n,
            'inventory_after':stock,'actual_grain_gain':stock.get('minecraft:wheat',0)-book['inventory_before'].get('minecraft:wheat',0),
            'observed_times':times,'original_request_replayed':False,'remaining_cells_not_inferred_from_growth':True}

def record(book,proof):
    if(book.get('complete')is not False or proof.get('schema')!=1
       or proof.get('classification')!=CLASSIFICATION or proof.get('host_hashes')!=HOST_HASHES
       or proof.get('world_session')!=book.get('world_session')or proof.get('original_pending')!=book.get('pending')
       or proof.get('original_cells')!=book.get('cells')or(book.get('pending')or{}).get('operation')!='planter_wheat_batch'
       or proof.get('original_scope_complete')is not False or proof.get('all_sent_actions_acknowledged')is not True
       or proof.get('original_request_replayed')is not False):raise RuntimeError('Original partial wheat journal changed')
    result=deepcopy(book);result.update(pending=None,known_partial_stop=True,partial_stop_proof=deepcopy(proof),
                                     partial_inventory_credit=proof['actual_grain_gain'])
    return result

def reconciled(book):
    proof=book.get('partial_stop_proof')or{}
    return (book.get('known_partial_stop')is True and book.get('pending')is None
            and proof.get('schema')==1 and proof.get('classification')==CLASSIFICATION and proof.get('host_hashes')==HOST_HASHES
            and proof.get('world_session')==book.get('world_session')and proof.get('original_cells')==book.get('cells')
            and proof.get('all_sent_actions_acknowledged')is True and proof.get('original_scope_complete')is False
            and proof.get('original_request_replayed')is False and bool(proof.get('request_id'))
            and type(proof.get('confirmed_crop_cycles'))is int and 0<proof['confirmed_crop_cycles']<len(book.get('cells',[]))
            and (proof.get('original_pending')or{}).get('operation')=='planter_wheat_batch'
            and (proof.get('original_pending')or{}).get('soils')==book.get('cells'))
