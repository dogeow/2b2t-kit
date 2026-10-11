"""Store registered surplus at known depots before a quarry visit; never discard."""
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .protocol import JobBlocked

ALLOWED = {'minecraft:'+name for name in ('wheat_seeds','glass_bottle','mud_bricks',
           'dirt','grass_block','coarse_dirt','rotten_flesh','nautilus_shell')}


def run(backend):
    cfg=backend.profile.get('quarry_inventory_staging')or{}
    if cfg.get('authorized')is not True:return {'phase':'done','prepared':False}
    minimum=cfg.get('minimum_empty_slots');reserves=cfg.get('reserves')
    if (type(minimum)is not int or not 4<=minimum<=10 or not isinstance(reserves,dict)
            or not reserves or any(i not in ALLOWED or type(n)is not int or not 0<=n<=2304
                                  for i,n in reserves.items())
            or reserves.get('minecraft:wheat_seeds',32)<32):
        raise JobBlocked('采坑周转空间登记无效，未存放物品')
    c=backend.ensure_client();state=c.status()
    rows=[r for r in state.get('inventory',[])if 0<=r.get('slot',-1)<36]
    if len(rows)!=36 or {r.get('slot')for r in rows}!=set(range(36)):
        raise JobBlocked('完整背包未确认，未存放物品')
    free=sum(not r.get('count',0)for r in rows)
    if free>=minimum:return {'phase':'done','prepared':True,'free_slots':free}
    before=dict(inventory_counts(state));protected=set(backend.request.get('targets',{}))
    deposit={i:n for i,n in reserves.items()if i not in protected and before.get(i,0)>n}
    if not deposit:return {'phase':'waiting','code':'WAIT_WORKSPACE','detail':'登记周转料不足，保留当前背包'}
    from material_storage_index import select_destinations
    from material_depots import exchange
    route=select_destinations(c,backend.profile['depots'],deposit)
    if not route['positions']:return {'phase':'waiting','code':'WAIT_WORKSPACE','detail':'已记录仓库没有存放空间'}
    with backend.action('quarry_inventory_staging')as(c,out):
        path=Path(out)/'quarry-workspace.json'
        if path.exists():raise JobBlocked('原存放回执必须保留，不重放')
        book={'before':before,'deposit_targets':deposit,'pending':'deposit','complete':False,
              'local_storage_search':route,'discarded_items':0}
        write_json(path,book)
        backend.prepare_travel();backend.stage_near_base(route['positions'])
        receipt=exchange(c,route['positions'],deposit=deposit)
        after=inventory_counts(c.status())
        if (receipt.get('complete')is not True or any(after.get(i,0)!=n for i,n in deposit.items())
                or any(after.get(i,0)!=n for i,n in before.items()if i not in deposit)):
            raise JobBlocked('采坑存放与物资预留未完整确认，保留原回执')
        free=sum(not r.get('count',0)for r in c.status()['inventory']if 0<=r.get('slot',-1)<36)
        book.update(pending=None,complete=True,after=dict(after),exchange=receipt,free_slots=free)
        write_json(path,book)
        return {'phase':'done'if free>=minimum else'waiting',
                'code':'WORKSPACE_READY'if free>=minimum else'WAIT_WORKSPACE',
                'prepared':free>=minimum,'free_slots':free,'discarded_items':0,
                'stored':{i:before[i]-after.get(i,0)for i in deposit}}
