"""Use a worthwhile carried smelting input batch before collecting more raw rock.

This is a planning offer, never source/fuel transfer or placement credit.
"""


def offer(backend,item,final_count):
    if backend.request.get('mode')!='projection' or not backend.request.get('flat_map'):
        return None
    if type(final_count)is not int or final_count<1:return None
    rows=(getattr(backend,'latest',None)or{}).get('inventory',[])
    if len(rows)!=43 or {r.get('slot')for r in rows}!=set(range(43)):return None
    stock={}
    for row in rows:
        if (set(row)=={'slot','item','count','max_stack'} and row['slot']<36
                and type(row['count'])is int and row['count']>0):
            stock[row['item']]=stock.get(row['item'],0)+row['count']
    held=stock.get(item,0);remaining=final_count-held
    if remaining<=0:return None
    minimum=backend.profile.get('minimum_projection_trip_stack',64)
    if type(minimum)is not int or not 3<=minimum<=64:return None
    bank=backend.profile.get('furnace_positions',[])
    if not isinstance(bank,list)or not 1<=len(bank)<=16:return None
    options=[]
    for recipe in backend.catalog.recipes.get(item,[]):
        spec=backend.catalog.smelting.get(recipe.id)
        if not isinstance(spec,dict)or recipe.count!=1 or len(recipe.cells)!=1:continue
        ticks=spec.get('cooking_ticks_per_recipe')
        if type(ticks)is not int or ticks<1:continue
        capacity=len(bank)*min(64,102400//ticks)
        for source in recipe.cells[0][1]:
            if source==item:continue
            amount=min(remaining,stock.get(source,0),capacity)
            if amount>=min(minimum,remaining):options.append(held+amount)
    return max(options)if options else None
