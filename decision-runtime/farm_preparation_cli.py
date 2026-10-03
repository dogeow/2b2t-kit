"""Prepare one explicit small field; reuse farm plant for potato/wheat planting."""
import argparse
import json
from pathlib import Path
import time
import hashlib
import uuid
import math

from farm_preparation import PreparationWait, _scope, _identity, journal_directory, plan, preparation_lock, run
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient
from potato_farm_cli import DEFAULT_GAME, finish_or_yield
from safety_interlock import require_unlocked


def parking_anchor_matches(expected, state):
    actual=state.get('pos');anchor=(state.get('supervision_lease')or{}).get('park_target')
    if any(not isinstance(p,list) or len(p)!=3 or any(type(n) not in (int,float) or not math.isfinite(n) for n in p) for p in [expected,actual,anchor]):return False
    # Native parking adopts the actually settled pose, rather than the requested Y.
    return (math.hypot(actual[0]-expected[0],actual[2]-expected[2])<=8
            and abs(actual[1]-expected[1])<=2 and math.dist(actual,anchor)<=.5)


def guarded_finish_proved(proof,state,book,world,rev,task,lease_id,target):
    lease=state.get('supervision_lease')or{}
    return (proof.get('action')=='KEEP_PVE_GUARD' and proof.get('lease')==lease_id
        and proof.get('job_session')==task and type(proof.get('time')) is int
        and state.get('connected') is True and state.get('world_session')==world
        and state.get('control_revision')==rev and type(state.get('time')) is int and state['time']>=proof['time']
        and state.get('health')==20 and state.get('food',0)>=18
        and ('recent_hurt_at' not in book or state.get('recent_hurt_at')==book['recent_hurt_at'])
        and state.get('manual_movement') is False and state.get('screen')=='' and state.get('under_water') is False
        and (state.get('safety_hold')or{}).get('active') is False and state.get('flight') is True
        and state.get('guard_armed') is True and state.get('guard_pve_only') is True and state.get('guard_busy') is False
        and state.get('navigating') is False and lease.get('id')==lease_id and lease.get('kind')=='parking'
        and lease.get('world_session')==world and lease.get('revision')==rev and lease.get('job_session')==task
        and parking_anchor_matches(target,state))


class _FinalizingClient:
    """Reuse existing guarded finish, retaining its unknown mutations in our journal."""
    def __init__(self, client, journal): self.client, self.journal = client, journal
    def __getattr__(self, name): return getattr(self.client, name)
    def __setattr__(self, name, value):
        if name in ('client', 'journal'): object.__setattr__(self, name, value)
        else: setattr(self.client, name, value)

    def _begin(self, op, params, cleanup=False):
        book = json.loads(self.journal.read_text()); key = 'cleanup_pending' if cleanup else 'pending'
        if book.get(key): raise PreparationWait('WAIT_RECONCILE', 'Previous finish mutation remains unresolved')
        book[key] = {'op': op, 'params': params, 'stage': 'intent_before_dispatch'}
        write_json(self.journal, book)
        return key

    def _complete(self, key, reply):
        book = json.loads(self.journal.read_text()); intent = book[key]
        intent['receipt'] = reply; book['actions'].append(intent); book[key] = None
        write_json(self.journal, book)

    def checked(self, op, **params):
        key = self._begin(op, params); reply = self.client.checked(op, **params)
        state = self.client.status(); lease = state.get('supervision_lease') or {}
        if (reply.get('id') != self.client.last or reply.get('world_session') != self.client.world
                or op != 'material_job_park' or lease.get('park_target') != params.get('park_target')):
            raise PreparationWait('WAIT_RECONCILE', 'Guard parking update is unconfirmed; finish intent retained')
        self._complete(key, reply); return reply

    def request(self, op, **params):
        key = self._begin(op, params, cleanup=True); reply = self.client.request(op, **params)
        if (reply.get('phase') != 'done' or reply.get('id') != self.client.last
                or reply.get('world_session') != self.client.world):
            raise PreparationWait('WAIT_RECONCILE', 'Cleanup pause is unconfirmed; cleanup intent retained')
        self._complete(key, reply); return reply

    def finish(self):
        key = self._begin('guarded_finish', {'park_target': self.client.park_target})
        self.client.finish()
        proof_path = Path(self.client.out) / 'stock-safety.json'
        proof = json.loads(proof_path.read_text()) if proof_path.exists() else {}
        # Native KEEP_PVE_GUARD receipts may omit snapshot and keep confirmed=false.
        # Require a fresh current parking lease instead of rewriting that receipt.
        state = self.client.raw(); lease = state.get('supervision_lease') or {}
        book = json.loads(self.journal.read_text())
        if not guarded_finish_proved(proof,state,book,self.client.world,self.client.rev,
                                     self.client.task,self.client.heartbeat.id,self.client.park_target):
            raise PreparationWait('WAIT_RECONCILE', 'Owned guarded finish was not confirmed; finish intent retained')
        self._complete(key, {**proof, 'fresh_observation': state})


