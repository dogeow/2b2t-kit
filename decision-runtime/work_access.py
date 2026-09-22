"""Bounded alternative access poses; ambiguous mutations are never retried here."""
import json,time

BLOCKED_APPROACHES={
    'No visible collision-free depot approach',
    'No loaded collision-free route to this depot; no ceiling is broken',
    'Depot approach occluded or out of reach',
}

class ApproachUnavailable(RuntimeError):pass

def approach_faces(client,pos,expected_state,faces,seconds=90,stand_distance=None):
    if stand_distance is not None and not .25<=stand_distance<=3:raise ValueError('Standing distance must be within native bounds')
    faces=list(dict.fromkeys(faces))
    if len(faces)>6 or any(f not in {'up','down','north','south','east','west'} for f in faces):
        raise ValueError('At most six observed block faces are allowed')
    attempts=[]
    for face in faces:
        # A previous navigation attempt may have moved us. Recheck both scope and
        # the exact target before choosing another pose; this never repeats mining.
        client.status()
        rows=client.request('scan',min=pos,max=pos)['blocks']
        if len(rows)!=1 or rows[0]['state']!=expected_state:
            raise RuntimeError('Work target changed during access recovery')
        reply=client.request('approach_block',pos=pos,face=face,expected_state=expected_state,seconds=seconds,**({'stand_distance':stand_distance} if stand_distance is not None else {}))
        outcome='reached' if reply.get('phase')=='done' else 'blocked' if reply.get('phase') in ('error','waiting') and reply.get('detail') in BLOCKED_APPROACHES else 'unconfirmed'
        attempts.append({'face':face,'outcome':outcome,'detail':reply.get('detail')})
        with (client.out/'access-recovery.jsonl').open('a') as stream:
            stream.write(json.dumps({'time':int(time.time()*1000),'pos':pos,'expected_state':expected_state,'attempt':attempts[-1]},ensure_ascii=False)+'\n')
        if outcome=='reached':return face
        if outcome!='blocked':raise RuntimeError(reply.get('detail','Access not confirmed; inspect before continuing'))
    raise ApproachUnavailable('No verified access face after bounded alternatives')
