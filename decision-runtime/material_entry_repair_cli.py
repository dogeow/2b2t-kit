"""Observe and optionally register a repaired natural-source entry through Kit."""
import argparse
import json
from pathlib import Path

from live_snapshot import read_fresh
from material_client import Client
from material_jobs.entry_repair import observe
from material_jobs.profile import load,profile_path
from kit_runtime.journal import write_json


def run(automation,region,out,apply=False):
    automation,out=Path(automation),Path(out)
    out.mkdir(parents=True,exist_ok=True)
    state=read_fresh(automation)
    if (not state.get('connected') or state.get('manual_movement') or state.get('screen')
            or state.get('native_material_busy') or state.get('navigating')):
        raise RuntimeError('Current player/control state is unavailable for read-only entry repair')
    context={k:state[k] for k in ('server','dimension','world_session')}
    profile=load(automation,context)
    client=Client(automation,out/'native-read',server=state['server'])
    proof=observe(client,region,profile,out)
    if apply and proof['planned'] is not None:
        current=client.status()
        if current['world_session']!=context['world_session'] or current['control_revision']!=client.rev:
            raise RuntimeError('Entry registration scope changed; original profile retained')
        path=profile_path(automation,context)
        raw=path.read_bytes();original=json.loads(raw)
        (out/'original-profile.json').write_bytes(raw)
        repaired={**proof['planned']['region'],'entry_repair_proof':str((out/'entry-repair-plan.json').resolve())}
        regions=original.setdefault('resource_regions',[])
        if repaired not in regions:regions.insert(0,repaired)
        original.setdefault('entry_repair_history',[]).append({
            'original_region':region,'replacement_region':repaired,
            'world_session':client.world,'observed_at':proof['observed_at'],
            'original_route_hold_unchanged':True})
        write_json(path,original)
        proof.update(registered=True,profile_path=str(path),game_movement_sent=False,inventory_credit=0)
        write_json(out/'registration-proof.json',proof)
    return proof


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--automation',type=Path,required=True)
    p.add_argument('--region',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--apply-profile',action='store_true')
    args=p.parse_args()
    proof=run(args.automation,json.loads(args.region.read_text()),args.out,args.apply_profile)
    print(json.dumps({'planned':proof['planned'],'registered':proof.get('registered',False),
                      'game_movement_sent':False,'inventory_credit':0},ensure_ascii=False))
    return 0 if proof['planned'] else 2


if __name__=='__main__':raise SystemExit(main())
