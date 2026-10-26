"""Plan a fully observed straight natural trunk from above; no game input here.

Grounded chopping is deliberately absent. A live executor must keep ordinary
health/ownership guards, resurvey threats before low steps, and never replay an
unconfirmed removal or credit uncollected drops.
"""
import hashlib,json,math
from survival_world import block_id

SOIL={'grass_block','dirt','coarse_dirt','rooted_dirt','podzol','moss_block'}

def plan(root,scene,low,high,*,world,log='oak_log',leaf='oak_leaves'):
    pairs={f'{wood}_log':f'{wood}_leaves'for wood in ['oak','birch','spruce','jungle','acacia','dark_oak','mangrove','cherry','pale_oak']}
    if pairs.get(log)!=leaf or not isinstance(world,str)or not world:raise ValueError('Explicit natural species and current world required')
    if (not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3):raise ValueError('Inclusive observed bounds required')
    if (not isinstance(root,list)or len(root)!=3 or any(type(n)is not int for n in root)
            or any(type(n)is not int for n in low+high)or len(low)!=3 or len(high)!=3
            or not all(a<=r<=b for a,r,b in zip(low,root,high))):raise ValueError('Exact witnessed root and bounds required')
    volume=math.prod(b-a+1 for a,b in zip(low,high))
    if (scene.get('phase')!='done'or scene.get('world_session')!=world or scene.get('scan_cells_read')!=volume
            or scene.get('scan_total_cells')!=volume or scene.get('scan_start_revision')!=scene.get('scan_end_revision')):
        raise ValueError('Complete same-world native scan required')
    rows={}
    for row in scene['blocks']:
        p=row.get('pos')
        if not isinstance(p,list)or len(p)!=3 or any(type(n)is not int for n in p)or not all(a<=v<=b for a,v,b in zip(low,p,high))or tuple(p)in rows:raise ValueError('Distinct native cells inside the observed bounds required')
        rows[tuple(p)]=row
    x,y,z=root;soil=rows.get((x,y-1,z),{})
    if block_id(soil.get('state',''))not in SOIL or not soil.get('solid')or soil.get('fluid'):raise ValueError('Natural dry rooted soil required')
    if any(r.get('block_entity')and abs(p[0]-x)<=1 and abs(p[2]-z)<=1 for p,r in rows.items()):raise ValueError('Bee nests and other block entities remain protected')
    leaves=[r for r in rows.values()if block_id(r['state'])==leaf and 'persistent=false'in r['state']]
    if len(leaves)<4:raise ValueError('Natural canopy evidence required')
    logs={p for p,r in rows.items()if block_id(r['state'])==log};connected={(x,y,z)};pending=[(x,y,z)]
    if (x,y,z)not in logs:raise ValueError('Root log absent')
    while pending:
        p=pending.pop()
        for a in logs-connected:
            if max(abs(a[i]-p[i])for i in range(3))<=1:connected.add(a);pending.append(a)
    if any(p[0]!=x or p[2]!=z for p in connected):raise ValueError('Branched or touching trunks need their own bounded plan')
    heights=sorted(p[1]for p in connected)
    if heights!=list(range(y,max(heights)+1))or not 1<=len(heights)<=32:raise ValueError('One continuous witnessed trunk required')
    core=[(p,r)for p,r in rows.items()if p[0]==x and p[2]==z and p[1]>=y]
    top=max(p[1]for p,r in core)
    if high[1]<max(top+4,y+14):raise ValueError('Top hover body and escape column are not observed')
    steps=[]
    for p,row in sorted(core,reverse=True):
        name=block_id(row['state'])
        if type(row.get('fluid'))is not bool or type(row.get('block_entity'))is not bool:raise ValueError('Detailed native fluid and container evidence required')
        if name==log and(p not in connected or 'axis=y'not in row['state']):raise ValueError('Only the connected vertical trunk is certified')
        if 'waterlogged=true'in row['state']:raise ValueError('Wet core is not an air escape column')
        if name not in [log,leaf]or row.get('fluid')or row.get('block_entity')or(name==leaf and 'persistent=false'not in row['state']):raise ValueError('Only certified logs and natural core leaves may be cleared')
        steps.append({'pos':list(p),'expected_state':row['state'],'kind':'log'if name==log else'core_leaf','hover':[x+.5,p[1]+2.1,z+.5],'ground_threat_scan_required':p[1]+2.1-y<8})
    payload={'world_session':world,'root':root,'steps':steps,'expected_logs':len(heights),'log_item':'minecraft:'+log,'highest_core_y':top,'safe_wait_hover':[x+.5,max(top+2.1,y+12.1),z+.5],'pickup_core':[x+.5,y+.1,z+.5],'pickup_requires_fresh_ground_threat_scan':True,'grounded_walk_or_chop_allowed':False,'original_scan_scope':'blocks sampled across client ticks; live state must be checked before each input'}
    payload['certificate_hash']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();return payload