def reconcile_guarded_finish(game_dir,center,radius=2,out=None):
    """Read-only exact current parking proof; never dispatch or repeat finish."""
    root=Path(game_dir)/'config/twob2tkit/automation';state=read_fresh(root);require_unlocked(root,state)
    request={'authorized':True,'center':center,'radius':radius}
    with preparation_lock(root,state,request):
        directory,journal=journal_directory(root,state,request,out)
        book=json.loads(journal.read_text());pending=book.get('pending')or{}
        if pending.get('op')!='guarded_finish' or book.get('cleanup_pending'):
            raise PreparationWait('WAIT_RECONCILE','Only the existing guarded_finish intent can be reconciled here')
        last=book.get('actions',[])[-1] if book.get('actions') else {}
        receipt=last.get('receipt')or{};lease=receipt.get('supervision_lease')or{}
        target=(pending.get('params')or{}).get('park_target')
        if (last.get('op')!='material_job_park' or (last.get('params')or{}).get('park_target')!=target
                or receipt.get('phase')!='done' or receipt.get('world_session')!=state['world_session']
                or lease.get('world_session')!=state['world_session'] or lease.get('kind')!='materials'
                or not lease.get('id') or not lease.get('job_session')):
            raise PreparationWait('WAIT_RECONCILE','Original owned park update is missing or scope changed')
        for path in directory.glob('control-*/stock-safety.json'):
            proof=json.loads(path.read_text())
            if (type(receipt.get('time')) is not int or type(proof.get('time')) is not int or proof['time']<receipt['time']):continue
            if guarded_finish_proved(proof,state,book,state['world_session'],state['control_revision'],
                                      lease['job_session'],lease['id'],target):
                original=dict(pending)
                book['actions'].append({**original,'receipt':{**proof,'fresh_observation':state},
                                        'reconciled_read_only':True,'original_proof_path':str(path)})
                book['pending']=None;write_json(journal,book)
                return {'phase':'done','code':'FINISH_RECONCILED','journal':str(journal),'game_actions':0,
                        'field_complete':book.get('complete') is True,'server_verified':False}
        raise PreparationWait('WAIT_RECONCILE','Matching current parking proof is unavailable; no intent changed')


def recover_read_only_session(root, state, request, out=None):
    """Explicit CLI recovery of a stopped read-only attempt; never waive a use intent."""
    scope=_scope(state,request);key=_identity({k:v for k,v in scope.items() if k!='radius'})
    registry=Path(root)/'farm-preparation'/key/'registry.json'
    if not registry.exists():return
    saved=json.loads(registry.read_text())
    if saved.get('world_session')==state['world_session']:return
    if saved.get('scope')!=scope or saved.get('water_source')!=request.get('water_source'):
        raise PreparationWait('WAIT_CONTROL','Recovery cannot change the original field scope/source')
    directory=Path(saved['directory']).resolve()
    if out is not None and Path(out).resolve()!=directory:
        raise PreparationWait('WAIT_CONTROL','Recovery cannot change the original output')
    journal=directory/('farm-preparation-'+_identity(scope)+'.json')
    book=json.loads(journal.read_text());actions=book.get('actions')
    if (book.get('scope')!=scope or book.get('world_session')!=saved['world_session']
            or book.get('pending') or book.get('cleanup_pending') or book.get('complete')
            or not isinstance(actions,list) or len(actions)!=2
            or [a.get('op') for a in actions]!=['acquire_control','material_job_pause']):
        raise PreparationWait('WAIT_RECONCILE','Only the original read-only, stopped attempt can be recovered automatically')
    receipt=actions[-1].get('receipt')or{}
    if (receipt.get('phase')!='done' or receipt.get('world_session')!=saved['world_session']
            or not isinstance(receipt.get('id'),str) or not receipt['id']):
        raise PreparationWait('WAIT_RECONCILE','Original owned pause acknowledgement is missing')
    archive=directory/'archives'/('read-only-'+uuid.uuid4().hex);archive.mkdir(parents=True)
    original_registry=registry.read_bytes();original_journal=journal.read_bytes()
    (archive/'registry.json').write_bytes(original_registry);(archive/'journal.json').write_bytes(original_journal)
    proof={'reason':'explicit_read_only_session_recovery','previous_world':saved['world_session'],
           'new_world':state['world_session'],'archive':str(archive),
           'registry_sha256':hashlib.sha256(original_registry).hexdigest(),
           'journal_sha256':hashlib.sha256(original_journal).hexdigest(),'world_actions_replayed':0}
    write_json(archive/'recovery.json',proof)
    write_json(journal,{'schema':1,'scope':scope,'world_session':state['world_session'],
                       'water_source':request.get('water_source'),'actions':[],'pending':None,'recovery':proof})
    write_json(registry,{**saved,'world_session':state['world_session'],'recovery':proof})


