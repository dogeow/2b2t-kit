"""Exact observed equipment/books from an explicit Ender shulker."""
import json
from pathlib import Path
from anvil_enchant_preview import stack_key, enchantments
from material_jobs.protocol import server_key
from material_plan import inventory_counts
from packed_supplies import open_box, take_box, matching_count, workspace_requirement, PackedWorkspaceRequired


def take(client,profile_path,box_slot,expected):
    if isinstance(expected,list):
        from packed_equipment_batch import take as take_batch
        return take_batch(client,profile_path,box_slot,expected)
    if (type(box_slot)is not int or not 0<=box_slot<27 or expected.get('count')!=1
            or expected.get('max_stack')!=1 or not expected.get('item','').startswith('minecraft:')
            or any(k.endswith('_curse') for k in enchantments(expected))):
        raise ValueError('One exact uncursed unstackable equipment/book and explicit box slot required')
    profile=json.loads(Path(profile_path).read_text());initial=client.status()
    if (server_key(profile.get('server'))!=server_key(client.server)
            or profile.get('dimension')!=initial.get('dimension')):
        raise ValueError('Current registered Ender workspace required')
    space=workspace_requirement(initial)
    if space:raise PackedWorkspaceRequired(space)
    item=expected['item'];exact={item:expected};count=inventory_counts(initial)[item]
    qualified=matching_count(initial['inventory'],item,exact_stacks=exact)
    state=open_box(client,profile['ender_chest'],'ChestMenu');box=state['menu']['slots'][box_slot]
    found=(box.get('count')==1 and box.get('item','').endswith('shulker_box')
           and matching_count(box.get('contains',[]),item,exact_stacks=exact)>0)
    client.checked('close_menu')
    if not found:
        return {'complete':False,'reason':'Explicit source no longer contains the exact approved stack','box_withdrawn':False}
    result=take_box(client,profile['ender_chest'],profile['shulker_pad'],box_slot,
                    {item:count+1},exact_stacks=exact)
    final=client.status()
    if (not result or result.get('stage')!='returned' or inventory_counts(final)[item]!=count+1
            or matching_count(final['inventory'],item,exact_stacks=exact)!=qualified+1):
        raise RuntimeError('Exact equipment withdrawal or intact box return remains unconfirmed; no retry')
    return {'complete':True,'packed_transfer':result,'expected_stack':expected,
            'before':count,'after':count+1,'visible_identity':stack_key(expected)}
