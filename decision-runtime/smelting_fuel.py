"""Verified vanilla fuel facts and a finite, reservation-aware furnace plan.

Additional fuels are enabled only for the checked26.1.2 FuelValues class and
its actual item tags. Recipe-only fixtures/legacy catalogs retain coal behavior.
No game client, backend, model, click, crafting or source acquisition is created.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

COAL='minecraft:coal'
CHARCOAL='minecraft:charcoal'
FUEL_CLASS='net/minecraft/world/level/block/entity/FuelValues.class'
FUEL_CLASS_SHA256='848788c166499360d3662a643a05f977c131b670529c47a7d9cc1a852467b8c4'


class FuelCatalog:
    def __init__(self,jar):
        self.jar=Path(jar);self.durations={COAL:1600};self.wood=set()
        self.evidence={'kind':'legacy_coal_only','extra_fuels_verified':False}
        with zipfile.ZipFile(self.jar) as z:
            if FUEL_CLASS not in z.namelist():return
            raw=z.read(FUEL_CLASS);digest=hashlib.sha256(raw).hexdigest()
            version=json.loads(z.read('version.json')).get('id')
            if version!='26.1.2' or digest!=FUEL_CLASS_SHA256:
                raise ValueError('Unknown game FuelValues semantics; no alternative fuel inferred')
            tags={};digests={}
            def expand(name,ancestors=()):
                if name in ancestors or len(ancestors)>32:raise ValueError('Fuel tag cycle/depth exceeded')
                if name in tags:return tags[name]
                path='data/minecraft/tags/item/'+name.removeprefix('minecraft:')+'.json'
                b=z.read(path)
                if len(b)>100000:raise ValueError('Fuel tag exceeds bound')
                digests[path]=hashlib.sha256(b).hexdigest();result=set()
                for value in json.loads(b).get('values',[]):
                    if isinstance(value,dict):value=value['id']
                    if not isinstance(value,str):raise ValueError('Invalid fuel item tag')
                    if value.startswith('#'):result.update(expand(value[1:],ancestors+(name,)))
                    else:result.add(value)
                tags[name]=result;return result
            self.wood=(expand('minecraft:logs')|expand('minecraft:planks'))-expand('minecraft:non_flammable_wood')
            self.durations.update({item:300 for item in self.wood});self.durations[CHARCOAL]=1600
            # The exact checked FuelValues class adds BLAZE_ROD at12 base units.
            # This remains opt-in through a task fuel_allow_items declaration.
            self.durations['minecraft:blaze_rod']=2400
            self.evidence={'kind':'vanilla26.1.2_FuelValues','extra_fuels_verified':True,
                           'fuel_class_sha256':digest,'base_unit_ticks':200,'tag_sha256':digests}


def recipe_jar_for_client(client,explicit=None):
    """Locate existing configured/instance data; never create a game client."""
    if explicit is not None:return Path(explicit)
    owner=getattr(client,'owner',None)
    configured=getattr(owner,'profile',{}).get('recipe_jar') if owner is not None else None
    if configured:return Path(configured)
    root=getattr(client,'root',None)
    if isinstance(root,(str,Path)):
        root=Path(root)
        if len(root.parents)>=3:
            game=root.parents[2];candidate=game/(game.name+'.jar')
            if candidate.is_file():return candidate
    return None


def quantities(value):
    if value is None:return {}
    if not isinstance(value,dict) or len(value)>256:raise ValueError('Fuel quantities need a bounded item map')
    if any(not isinstance(i,str) or not re.fullmatch(r'minecraft:[a-z0-9_./-]+',i)
           or type(n) is not int or not 0<=n<=1000000 for i,n in value.items()):
        raise ValueError('Invalid actual fuel/keep quantity')
    return dict(value)


def policy(catalog,profile,recipe,client=None):
    """Task-declared fuel items override profile items; retained counts merge max."""
    keep={}
    owner=getattr(client,'owner',None)
    targets=getattr(owner,'request',{}).get('targets',{}) if owner is not None else {}
    for values in (profile.get('fuel_keep'),targets,recipe.get('fuel_keep')):
        for item,n in quantities(values).items():keep[item]=max(keep.get(item,0),n)
    declared=recipe.get('fuel_allow_items',profile.get('fuel_allow_items'))
    if declared is None:
        allowed=[i for i in (COAL,CHARCOAL) if i in catalog.durations]
    else:
        if (not isinstance(declared,list) or not 1<=len(declared)<=128
                or any(not isinstance(i,str) or i not in catalog.durations for i in declared)
                or len(set(declared))!=len(declared)):
            raise ValueError('Fuel allowlist contains unverified/unsupported items')
        allowed=list(declared)
    return keep,allowed


def select_fuels(catalog,stock,parts,cooking_ticks,source,output,keep=None,allowed=None):
    """Select one exact fuel item per furnace, preserving recipe/output stock.

    All shortages are real absolute backpack targets, never coal-equivalent
    counts for a wooden fuel. Nothing is dispatched until the full plan fits.
    """
    stock=quantities(stock);keep=quantities(keep)
    if (not isinstance(parts,list) or not 1<=len(parts)<=16
            or any(type(n) is not int or not 0<=n<=64 for n in parts)
            or not any(parts) or type(cooking_ticks) is not int or not 1<=cooking_ticks<=102400):
        raise ValueError('Fuel plan needs1..16 bounded furnaces and a verified cooking duration')
    allowed=list(allowed) if allowed is not None else [i for i in (COAL,CHARCOAL) if i in catalog.durations]
    if not allowed or len(set(allowed))!=len(allowed) or any(i not in catalog.durations for i in allowed):
        raise ValueError('Unknown/empty fuel selection')
    # Output fuel would destroy the carried goal or cause a charcoal self-cycle.
    allowed=[i for i in allowed if i!=output]
    if not allowed:raise ValueError('Requested output cannot be used as its own fuel')
    order=sorted(allowed,key=lambda i:(0 if i==COAL else 1 if i==CHARCOAL else 2 if i.endswith('_planks') else 3,allowed.index(i)))
    reserve=Counter(keep);reserve[source]+=sum(parts);reserve[output]=max(reserve[output],stock.get(output,0))
    free={i:max(0,stock.get(i,0)-reserve[i]) for i in order}
    spent=Counter();entries=[];missing=Counter();source_needed=sum(parts)
    if stock.get(source,0)<source_needed:missing[source]=source_needed
    for n in parts:
        if not n:entries.append(None);continue
        choices=[(item,math.ceil(n*cooking_ticks/catalog.durations[item])) for item in order]
        choices=[(i,count) for i,count in choices if count<=64]
        fitting=next(((i,count) for i,count in choices if free[i]>=count),None)
        if fitting is None:
            if not choices:raise ValueError('No allowed fuel fits one64-item fuel slot')
            item,count=min(choices,key=lambda row:(max(0,row[1]-free[row[0]]),order.index(row[0])))
            # Complete the hypothetical shortage plan for later furnaces too.
            missing[item]=max(missing[item],reserve[item]+spent[item]+count)
            free[item]=max(0,free[item]-count)
        else:
            item,count=fitting;free[item]-=count
        spent[item]+=count
        entries.append({'fuel_item':item,'fuel':count,'burn_ticks_per_fuel':catalog.durations[item],
                        'planned_fuel_ticks':count*catalog.durations[item],
                        'required_cooking_ticks':n*cooking_ticks})
    return {'ready':not missing,'entries':entries,'fuel_totals':dict(spent),
            'requirements':dict(missing),'retained_counts':dict(keep),
            'recipe_input_reserved':{source:source_needed},'output_fuel_excluded':output,
            'evidence':catalog.evidence}
