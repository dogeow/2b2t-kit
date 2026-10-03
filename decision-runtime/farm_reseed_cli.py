"""Explicitly reseed listed AIR cells in an original completed field; never till."""
import argparse
import json
import math
from pathlib import Path
import time

from farm_preparation import preparation_lock
from farm_reseed import prepare_journal,registered,run
from job_progress import JobProgress
from live_snapshot import read_fresh
from material_client import MaterialClient
from potato_farm_cli import DEFAULT_GAME,finish_or_yield
from safety_interlock import require_unlocked


def execute(game_dir,registry,cells,out=None,no_move=False):
    root=Path(game_dir)/'config/twob2tkit/automation';state=read_fresh(root);require_unlocked(root,state)
    if (state.get('connected') is not True or state.get('health')!=20 or state.get('food',0)<18
            or state.get('manual_movement') is not False or state.get('screen')!='' or state.get('dimension')!='minecraft:overworld'):
        raise RuntimeError('Reseeding requires an idle full-health current Overworld connection')
    values=registered(root,registry,cells,server=state['server']);request=values[5];layout=values[3];crop=values[4]
    if math.hypot(state['pos'][0]-layout['center'][0],state['pos'][2]-layout['center'][2])>384:
        raise RuntimeError('Explicit maintenance is outside the existing bounded384-block travel route')
    with preparation_lock(root,state,request):
        journal,_=prepare_journal(root,registry,cells,state['world_session'],out,server=state['server'])
        park_y=min(315,max(100,state['pos'][1],layout['center'][1]+35));park=[state['pos'][0],park_y,state['pos'][2]]
        client=MaterialClient(root,journal.parent/('reseed-control-'+str(time.time_ns())),server=state['server'],remote_finish='guard',park_target=park)
        client.job_progress=JobProgress(root,client.world,client.task,client.rev,crop.title+'原耕地补种',len(cells))
        hurt=state['recent_hurt_at'];result=None
        try:
            result=run(client,registry,cells,out,allow_move=not no_move,_locked=True,journal=journal)
            client.set_progress(done=result['new_reseed'],phase='原耕地补种已核对' if result.get('phase')=='done' else '补种暂停，原记录保留')
            return result
        finally:finish_or_yield(client,result,journal,hurt,park_y,no_move,allow_settled_wait=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,default=DEFAULT_GAME)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--cell',type=int,nargs=3,action='append',required=True,metavar=('X','FLOOR_Y','Z'))
    parser.add_argument('--out',type=Path)
    parser.add_argument('--no-move',action='store_true')
    parser.add_argument('--journal',type=Path)
    parser.add_argument('--control-dir',type=Path)
    parser.add_argument('--archive-verified',action='store_true')
    parser.add_argument('action',nargs='?',choices=('run','reconcile-rejected'),default='run')
    args=parser.parse_args(argv)
    try:
        if args.action=='reconcile-rejected':
            if args.journal is None or args.control_dir is None:raise ValueError('Rejection verification requires the original journal and control directory')
            from farm_reseed import read
            if read(args.journal).get('requested_cells')!=args.cell:raise ValueError('Explicit cells must match the exact original rejected maintenance request')
            from farm_reseed_reconcile import reconcile_rejected
            result=reconcile_rejected(args.game_dir/'config/twob2tkit/automation',args.registry,args.journal,args.control_dir,archive_verified=args.archive_verified)
        else:
            if args.archive_verified or args.journal is not None or args.control_dir is not None:raise ValueError('Original evidence arguments only apply to reconcile-rejected')
            result=execute(args.game_dir,args.registry,args.cell,args.out,args.no_move)
        print(json.dumps(result,ensure_ascii=False));return 0 if result.get('phase') in ('done','verified_rejection','archived_rejection') else 2
    except (RuntimeError,ValueError,OSError,KeyError) as error:
        print(json.dumps({'phase':'waiting','code':getattr(error,'code','WAIT_RESEED'),'detail':str(error)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
