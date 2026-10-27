"""Weave exact banner layers using current vanilla loom options and input balances."""
from pathlib import Path
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from material_plan import inventory_counts


def exact_banner(row,item,layers):
    return row.get('item')==item and row.get('count')==1 and row.get('banner_patterns')==layers


def weave(client,item,layers,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if not item.endswith('_banner')or not isinstance(layers,list)or not 1<=len(layers)<=6:
        raise ValueError('One banner and a finite original layer sequence are required')
    initial=checkpoint();menu=initial['menu'];menu_id=menu['id']
    if (menu['type']!='LoomMenu'or not menu.get('material_owned')or menu['cursor']['count']
            or any(r['count']for r in menu['slots'][:4])):
        raise RuntimeError('Current owned clear loom required')
    session=InventorySession(client);prefix=[];book={'world_session':client.world,'menu_id':menu_id,'banner':item,'wanted_layers':layers,'steps':[],'pending':None,'complete':False}
    path=out/'loom.json'
    def save():write_json(path,book)
    def current():
        q=checkpoint();m=q['menu']
        if m['id']!=menu_id or m['type']!='LoomMenu'or not m.get('material_owned'):raise RuntimeError('Original owned loom changed')
        return q
    save()
    for i,layer in enumerate(layers):
        if set(layer)!={'pattern','color'}or not layer['pattern'].startswith('minecraft:'):raise ValueError('Exact pattern and dye color required')
        q=current();before=inventory_counts(q);m=q['menu'];dye='minecraft:'+layer['color']+'_dye'
        source=next((r for r in m['slots'][4:]if exact_banner(r,item,prefix)),None)
        if source is None or before[dye]<1:raise RuntimeError('Actual prefix banner or dye missing; no input clicks sent')
        if any(r['count']for r in m['slots'][:4])or m['cursor']['count']:raise RuntimeError('Loom inputs are not empty')
        book['pending']={'layer':i,'kind':'one_banner_and_dye_input'};save()
        q=session.place_cell(q,source,0,1)
        q=session._wait(q,menu_id,lambda m:exact_banner(m['slots'][0],item,prefix)and not m['cursor']['count'],'loom_banner_input',confirmations=2,fresh=True)
        source=next((r for r in q['menu']['slots'][4:]if r['item']==dye and r['count']>=1),None)
        if source is None:raise RuntimeError('Loom dye source changed')
        q=session.place_cell(q,source,1,1)
        q=session._wait(q,menu_id,lambda m:exact_banner(m['slots'][0],item,prefix)and m['slots'][1]['item']==dye and m['slots'][1]['count']==1 and not m['cursor']['count'],'loom_dye_input',confirmations=2,fresh=True)
        info=q['menu']['processing'];choices=[r for r in info['options']if r['key']==layer['pattern']]
        if len(choices)!=1:raise RuntimeError('Original pattern unavailable in actual loom options; no selection sent')
        inputs=[{'item':r['item'],'count':r['count'],**({'banner_patterns':r.get('banner_patterns')}if n==0 else{})}for n,r in enumerate(q['menu']['slots'][:3])]
        book['pending']={'layer':i,'kind':'one_vanilla_pattern_selection','pattern':layer['pattern'],'inputs':inputs};save()
        reply=client.checked('processing_menu_select',menu_id=menu_id,button=choices[0]['button'],expected_option=layer['pattern'],expected_selected=info['selected'],expected_inputs=inputs)
        write_json(out/('%02d-select-native.json'%i),reply);wanted=prefix+[layer]
        q=session._wait(client.status(),menu_id,lambda m:exact_banner(m['slots'][3],item,wanted)and not m['cursor']['count'],'loom_exact_preview',confirmations=2,fresh=True)
        book['pending']={'layer':i,'kind':'one_output_quick_move','wanted_layers':wanted};save()
        q=session.click(q,3,kind='quick_move')
        q=session._wait(q,menu_id,lambda m:not any(r['count']for r in m['slots'][:4])and not m['cursor']['count']and sum(exact_banner(r,item,wanted)for r in m['slots'][4:])==1,'loom_output_balance',confirmations=2,fresh=True)
        now=inventory_counts(q)
        if now[dye]!=before[dye]-1 or now[item]!=before[item]:raise RuntimeError('Loom dye or banner count differs; no output replay')
        prefix=wanted;book['pending']=None;book['steps'].append({'layer':i,'actual_layers':prefix,'dye_used':1});save()
        print('LOOM_LAYER',i,layer,flush=True)
    book.update(complete=True,actual_layers=prefix);save();return book
