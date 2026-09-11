"""Turn observed Kit transactions into parameterized skill candidates without an LLM call."""
from .model import OPS,validate_action,verify_episode,digest

META={'id','op','server','dimension','site'}
def skill_from_request(request):
    op=request.get('op');args={k:v for k,v in request.items() if k not in META}
    validate_action(op,args)
    if op=='scan':raise ValueError('Observations are evidence, not learned action skills')
    parameters={k:{'required':True} for k in args};bindings={k:{'param':k} for k in args}
    if op=='chop':
        item=args.get('item','minecraft:oak_log');bindings['item']={'param':'item'};parameters['item']={'required':True}
        name='collect_logs';description='采集指定类型原木，检查实际背包达到目标数量；适用于 Kit 自动砍树。';success=[{'type':'inventory_at_least','item':{'param':'item'},'count':{'param':'target_count'}}]
    elif op in ('walk','navigate'):
        name='walk_to_worksite' if op=='walk' else 'navigate_to_worksite';description='前往指定施工点，完成后核对实际 XYZ 位置；遵循当前服务器和维度范围。'
        success=[{'type':'position_near','target':{'param':'target'},'radius':{'param':'arrival'} if 'arrival' in args else (0.65 if op=='walk' else 1.5)}]
    else:
        name='print_nearby_batch';description='在当前站位短时打印可放置的投影方块，用服务器确认验收本批次；不代表整栋建筑完成。'
        success=[{'type':'server_placements_at_least','count':1}]
    return {'schema':1,'name':name,'description':description,'tags':[op,'minecraft','kit'],'parameters':parameters,'preconditions':{'min_health':14,'connected':True,'same_server_dimension':True,'controller':'kit'},'steps':[{'op':op,'args':bindings}],'success':success}
def learn_transaction(manager,request,before,after):
    detail=after.get('detail','')
    if not after.get('connected') or any(x in detail for x in ('手动','接管','紧急停止','本地脚本停止','退出游戏','离开世界')):
        manager.lesson({'kind':'interrupted','request_id':request.get('id'),'reason':detail});return {'status':'lesson','reason':'interrupted; not a failed skill'}
    try:skill=skill_from_request(request)
    except ValueError as e:
        manager.lesson({'kind':'unlearned_operation','op':request.get('op'),'reason':str(e),'request_id':request.get('id')});return {'status':'lesson','reason':str(e)}
    params={k:v for k,v in request.items() if k not in META}
    if request['op']=='chop':params.setdefault('item','minecraft:oak_log')
    # The actual request may omit Kit's oak default; normalize that one documented default.
    req=dict(request)
    if req['op']=='chop':req.setdefault('item','minecraft:oak_log')
    episode={'id':request['id'],'before':before,'after':after,'parameters':params,'actions':[{'request':req,'result':after}]}
    success,reason=verify_episode(skill,episode)
    result=manager.record(skill,episode,success,reason,observed=True)
    if not success:manager.lesson({'kind':'execution_failed','skill':skill['name'],'reason':reason,'detail':after.get('detail',''),'episode':episode['id']})
    return result
def propose_from_ai(manager,document):
    """A model can propose a new DSL program; its claimed success never promotes it."""
    return manager.add_new_skill(document)
def learn_episode(manager,document):
    skill=document['skill'];episode=document['episode'];ok,reason=verify_episode(skill,episode)
    return manager.record(skill,episode,ok,"imported evidence; native observation required: "+reason)
