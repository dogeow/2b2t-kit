"""Cut an exact loaded input batch with current vanilla recipe options and balances."""
from pathlib import Path
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from material_plan import inventory_counts


def exact_yield(before,after,source,amount,output,per):
    return (source!=output and after.get(source,0)==before.get(source,0)-amount
            and after.get(output,0)==before.get(output,0)+amount*per)


def cut(client,source,amount,output,per,out,checkpoint):
    if (type(amount)is not int or not 1<=amount<=64 or type(per)is not int or not 1<=per<=2
            or source==output or not source.startswith('minecraft:')or not output.startswith('minecraft:')):
        raise ValueError('Finite ordinary stonecutter inputs and exact output yield required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);q=checkpoint();m=q['menu'];menu_id=m['id']
    if m['type']!='StonecutterMenu'or not m.get('material_owned')or m['cursor']['count']or any(r['count']for r in m['slots'][:2]):
        raise RuntimeError('Current owned clear stonecutter required')
    before=inventory_counts(q);stack=next((r for r in m['slots'][2:]if r['item']==source and r['count']>=amount),None)
    if stack is None:raise RuntimeError('One actual complete input stack required')
    room=sum(output_limit if not r['count']else max(0,output_limit-r['count'])if r['item']==output else 0
             for r in m['slots'][2:]for output_limit in(64,))
    if room<amount*per:raise RuntimeError('No verified output capacity before cutting')
    book={'world_session':client.world,'menu_id':menu_id,'source':source,'input_amount':amount,'output':output,'per_input':per,'inventory_before':dict(before),'pending':'one_exact_input_batch','complete':False};path=out/'stonecutter.json';write_json(path,book)
    session=InventorySession(client);q=session.place_cell(q,stack,0,amount)
    q=session._wait(q,menu_id,lambda m:m['material_owned']and m['slots'][0]['item']==source and m['slots'][0]['count']==amount and not m['cursor']['count'],'stonecutter_exact_input',confirmations=2,fresh=True)
    info=q['menu']['processing'];choices=[r for r in info['options']if r['key']==output and r['count']==per]
    if len(choices)!=1:raise RuntimeError('Exact desired yield absent from current stonecutter options')
    book['pending']='one_vanilla_recipe_selection';write_json(path,book)
    reply=client.checked('processing_menu_select',menu_id=menu_id,button=choices[0]['button'],expected_option=output,expected_selected=info['selected'],expected_inputs=[{'item':source,'count':amount}]);write_json(out/'native-select.json',reply)
    q=session._wait(client.status(),menu_id,lambda m:m['slots'][1]['item']==output and m['slots'][1]['count']==per and m['slots'][0]['count']==amount and not m['cursor']['count'],'stonecutter_exact_preview',confirmations=2,fresh=True)
    book['pending']='one_output_quick_move';write_json(path,book);q=session.click(q,1,kind='quick_move')
    q=session._wait(q,menu_id,lambda m:not m['cursor']['count']and not any(r['count']for r in m['slots'][:2]),'stonecutter_consumed_batch',confirmations=2,fresh=True)
    now=inventory_counts(q)
    if not exact_yield(before,now,source,amount,output,per):raise RuntimeError('Actual cutting balance differs; never replay output click')
    book.update(complete=True,pending=None,inventory_after=dict(now));write_json(path,book);return book
