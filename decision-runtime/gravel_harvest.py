"""Mine only exposed gravel away from water in a bounded work area.

Uses ordinary shovel mining and verifies each target and pickup. A falling-stack
torch shortcut is deliberately excluded until server timing can be verified.
"""

import argparse
import json
import time
from pathlib import Path

from drop_collection import collect_drop
from material_client import Handoff, MaterialClient
from shore_concrete import block_state, item_count

GRAVEL = 'minecraft:gravel'
FLINT = 'minecraft:flint'
WATER_BUFFER = 3


def dry_top_gravel(rows, pos):
    x, y, z = pos
    if block_state(rows, pos) != 'Block{minecraft:gravel}' or block_state(rows, [x, y+1, z]) != 'Block{minecraft:air}':
        return False
    return water_buffer_clear(rows,pos)


def water_buffer_clear(rows, pos):
    x, y, z = pos
    # Include diagonals and flowing/waterlogged blocks. Mining a shoreline
    # block can release water and wash the next drop away.
    return not any((row.get('fluid',False) or row['state'].startswith('Block{minecraft:water}'))
                   and max(abs(row['pos'][0]-x),abs(row['pos'][2]-z))<=WATER_BUFFER
                   and abs(row['pos'][1]-y)<=2 for row in rows)


def fresh_drops(before, after, pos):
    old = {e['uuid'] for e in before.get('entities', []) if e.get('type') == 'minecraft:item'}
    return [e for e in after.get('entities', []) if e.get('type') == 'minecraft:item'
            and e.get('uuid') not in old and e.get('stack', {}).get('item') in (GRAVEL, FLINT)
            and sum((a-b)**2 for a, b in zip(e['pos'], [v+.5 for v in pos])) <= 36]


def harvest(client, low, high, target_count, out):
    if target_count < 1 or target_count > 64:
        raise ValueError('A session harvests 1..64 gravel items')
    if any(a > b for a, b in zip(low, high)) or (high[0]-low[0]+1)*(high[1]-low[1]+1)*(high[2]-low[2]+1) > 2000:
        raise ValueError('Bounded observed gravel area required')
    start = client.status()
    if item_count(start, 'minecraft:diamond_shovel') != 1:
        raise RuntimeError('One verified diamond shovel is required')
    result = {'bounds': [list(low), list(high)], 'gravel_before': item_count(start, GRAVEL), 'blocks': []}
    blocked = set()
    while item_count(client.status(), GRAVEL) - result['gravel_before'] < target_count:
        scan = client.request('scan', min=[low[0]-WATER_BUFFER, low[1]-2, low[2]-WATER_BUFFER],
                              max=[high[0]+WATER_BUFFER, high[1]+2, high[2]+WATER_BUFFER], details=True)
        rows = scan['blocks']
        current = client.status()
        candidates = [(x,y,z) for x in range(low[0],high[0]+1) for y in range(high[1],low[1]-1,-1)
                      for z in range(low[2],high[2]+1) if (x,y,z) not in blocked and dry_top_gravel(rows,[x,y,z])]
        if not candidates:break
        candidates.sort(key=lambda p:(sum((a-b)**2 for a,b in zip(p,current['pos'])), -p[1]))
        p=list(candidates[0]);record={'pos':p}
        approach=client.request('approach_block',pos=p,face='up',expected_state='Block{minecraft:gravel}',seconds=120)
        if approach.get('phase')!='done':
            if approach.get('phase')=='waiting' or 'Manual menu' in str(approach.get('detail','')):
                raise Handoff('Gravel approach yielded to player control: '+str(approach.get('detail')))
            record['approach']=approach.get('detail');blocked.add(tuple(p));result['blocks'].append(record);continue
        client.checked('select_item',item='minecraft:diamond_shovel')
        before=client.status()
        fluid_veto=False
        for attempt in range(3):
            fresh=client.request('scan',min=[p[0]-WATER_BUFFER,p[1]-2,p[2]-WATER_BUFFER],
                                 max=[p[0]+WATER_BUFFER,p[1]+2,p[2]+WATER_BUFFER],details=True)['blocks']
            state=block_state(fresh,p)
            if state!='Block{minecraft:gravel}':
                raise RuntimeError('Gravel changed before a confirmed mine; stop without replay')
            if not dry_top_gravel(fresh,p):
                fluid_veto=True;record['skipped']='water buffer changed before mining';break
            mined=client.request('mine_block',pos=p,face='up',expected_state=state,seconds=20)
            record['mine_phase']=mined.get('phase');record['mine_detail']=mined.get('detail')
            if mined.get('phase')=='done':break
            if mined.get('detail')=='Fluid next to target is protected':
                fluid_veto=True
                break
            if mined.get('phase')!='error' or mined.get('detail') not in ('Mining target out of reach','Construction guard is defending or eating; wait before changing items or starting work'):
                raise RuntimeError('Gravel mining was not confirmed: '+str(mined.get('detail')))
            if attempt==2:raise RuntimeError('Guard repeatedly interrupted gravel mining')
            again=client.request('approach_block',pos=p,face='up',expected_state=state,seconds=120)
            if again.get('phase')!='done':raise RuntimeError('Could not return to the gravel target after defense')
            client.checked('select_item',item='minecraft:diamond_shovel')
        if fluid_veto:
            blocked.add(tuple(p));record.setdefault('skipped','fluid protection');result['blocks'].append(record)
            Path(out).mkdir(parents=True,exist_ok=True)
            (Path(out)/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            continue
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            after=client.status()
            if item_count(after,GRAVEL)>item_count(before,GRAVEL) or item_count(after,FLINT)>item_count(before,FLINT):break
            drops=fresh_drops(before,after,p)
            if drops:
                for drop in drops:
                    if not collect_drop(client,drop,observation=after):
                        raise RuntimeError('Observed gravel/flint drop could not be recovered')
                break
            time.sleep(.25)
        after=client.status()
        record['gravel_gain']=item_count(after,GRAVEL)-item_count(before,GRAVEL)
        record['flint_gain']=item_count(after,FLINT)-item_count(before,FLINT)
        record['health']=after['health']
        result['blocks'].append(record)
        Path(out).mkdir(parents=True,exist_ok=True)
        (Path(out)/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        if record['gravel_gain']+record['flint_gain']<1:
            raise RuntimeError('Removed gravel yielded no verified pickup')
    result['gravel_after']=item_count(client.status(),GRAVEL)
    result['gained']=result['gravel_after']-result['gravel_before']
    result['complete']=result['gained']>=target_count
    result['health']=client.status()['health']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--min',nargs=3,type=int,required=True)
    parser.add_argument('--max',nargs=3,type=int,required=True)
    parser.add_argument('--count',type=int,required=True)
    parser.add_argument('--park-high',nargs=3,type=float,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    client=MaterialClient('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation',args.out,
                          remote_finish='guard',park_target=args.park_high)
    try:
        result=harvest(client,args.min,args.max,args.count,args.out)
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:client.finish()


if __name__=='__main__':main()
