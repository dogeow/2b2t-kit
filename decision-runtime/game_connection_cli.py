"""Normal connection to a saved server from an idle title screen; no credential access."""
import argparse
import json
from pathlib import Path
import time
import uuid
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from safety_interlock import require_unlocked

def pending_screen(screen, seen_connecting, elapsed):
    return screen in ('ConnectScreen','ReceivingLevelScreen','ProgressScreen','LevelLoadingScreen') or (
        screen in ('TitleScreen','DisconnectedScreen') and not seen_connecting and 0 <= elapsed <= 2)

def connection_screen_seen(screen, seen_connecting):
    return seen_connecting or screen in ('ConnectScreen','ReceivingLevelScreen','ProgressScreen','LevelLoadingScreen')

def connect(root, address, expected_player, out, *, seconds=60):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + seconds
    while True:
        try:
            state = read_fresh(root, wait_seconds=.5)
            if state.get('client_connection_protocol') == 1:
                break
        except RuntimeError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Current connection-capable client did not start; no request sent')
        time.sleep(.2)
    require_unlocked(root,state)
    if (state.get('connected') is not False or state.get('screen') not in ('TitleScreen','DisconnectedScreen')
            or state.get('account_name') != expected_player or state.get('supervision_lease')
            or state.get('safety_hold', {}).get('active') or state.get('health_recovery_hold')):
        raise RuntimeError('Current idle title account or safety state differs; no connection sent')
    request_id = 'connect-' + uuid.uuid4().hex[:12]
    request = {'id': request_id, 'op': 'connect_server', 'address': address,
               'expected_player': expected_player, 'world_session': state['world_session'],
               'expected_revision': state['control_revision'], 'expires_at': int(time.time()*1000)+12_000}
    write_json(out/'intent.json', request)
    write_json(root/'request.json', request)
    reply = root / ('reply-' + request_id + '.json')
    while time.monotonic() < deadline:
        if reply.exists():
            observed = json.loads(reply.read_text())
            write_json(out/'native-reply.json', observed)
            if observed.get('id') != request_id or observed.get('phase') != 'done':
                raise RuntimeError(observed.get('detail','Connection request not accepted; never replayed'))
            break
        time.sleep(.2)
    else:
        raise RuntimeError('Original connection receipt missing; request retained and not replayed')
    accepted_at=time.monotonic();seen_connecting=False
    while time.monotonic() < deadline:
        current = read_fresh(root)
        write_json(out/'latest.json', current)
        if current.get('connected') is True:
            if current.get('player_name') != expected_player or current.get('server','').removesuffix(':25565').lower() != address.removesuffix(':25565').lower():
                raise RuntimeError('Actual connected account or server differs; no gameplay actions')
            write_json(out/'result.json', {'connected':True,'server':current['server'],
                'world_session':current['world_session'],'player_name':current['player_name'],
                'game_version':current['game_version'],'kit_version':current['kit_version'],
                'runtime_version':current['runtime_version'],'inventory_credit':0,'request_replayed':False})
            return current
        if not pending_screen(current.get('screen'),seen_connecting,time.monotonic()-accepted_at):
            raise RuntimeError('Connection awaiting a different screen; preserve receipt without replay')
        seen_connecting=connection_screen_seen(current.get('screen'),seen_connecting)
        time.sleep(.25)
    raise RuntimeError('Connection observation expired; original request was not replayed')

def stale_owner_releasable(state,world,task):
    lease=state.get('supervision_lease')or{}
    return (state.get('connected')is False and state.get('screen')in ('TitleScreen','DisconnectedScreen')
            and isinstance(world,str)and bool(world)and isinstance(task,str)and bool(task)
            and state.get('world_session')!=world and lease.get('world_session')==world
            and lease.get('job_session')==task and lease.get('kind')=='materials'
            and not state.get('safety_hold',{}).get('active')and not state.get('health_recovery_hold'))

def release_disconnected_owner(root,out,terminal):
    """Stop only a confirmed-terminal owner's stale disconnected scope; retain all journals."""
    root,out=Path(root),Path(out);state=read_fresh(root);require_unlocked(root,state)
    if (terminal.get('exec_terminal_confirmed')is not True or type(terminal.get('exit_code'))is not int
            or not stale_owner_releasable(state,terminal.get('world_session'),terminal.get('task_session'))):
        raise RuntimeError('No exact terminal disconnected owner to release')
    out.mkdir(exist_ok=False);write_json(out/'before.json',state);write_json(out/'terminal.json',terminal)
    request={'id':'stale-stop-'+uuid.uuid4().hex[:12],'op':'stop','world_session':state['world_session'],'expected_revision':state['control_revision']}
    write_json(out/'intent.json',request);write_json(root/'request.json',request);deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        current=read_fresh(root)
        if current.get('id')==request['id']and current.get('phase')=='stopped'and not current.get('supervision_lease'):
            write_json(out/'after.json',current);write_json(out/'result.json',{'complete':True,'request_id':request['id'],'old_actions_replayed':False,'world_inputs':0,'safety_lock_cleared':False});return current
        time.sleep(.1)
    raise RuntimeError('Original stale-owner stop outcome retained; no replay')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--server',required=True)
    p.add_argument('--player',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try:
        s=connect(a.root,a.server,a.player,a.out)
        print('ACTUAL_CONNECTED',s['server'],s['player_name'],s['game_version'],s['kit_version'],flush=True)
    except Exception as error:
        if a.out.exists():write_json(a.out/'retained-result.json',{'reason':str(error),'request_replayed':False})
        raise

if __name__=='__main__':main()
