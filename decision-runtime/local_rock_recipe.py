"""Opt-in local vanilla rock synthesis on the existing material controller."""
from collections import Counter
import math
from types import SimpleNamespace

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_storage_index import records
from material_jobs.protocol import JobBlocked


def offer(backend, item, target):
    """A bounded planning hint only; every source still needs actual transfer."""
    name=(backend.profile.get('local_rock_recipes')or{}).get(item)
    if name is None:return None
    recipe=next((r for r in backend.crafting_catalog.recipes.get(item,[])if r.id==name),None)
    if recipe is None or any(len(opts)!=1 for _,opts in recipe.cells):return None
    ingredients=Counter(opts[0]for _,opts in recipe.cells)
    state=backend.latest;available=Counter(inventory_counts(state));held=available[item]
    depots={tuple(p)for p in backend.profile['depots']}
    client=SimpleNamespace(root=backend.root,status=lambda:state)
    for row in records(client,state):
        if not row.get('missing')and row.get('block_id')!='minecraft:ender_chest'and any(
                tuple(p)in depots for p in row.get('aliases',[row['pos']])):
            available.update(row.get('loose_counts',row['counts']))
    rounds=min((available[raw]//amount for raw,amount in ingredients.items()),default=0)
    count=min(target,held+16,available[item]+rounds*recipe.count)
    return count if count>held else None


def run(backend, client, item, target, out):
    name=(backend.profile.get('local_rock_recipes')or{}).get(item)
    if name is None:return None
    if type(target)is not int or not 1<=target<=2304:raise JobBlocked('Bounded absolute rock target required')
    path=out/'local-rock-recipe.json'
    if path.exists():
        import json
        previous_book=json.loads(path.read_text())
        if any(previous_book.get(k)!=v for k,v in {'world_session':client.world,'item':item,'target':target}.items()):
            raise JobBlocked('Previous local rock journal scope differs')
        if previous_book.get('pending'):raise JobBlocked('Previous local rock action unknown; no replay')
        if previous_book.get('complete'):
            if inventory_counts(client.status())[item]>=target:
                return {'phase':'done','local_recipe':name,'new_craft':False,'journal':str(path)}
            raise JobBlocked('Completed local rock journal cannot be replayed')
    if item not in ('minecraft:diorite','minecraft:andesite','minecraft:granite') or name!=item.split(':')[1]:
        raise JobBlocked('Local rock recipe registration is invalid')
    recipe=next((r for r in backend.crafting_catalog.recipes.get(item,[])if r.id==name),None)
    if recipe is None or not 1<=recipe.count<=4 or any(len(opts)!=1 for _,opts in recipe.cells):
        raise JobBlocked('Current installed game lacks an unambiguous registered rock recipe')
    ingredients=Counter(opts[0]for _,opts in recipe.cells)
    state=client.status();held=inventory_counts(state)
    depots={tuple(p)for p in backend.profile['depots']}
    available=Counter(held)
    for row in records(client,state):
        if row.get('missing') or row.get('block_id')=='minecraft:ender_chest':continue
        if any(tuple(p)in depots for p in row.get('aliases',[row['pos']])):
            available.update(row.get('loose_counts',row['counts']))
    needed=math.ceil(max(0,target-available[item])/recipe.count)
    if any(available[raw]<amount*needed for raw,amount in ingredients.items()):
        return None  # Ordinary registered collection remains available.
    book={'schema':1,'world_session':client.world,'item':item,'target':target,
          'recipe':name,'pending':None,'warehouse_inventory_credit':0,'receipts':[]}
    previous=getattr(backend,'resource_pipeline_context',None)
    backend.resource_pipeline_context={'item':item,'target_scope':'absolute_backpack_total',
                                      'world_session':client.world,'projection_key':backend.request.get('projection_key')}
    try:
        book['pending']='finished_fetch';write_json(path,book)
        receipt=backend.fetch({item:target});book['receipts'].append(receipt)
        if (receipt.get('phase')not in ('done','waiting') or receipt.get('pending')
                or str(receipt.get('code','')).lower()in ('wait_reconcile','wait_receipt','route_uncertain')):
            raise JobBlocked('Local finished-rock fetch outcome unknown')
        book['pending']=None;write_json(path,book)
        held=inventory_counts(client.status())
        if held[item]>=target:return {'phase':'done','local_recipe':name,'new_craft':False}
        rounds=math.ceil((target-held[item])/recipe.count)
        targets={raw:amount*rounds for raw,amount in ingredients.items()}
        book['pending']='ingredient_fetch';write_json(path,book)
        fetched=backend.fetch(targets);book['receipts'].append(fetched)
        if (fetched.get('phase')not in ('done','waiting') or fetched.get('pending')
                or str(fetched.get('code','')).lower()in ('wait_reconcile','wait_receipt','route_uncertain')):
            raise JobBlocked('Local rock ingredient fetch outcome unknown')
        before=inventory_counts(client.status())
        book['pending']=None;write_json(path,book)
        if any(before[raw]<amount for raw,amount in targets.items()):
            return {'phase':'waiting','code':'WAIT_LOCAL_RECIPE_SOURCE','safe_to_leave':True,
                    'detail':'本地配方原料实际取出后不足，保留已有材料'}
        book.update(pending='craft',before=dict(before));write_json(path,book)
        original=backend.crafting_catalog.recipes[item]
        backend.crafting_catalog.recipes[item]=[recipe]
        try:result=backend.craft({item:target})
        finally:backend.crafting_catalog.recipes[item]=original
        after=inventory_counts(client.status());gain=after[item]-before[item]
        if (result.get('phase')!='done' or gain!=rounds*recipe.count or after[item]<target
                or any(before[raw]-after[raw]!=amount for raw,amount in targets.items())):
            raise JobBlocked('Local rock recipe output or ingredient conservation unproved')
        book.update(pending=None,complete=True,after=dict(after),produced=gain);write_json(path,book)
        return {'phase':'done','local_recipe':name,'produced':gain,'inventory_total':after[item],
                'journal':str(path),'recipe_conservation_verified':True}
    finally:backend.resource_pipeline_context=previous
