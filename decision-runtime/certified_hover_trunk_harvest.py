"""Journaled normal-input execution of a certified straight hover trunk plan.

Never calls grounded chop/walk, never clears outside the certified core, never
replays a pending step. Existing builder health and resident guards remain in
force, and the native safety interlock is checked before every action.
"""
from pathlib import Path
import time,math
from material_plan import inventory_counts
from kit_runtime.journal import write_json
from safety_interlock import require_unlocked
from ground_work_threat_survey import bounds,assess
from overhead_melee_clearance import separated


class DefensePriority(RuntimeError):pass

def run(builder,certificate,path,*,resume=False):
    import json
    path=Path(path)
    def state(allow_defense=False):
        s=builder.check();require_unlocked(builder.root,s);lease=s.get('supervision_lease')or{}
        if (s.get('world_session')!=certificate['world_session']or s.get('health')!=20
                or s.get('connected')is not True or s.get('manual_movement')is not False
                or s.get('guard_armed')is not True or s.get('guard_pve_only')is not True
                or s.get('screen')or lease.get('kind')!='materials'
                or lease.get('world_session')!=s['world_session']or not lease.get('job_session')
                or lease.get('revision')!=s.get('control_revision')):
            raise RuntimeError('Healthy current protected hover owner required')
        if s.get('guard_busy')and not allow_defense:raise DefensePriority('PvE input has priority')
        return s
    initial=state(allow_defense=True);task=initial['supervision_lease']['job_session']
    if path.exists():
        if not resume:raise RuntimeError('Original hover journal exists; do not replay it')
        book=json.loads(path.read_text())
        if book.get('pending')or book.get('complete')or book.get('certificate_hash')!=certificate['certificate_hash']or book.get('task')!=task:
            raise RuntimeError('Only a known same-owner paused journal can resume')
    else:
        if resume:raise RuntimeError('No journal to resume')
        book={'complete':False,'pending':None,'certificate_hash':certificate['certificate_hash'],'certificate':certificate,
              'world_session':certificate['world_session'],'task':task,'cursor':0,'steps':[],
              'logs_before':inventory_counts(initial)[certificate['log_item']], 'ground_scans':[]}
    def save():write_json(path,book)
    def nav(target):
        s=state()
        if math.dist(s['pos'],target)<.12:return
        book['pending']={'op':'navigate','target':target};save();builder.nav(target);book['pending']=None;save()
    def ground_ready(work_pose):
        before=state();low,high=bounds(certificate['root']);book['pending']={'op':'ground_threat_scan','min':low,'max':high};save()
        r=builder.n('scan',min=low,max=high,details=True)
        request={'op':'scan','min':low,'max':high,'details':True,'id':r['id'],'world_session':before['world_session'],
                 'task_session':task,'expected_revision':before['control_revision']}
        a=assess(request,r,certificate['root'],world=before['world_session'],task=task,revision=before['control_revision'],now_ms=int(time.time()*1000))
        a['work_pose']=work_pose;a['native_guarded_separation_admitted']=not a['safe_now']and separated(a['threats'],[work_pose])
        book['pending']=None;book['ground_scans'].append(a);save()
        if a['safe_now']or a['native_guarded_separation_admitted']:return True
        current=state();safe=certificate['safe_wait_hover']
        if current['pos'][1]<safe[1]:nav(safe)
        book['phase']='waiting_for_ground_threats';save();return False
    def execute_steps():
        save();root=certificate['root'];top=certificate['steps'][0]['hover'];s=state()
        if not s.get('flight'):raise RuntimeError('Start hover clearing from verified flight, not a grounded canopy pose')
        high=max(s['pos'][1],top[1]+2);nav([s['pos'][0],high,s['pos'][2]]);nav([top[0],high,top[2]])
        for index,step in enumerate(certificate['steps']):
            if index<book['cursor']:
                _,old=builder.scan(step['pos'],step['pos'])
                if tuple(step['pos'])in old:raise RuntimeError('A previously verified cleared cell changed; no repeat')
                continue
            if step['ground_threat_scan_required']and not ground_ready(step['hover']):return {'complete':False,'phase':book['phase'],'journal':str(path)}
            nav(step['hover']);actual=state()
            if math.dist(actual['pos'],step['hover'])>.4:
                book['phase']='waiting_after_owned_pose_changed';save();return {'complete':False,'phase':book['phase'],'journal':str(path)}
            _,rows=builder.scan(step['pos'],step['pos']);row=rows.get(tuple(step['pos']))
            if row is None:
                book['steps'].append({'index':index,'pos':step['pos'],'outcome':'already_air_observed_no_mining_or_drop_credit'});book['cursor']=index+1;save();continue
            if row['state']!=step['expected_state']or row.get('fluid')or row.get('block_entity'):raise RuntimeError('Certified core changed; no mining input')
            builder.n('select_item',item='minecraft:diamond_axe');state();book['pending']={'op':'mine_block','pos':step['pos'],'expected_state':step['expected_state']};save()
            r=builder.n('mine_block',pos=step['pos'],face='up',expected_state=step['expected_state'],seconds=15)
            book['pending']['native_reply']={k:r.get(k)for k in ['id','world_session','native_sequence','server_ack_sequence','server_confirmed']};save()
            if not(r.get('server_confirmed')and r.get('native_sequence',0)>0 and r.get('server_ack_sequence')==r['native_sequence']):raise RuntimeError('Original core removal not server-confirmed; never replay')
            _,after=builder.scan(step['pos'],step['pos'])
            if tuple(step['pos'])in after:raise RuntimeError('Original removed core is still occupied; no retry')
            book['steps'].append({'index':index,'pos':step['pos'],'kind':step['kind'],'outcome':'mined','request_id':r['id']});book['cursor']=index+1;book['pending']=None;save()
        _,core=builder.scan(root,[root[0],certificate['highest_core_y'],root[2]])
        if core:raise RuntimeError('Pickup core is not empty; no descent')
        expected=sum(s.get('kind')=='log'and s['outcome']=='mined'for s in book['steps']);wanted=book['logs_before']+expected
        if inventory_counts(state())[certificate['log_item']]<wanted:
            if not ground_ready(certificate['pickup_core']):return {'complete':False,'phase':book['phase'],'journal':str(path)}
            nav(certificate['pickup_core']);deadline=time.monotonic()+20;tried=set()
            while inventory_counts(state())[certificate['log_item']]<wanted:
                s=state();drops=[e for e in s.get('entities',[])if e.get('type')=='minecraft:item'and e.get('stack',{}).get('item')==certificate['log_item']and e.get('uuid')not in tried
                                and abs(e['pos'][0]-root[0]-.5)<=1.3 and abs(e['pos'][2]-root[2]-.5)<=1.3]
                if drops:
                    e=drops[0];tried.add(e['uuid']);target=[root[0]+.5,max(root[1]+.1,min(e['pos'][1]+.1,certificate['highest_core_y']+1.1)),root[2]+.5]
                    if target[1]-root[1]<8 and not ground_ready(target):return {'complete':False,'phase':book['phase'],'journal':str(path)}
                    nav(target)
                if time.monotonic()>deadline:raise RuntimeError('Known removed logs not all collected; never remine; inspect observed drops')
                time.sleep(.1)
        book.update(complete=True,phase='certified_trunk_cleared_drops_collected',logs_mined=expected,
                    logs_after=inventory_counts(state())[certificate['log_item']],no_grounded_chop_used=True,leaves_outside_core_not_claimed_clear=True);save()
        return {'complete':True,'logs_mined':expected,'log_gain':book['logs_after']-book['logs_before'],'journal':str(path)}
    try:return execute_steps()
    except DefensePriority:
        if book.get('pending'):raise
        book['phase']='waiting_for_defense';save();return {'complete':False,'phase':book['phase'],'journal':str(path)}