def execute(game_dir, center, radius=2, water_source=None, out=None, no_move=False, max_torches=4, recover_read_only=False):
    request = {'authorized': True, 'center': center, 'radius': radius, 'water_source': water_source}
    plan(request)
    if type(max_torches) is not int or not 1 <= max_torches <= 4: raise ValueError('Torch budget must be 1..4')
    root = Path(game_dir) / 'config/twob2tkit/automation'; state = read_fresh(root)
    require_unlocked(root, state)
    if (state.get('connected') is not True or state.get('screen') != '' or state.get('manual_movement') is not False
            or state.get('dimension') != 'minecraft:overworld' or state.get('game_mode') != 'survival'
            or state.get('health') != 20 or state.get('food', 0) < 18
            or type(state.get('recent_hurt_at')) is not int):
        raise PreparationWait('WAIT_SAFETY', 'Connected idle full-health survival player and exact injury marker are required')
    with preparation_lock(root, state, request):
        if recover_read_only:recover_read_only_session(root,state,request,out)
        directory, journal = journal_directory(root, state, request, out)
        book = json.loads(journal.read_text()) if journal.exists() else {'schema': 1, 'scope': _scope(state, request),
            'world_session': state['world_session'], 'water_source': water_source, 'actions': [], 'pending': None}
        if (book.get('schema') != 1 or book.get('scope') != _scope(state, request)
                or book.get('world_session') != state['world_session'] or book.get('water_source') != water_source
                or not isinstance(book.get('actions'), list)):
            raise PreparationWait('WAIT_CONTROL', 'Preparation journal scope/session is inconsistent; no controller created')
        if book.get('pending') or book.get('cleanup_pending'):
            return {'phase': 'waiting', 'code': 'WAIT_RECONCILE', 'journal': str(journal),
                    'detail': 'Saved preparation intent is unresolved; no controller or repeated action created'}
        park_y = min(315, max(100, state['pos'][1], center[1]+35))
        park = [state['pos'][0], park_y, state['pos'][2]]
        book['pending'] = {'op': 'acquire_control', 'stage': 'intent_before_dispatch'}; write_json(journal, book)
        try:
            c = MaterialClient(root, directory / ('control-'+str(time.time_ns())), server=state['server'],
                               remote_finish='guard', park_target=park)
        except (RuntimeError, OSError, ValueError, KeyError) as error:
            raise PreparationWait('WAIT_RECONCILE', 'Control acquisition outcome unknown; intent retained at '+str(journal)+': '+str(error)) from error
        c.job_progress = None
        result = None
        try:
            if c.world != state['world_session']:
                raise PreparationWait('WAIT_CONTROL', 'Game session changed during control acquisition')
            book['actions'].append(book['pending']); book['pending'] = None; write_json(journal, book)
            result = run(c, request, directory, no_move=no_move, max_torches=max_torches, _locked=True)
            try:
                finish_or_yield(_FinalizingClient(c, journal), result, journal,
                                state['recent_hurt_at'], park_y, no_move, allow_settled_wait=True)
            except (RuntimeError, OSError, ValueError, KeyError) as error:
                result = {**result, 'phase': 'waiting', 'code': 'WAIT_RECONCILE', 'detail': str(error)}
            saved = json.loads(journal.read_text())
            if saved.get('pending') or saved.get('cleanup_pending'):
                result = {**result, 'phase': 'waiting', 'code': 'WAIT_RECONCILE',
                          'detail': result.get('detail') or 'Finish or cleanup intent remains unresolved; no retry'}
            return result
        finally:
            c.heartbeat.close()
            if c.job_progress: c.job_progress.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, default=DEFAULT_GAME)
    parser.add_argument('--center', type=int, nargs=3, required=True)
    parser.add_argument('--radius', type=int, choices=(1, 2), default=2)
    parser.add_argument('--water-source', type=int, nargs=3)
    parser.add_argument('--max-torches', type=int, choices=(1, 2, 3, 4), default=4)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--reconcile-finish',action='store_true',help='Verify an existing finish against its current native parking lease; no game actions')
    parser.add_argument('--recover-read-only-session',action='store_true',help='Archive an acknowledged stopped read-only attempt after reconnect; never clears unknown uses')
    parser.add_argument('--no-move', action='store_true', help='Require exact interaction targets already in reach')
    args = parser.parse_args(argv)
    try:
        if args.reconcile_finish:
            result=reconcile_guarded_finish(args.game_dir,args.center,args.radius,args.out)
            print(json.dumps(result,ensure_ascii=False));return 0
        options={'recover_read_only':True} if args.recover_read_only_session else {}
        result = execute(args.game_dir, args.center, args.radius, args.water_source, args.out, args.no_move, args.max_torches,**options)
        print(json.dumps(result, ensure_ascii=False)); return 0 if result.get('phase') == 'done' else 2
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(json.dumps({'phase': 'waiting', 'code': getattr(error, 'code', 'WAIT_CONTROL'), 'detail': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__': raise SystemExit(main())
