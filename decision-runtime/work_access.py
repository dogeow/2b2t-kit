"""Bounded alternative access poses; ambiguous mutations are never retried here."""
import json,time

BLOCKED_APPROACHES={
    'No visible collision-free depot approach',
    'No loaded collision-free route to this depot; no ceiling is broken',
    'Depot approach occluded or out of reach',
}

class ApproachUnavailable(RuntimeError):pass

def _same_access_scope(client,state,world,revision):
    return (isinstance(state,dict) and isinstance(world,str) and bool(world) and type(revision) is int
            and getattr(client,'world',None)==world and getattr(client,'rev',None)==revision
            and state.get('world_session')==world and type(state.get('control_revision')) is int
            and state['control_revision']==revision)


def approach_faces(client,pos,expected_state,faces,seconds=90,stand_distance=None,*,allow_state_change=None):
    if allow_state_change is not None and not callable(allow_state_change):raise ValueError('State change rule must be callable')
    if stand_distance is not None and not .25<=stand_distance<=3:raise ValueError('Standing distance must be within native bounds')
    faces=list(dict.fromkeys(faces))
    if len(faces)>6 or any(f not in {'up','down','north','south','east','west'} for f in faces):
        raise ValueError('At most six observed block faces are allowed')
    attempts=[]
    for face in faces:
        # A previous navigation attempt may have moved us. Recheck both scope and
        # the exact target before choosing another pose; this never repeats mining.
        before=client.status();world=getattr(client,'world',None);revision=getattr(client,'rev',None)
        if allow_state_change is not None and not _same_access_scope(client,before,world,revision):
            raise RuntimeError('Work access world or revision changed')
        scan=client.request('scan',min=pos,max=pos);rows=scan.get('blocks')
        if (not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict)
                or not isinstance(rows[0].get('state'),str)):
            raise RuntimeError('Work target changed during access recovery')
        if allow_state_change is not None:
            if (scan.get('phase')!='done' or rows[0].get('pos')!=list(pos)
                    or not _same_access_scope(client,scan,world,revision)
                    or not _same_access_scope(client,client.status(),world,revision)):
                raise RuntimeError('Work access world, revision or scan changed')
        previous_state=expected_state;observed=rows[0]['state']
        if observed!=expected_state and (allow_state_change is None or allow_state_change(expected_state,observed) is not True):
            raise RuntimeError('Work target changed during access recovery')
        expected_state=observed  # The normal native approach still receives an exact fresh state.
        reply=client.request('approach_block',pos=pos,face=face,expected_state=expected_state,seconds=seconds,**({'stand_distance':stand_distance} if stand_distance is not None else {}))
        outcome='reached' if reply.get('phase')=='done' else 'blocked' if reply.get('phase') in ('error','waiting') and reply.get('detail') in BLOCKED_APPROACHES else 'unconfirmed'
        attempts.append({'face':face,'outcome':outcome,'detail':reply.get('detail')})
        with (client.out/'access-recovery.jsonl').open('a') as stream:
            stream.write(json.dumps({'time':int(time.time()*1000),'pos':pos,'expected_state':expected_state,
                                     'state_before':previous_state,'attempt':attempts[-1]},ensure_ascii=False)+'\n')
        if outcome=='reached':return face
        if outcome!='blocked':raise RuntimeError(reply.get('detail','Access not confirmed; inspect before continuing'))
    raise ApproachUnavailable('No verified access face after bounded alternatives')
