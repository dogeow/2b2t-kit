"""Choose a receiving slot; only plain server-quoted emeralds may stack."""
def choose(menu,offer):
    result=offer['result'];data=result.get('stack_data');item=result['item']
    plain=(item=='minecraft:emerald' and result.get('max_stack')==64
           and set(result)<= {'item','count','max_stack','stack_data'}
           and isinstance(data,dict)and set(data)<= {'id','count','components'}
           and data.get('id')==item and data.get('count',1)==result['count']
           and data.get('components',{})=={}
           and all(not cost.get('count')or cost['item']!=item for cost in (offer['cost_a'],offer['cost_b'])))
    rows=menu['slots'][3:]
    if plain:
        fits=[r for r in rows if set(r)=={'slot','item','count','max_stack'}
              and r['item']==item and r['max_stack']==64 and 0<r['count']<=64-result['count']]
        if fits:return dict(max(fits,key=lambda r:r['count']))
    return next((dict(r)for r in rows if not r['count']),None)
