"""Explicit Kit native trial lifecycle commands; never model-generated input."""
import argparse
import json
from pathlib import Path
import time
import uuid


def call(game, command, *, world_id=None, timeout=15):
    game=Path(game);folder=game/'config/twob2tkit/singleplayer-trial'
    status=json.loads((game/'config/twob2tkit/automation/status.json').read_text())
    if time.time()*1000-status.get('time',0)>5000 or status.get('singleplayer_trial_api_protocol')!=1:
        raise RuntimeError('A fresh Kit native trial API is required')
    if command not in ('status','start','pause','resume','cancel','open_world','create_world','quit_game'):
        raise ValueError('Unsupported trial command')
    request={'protocol':1,'id':'trial-api-'+uuid.uuid4().hex,'command':command,'expires_at':int(time.time()*1000)+15000}
    if command in ('start','pause','resume','cancel'):
        if status.get('server')!='singleplayer' or not status.get('connected'):
            raise RuntimeError('Only the currently entered local world can run a trial')
        request.update(world_id=status['world_id'],world_session=status['world_session'],expected_revision=status['control_revision'])
    elif command=='open_world':
        if status.get('connected') or not world_id:raise RuntimeError('Exit the current world before opening the exact requested local save')
        request['world_id']=str(Path(world_id).absolute())
    elif command in ('create_world','quit_game') and status.get('connected'):
        raise RuntimeError('Exit the current world before creating a new save')
    folder.mkdir(parents=True,exist_ok=True);path=folder/'api-request.json'
    if path.exists():
        old=json.loads(path.read_text());receipt=folder/('api-reply-'+old['id']+'.json')
        if not receipt.exists():raise RuntimeError('An earlier native trial command is unconfirmed; do not replay')
    temp=folder/'api-request.tmp';temp.write_text(json.dumps(request,ensure_ascii=False));temp.replace(path)
    receipt=folder/('api-reply-'+request['id']+'.json');until=time.monotonic()+timeout
    while time.monotonic()<until:
        if receipt.exists():
            result=json.loads(receipt.read_text())
            if result.get('id')!=request['id']:raise RuntimeError('Trial reply identity differs')
            if result.get('phase')!='done':raise RuntimeError(result.get('detail','Native trial command failed'))
            return result
        time.sleep(.1)
    raise RuntimeError('Native trial outcome is unknown; preserve the request and do not replay')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--game',type=Path,required=True)
    p.add_argument('command',choices=('status','start','pause','resume','cancel','open_world','create_world','quit_game'))
    p.add_argument('--world-id');a=p.parse_args();print(json.dumps(call(a.game,a.command,world_id=a.world_id),ensure_ascii=False))
