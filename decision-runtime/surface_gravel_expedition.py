"""Fly between bounded surface patches and use the guarded gravel miner.

The miner only opens already exposed, dry gravel. After each patch the player
flies back into open air before another search; it never routes underground
between deposits.
"""

import argparse
import json
import re
import time
from pathlib import Path

from build_supervisor import stocks
from gravel_harvest import dry_top_gravel, harvest
from material_client import MaterialClient

GRAVEL = 'minecraft:gravel'


def route_for_targets(value):
    selected = {part.upper() for part in re.split(r'[,;|\s]+', value) if part}
    return 'surface' if selected == {'GRAVEL'} else 'underground'


def candidates(rows, low, high):
    return [entry['pos'] for entry in rows if entry['state'] == 'Block{minecraft:gravel}'
            and all(low[i] <= entry['pos'][i] <= high[i] for i in range(3))
            and dry_top_gravel(rows, entry['pos'])]


def centre(low, high, y):
    return [(low[0] + high[0] + 1)/2, y, (low[2] + high[2] + 1)/2]


def expedition(client, regions, target, cruise_y, out):
    if not 1 <= target <= 64 or not 85 <= cruise_y <= 160:
        raise ValueError('One guarded expedition collects 1..64 gravel at Y85..160')
    result = {'start': client.status()['pos'], 'gravel_before': stocks(client.status()).get(GRAVEL,0),
              'target': target, 'regions': []}
    for number, (low, high) in enumerate(regions):
        gained = stocks(client.status()).get(GRAVEL,0) - result['gravel_before']
        if gained >= target: break
        if any(low[i] > high[i] for i in range(3)) or any(high[i]-low[i] > 16 for i in (0,2)) \
                or high[1]-low[1] > 3:
            raise ValueError('A surface patch must be at most 17×4×17 blocks')
        site = centre(low, high, cruise_y)
        flight = client.request('navigate', target=site, arrival=2, seconds=120)
        if flight.get('phase') != 'done' or client.status()['health'] < 18:
            raise RuntimeError('High approach to surface patch did not complete')
        observed = client.request('scan', min=[low[0]-1,low[1]-1,low[2]-1],
                                  max=[high[0]+1,high[1]+1,high[2]+1], details=True)
        dry = candidates(observed['blocks'],low,high)
        entry = {'bounds': [low,high], 'high_arrival': client.status()['pos'],
                 'dry_candidates': len(dry), 'examples': dry[:8]}
        result['regions'].append(entry)
        if dry:
            region_out = Path(out)/('patch-'+str(number))
            entry['harvest'] = harvest(client,low,high,min(target-gained,len(dry)),region_out)
            # Mining stays within one small surface patch. Before searching a
            # different patch, rise to clear air rather than traversing caves.
            climb = client.request('navigate', target=site, arrival=2, seconds=90)
            entry['high_departure'] = {'phase': climb.get('phase'),
                                       'pos': client.status()['pos']}
            if climb.get('phase') != 'done' or client.status()['health'] < 18:
                raise RuntimeError('Surface patch ascent did not complete')
        Path(out).mkdir(parents=True,exist_ok=True)
        (Path(out)/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    result['gravel_after'] = stocks(client.status()).get(GRAVEL,0)
    result['gained'] = result['gravel_after']-result['gravel_before']
    result['health'] = client.status()['health']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region',action='append',nargs=6,type=int,required=True,
                        metavar=('MIN_X','MIN_Y','MIN_Z','MAX_X','MAX_Y','MAX_Z'))
    parser.add_argument('--target',type=int,default=32)
    parser.add_argument('--targets',default='GRAVEL',
                        help='Only GRAVEL uses this surface route; mixed selections remain underground')
    parser.add_argument('--cruise-y',type=float,default=95)
    parser.add_argument('--park-high',type=float,nargs=3,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if route_for_targets(args.targets)!='surface':
        raise ValueError('Mixed ore selections belong to the existing underground miner')
    regions=[(r[:3],r[3:]) for r in args.region]
    client=MaterialClient('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation',args.out,
                          remote_finish='guard',park_target=args.park_high)
    try:
        result=expedition(client,regions,args.target,args.cruise_y,args.out)
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:client.finish()


if __name__=='__main__':main()
