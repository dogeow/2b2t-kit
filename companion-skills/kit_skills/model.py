"""Declarative skills and objective evidence. Generated text is never executed as code."""
import hashlib,json,math,re

OPS={
 'navigate':{'target','arrival','seconds'},
 'walk':{'target','arrival','seconds','restore_flight'},
 'chop':{'item','target_count','seconds'},
 'professional_print':{'seconds','conservative'},
 'scan':{'min','max'},
}
CHECKS={'inventory_at_least','position_near','server_placements_at_least'}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def resolve(value,params):
    if isinstance(value,dict):
        if set(value)=={'param'}:
            if value['param'] not in params:raise ValueError('Missing parameter: '+str(value['param']))
            return params[value['param']]
        return {k:resolve(v,params) for k,v in value.items()}
    if isinstance(value,list):return [resolve(v,params) for v in value]
    return value
def validate(skill):
    if skill.get('schema')!=1 or not re.fullmatch(r'[a-z][a-z0-9_]{2,63}',skill.get('name','')):raise ValueError('Invalid skill name or schema')
    if not isinstance(skill.get('description'),str) or not 1<=len(skill['description'])<=1000:raise ValueError('Missing bounded description')
    if not isinstance(skill.get('parameters',{}),dict):raise ValueError('Invalid parameters')
    if not isinstance(skill.get('steps'),list) or not 1<=len(skill['steps'])<=12:raise ValueError('A skill needs 1..12 steps')
    for step in skill['steps']:
        if set(step)!={'op','args'} or step['op'] not in OPS:raise ValueError('Unsupported Kit capability')
        if not isinstance(step['args'],dict) or set(step['args'])-OPS[step['op']]:raise ValueError('Unsupported arguments')
    if not skill.get('success') or any(c.get('type') not in CHECKS for c in skill['success']):raise ValueError('Objective success checks are required')
    def refs(v):
        if isinstance(v,dict):
            if set(v)=={'param'} and v['param'] not in skill.get('parameters',{}):raise ValueError('Undeclared parameter')
            for x in v.values():refs(x)
        elif isinstance(v,list):
            for x in v:refs(x)
    refs(skill['steps']);refs(skill['success'])
    if len(json.dumps(skill))>24000:raise ValueError('Skill too large')
    return skill
def vector(v):
    return isinstance(v,list) and len(v)==3 and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) for n in v)
def validate_action(op,args):
    if op not in OPS or set(args)-OPS[op]:raise ValueError('Unsupported action')
    if op in ('walk','navigate'):
        if not vector(args.get('target')):raise ValueError('Target must be a finite XYZ vector')
        if not .1<=args.get('arrival',1)<=8:raise ValueError('Invalid arrival radius')
    if 'seconds' in args and (not isinstance(args['seconds'],(int,float)) or not 1<=args['seconds']<=(30 if op=='professional_print' else 600)):raise ValueError('Unbounded action duration')
    if op=='chop':
        if not re.fullmatch(r'minecraft:[a-z0-9_]+_log',args.get('item','minecraft:oak_log')):raise ValueError('Chop supports a specific vanilla log type')
        if not isinstance(args.get('target_count'),int) or not 1<=args['target_count']<=512:raise ValueError('Invalid collection target')
    if op=='scan':
        if not vector(args.get('min')) or not vector(args.get('max')):raise ValueError('Missing scan bounds')
        spans=[b-a+1 for a,b in zip(args['min'],args['max'])]
        if any(v<=0 for v in spans) or math.prod(spans)>50000:raise ValueError('Invalid scan volume')
def inventory(state):
    out={}
    for s in state.get('inventory',[]):
        if 0<=s.get('slot',-1)<36 and s.get('item')!='minecraft:air':out[s['item']]=out.get(s['item'],0)+s.get('count',0)
    return out
def same_world(a,b):return all(a.get(k) and a.get(k)==b.get(k) for k in ('server','dimension'))
def check_success(check,before,after):
    kind=check['type']
    if kind=='inventory_at_least':return inventory(after).get(check['item'],0)>=check['count']
    if kind=='position_near':
        return vector(after.get('pos')) and vector(check.get('target')) and math.dist(after['pos'],check['target'])<=check.get('radius',1.2)
    if kind=='server_placements_at_least':
        p=after.get('professional_printer',{})
        return not p.get('failure') and not p.get('waiting_for_server') and p.get('server_confirmed',0)>=check.get('count',1)
    return False
def verify_episode(skill,episode):
    """Both transport completion and independent state evidence are necessary."""
    validate(skill);params=episode.get('parameters',{});before=episode.get('before',{});after=episode.get('after',{})
    if not before.get('connected') or not after.get('connected') or not same_world(before,after):return False,'world changed or disconnected'
    if not isinstance(before.get('time'),(int,float)) or not isinstance(after.get('time'),(int,float)) or after['time']<=before['time']:return False,'missing ordered snapshots'
    if after.get('health',0)<14:return False,'health below skill acceptance threshold'
    actual=episode.get('actions',[]);steps=resolve(skill['steps'],params)
    if len(actual)!=len(steps):return False,'action trace incomplete'
    for expected,seen in zip(steps,actual):
        request=seen.get('request',{});result=seen.get('result',{})
        validate_action(expected['op'],expected['args'])
        if request.get('op')!=expected['op'] or {k:v for k,v in request.items() if k not in {'op','id','server','dimension','site'}}!=expected['args']:return False,'trace differs from proposed skill'
        if not request.get('id') or result.get('id')!=request['id'] or result.get('phase')!='done' or result.get('last_request',request['id'])!=request['id']:return False,'request was not confirmed complete'
        if not same_world(request,before) or not same_world(result,after):return False,'action context differs'
    checks=resolve(skill['success'],params)
    if not all(check_success(c,before,after) for c in checks):return False,'objective result not reached'
    return True,'objective result verified'
