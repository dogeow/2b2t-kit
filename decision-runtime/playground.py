"""Chinese, manually launched menu for the already validated marker demo."""
import json
import math
import re
import time
import uuid
from pathlib import Path
from decisions import PRIVATE, DecisionError, provider, choose, status, validate_local_scene, execute_walk

TEST_ROOT=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation')
TARGETS={'yellow':[10.5,-60,9.5],'blue':[6.5,-60,13.5]}
CHOICES={'yellow':'Walk to the yellow marker.','blue':'Walk to the blue marker.','wait':'Stay still; do not walk anywhere.'}
LABELS={'yellow':'黄色标记','blue':'蓝色标记','wait':'原地等待'}
MESSAGES={
    'Decision is too old for game control':'模型这次回复较慢，已放弃旧指令。可重新选择 3 再试。',
    'Player moved during inference; discard the answer':'模型判断时角色移动了，已取消这次动作。',
    'Another controller took over during inference':'其他操作已接管角色，这次没有移动。',
    'Menu, health, defense or an existing task currently owns control':'请关闭游戏菜单，并先结束其他任务；低血量或防护接管时也不会执行。',
    'Game observation is stale':'没有读到新的游戏状态，请确认测试实例正在运行。',
    'TypeSafe network request failed; no automatic retry':'Jev 请求失败，没有自动重试或操作游戏。稍后可重新选择。',
}
SAFE_FLOOR=re.compile(r'Block\{minecraft:(?:grass_block|dirt|stone|white_wool|yellow_wool|blue_wool)\}(?:\[.*\])?')

def ready(timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            s=status(TEST_ROOT);validate_local_scene(s,s)
            if s.get('window_active'):
                return s
        except (DecisionError,OSError,ValueError): pass
        time.sleep(.25)
    raise DecisionError('30 秒内未等到测试世界。请进入 Jev Local Test 20260921，关闭菜单，切回游戏并松开移动键。')

def scan_area(before,root=TEST_ROOT):
    current=status(root);validate_local_scene(before,current)
    existing=root/'request.json'
    if existing.exists() and json.loads(existing.read_text()).get('id')!=current.get('last_request'):
        raise DecisionError('游戏还有其他待处理请求，请先完成或停止它。')
    request={'id':'jev-scan-'+uuid.uuid4().hex[:12],'op':'scan','server':'singleplayer','dimension':'minecraft:overworld',
             'site':current['pos'],'min':[5,-61,8],'max':[11,-59,14]}
    temp=root/(request['id']+'.tmp');temp.write_text(json.dumps(request));temp.replace(existing)
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        reply=root/('reply-'+request['id']+'.json')
        if reply.exists():
            data=json.loads(reply.read_text())
            if data.get('id')!=request['id'] or 'blocks' not in data:raise DecisionError('无法完成测试场地扫描。')
            current=status(root)
            if current.get('last_request')!=request['id']:raise DecisionError('扫描后有其他控制器接管，已取消。')
            expected={**before,'last_request':request['id']};validate_local_scene(expected,current)
            return current,data['blocks']
        time.sleep(.1)
    raise DecisionError('场地扫描未确认，未发出移动。')

def marker_plan(goal,s,rows):
    validate_local_scene(s,s)
    x,y,z=s['pos']
    if not (5.3<=x<=11.7 and 8.3<=z<=14.7 and abs(y+60)<=.15):
        raise DecisionError('请先站到测试世界的白色、蓝色或黄色标记附近，落到地面后再试。')
    blocks={tuple(row['pos']):row['state'] for row in rows}
    for bx in range(5,12):
        for bz in range(8,15):
            if not SAFE_FLOOR.fullmatch(blocks.get((bx,-61,bz),'')):
                raise DecisionError('测试区域的地面已改变或有坑，未移动。')
            if (bx,-60,bz) in blocks or (bx,-59,bz) in blocks:
                raise DecisionError('测试通道里有障碍，未移动。')
    for p,name in [((6,-61,9),'white_wool'),((10,-61,9),'yellow_wool'),((6,-61,13),'blue_wool')]:
        if blocks.get(p)!='Block{minecraft:'+name+'}':raise DecisionError('没有找到原来的三个标记，请确认进入的是验收世界。')
    targets={k:v for k,v in TARGETS.items() if math.dist(s['pos'],v)<=6}
    if not targets:raise DecisionError('当前位置没有六格以内的目标。')
    choices={k:CHOICES[k] for k in targets};choices['wait']=CHOICES['wait']
    return {'goal':goal,'origin':s['pos'],'targets':targets,'choices':choices,
            'scene':{'game':'Minecraft','markers':list(targets),'test_area':'flat floor and clear body space verified from current game scan'}}

def show(result):
    print(f"\n模型选择：{LABELS.get(result['choice'],result['choice'])}；置信度 {result['confidence']:.0%}；耗时 {result['elapsed_ms']:.0f} 毫秒")
    control=result.get('control',{})
    if control.get('verified'):print('已核对游戏位置：到达目标。')
    elif control.get('phase')=='rejected':
        reason=control.get('reason','检查未通过');print('本次未执行：'+MESSAGES.get(reason,reason))
    elif control.get('executed'):print('动作已发送，但未确认完成；请查看游戏，不会自动重试。')
    else:print('没有操作游戏。' if control.get('mode')=='advice' else '置信度不足，没有移动。' if result['confidence']<.75 else '保持原地，没有发出移动。')

def main():
    clients={}
    print('Minecraft AI 体验\n标记移动演示，以及本机开局试运行。尚不支持自动通关。')
    try:
        while True:
            print('\n1  Jev 判断（联网，不操作游戏）\n2  Laya 判断（本机，不操作游戏）\n3  旧标记测试（开发用）\n4  旧营地原型（开发用）\n5  旧铁装备原型（开发用）\n6  启动/托管选中投影（Jev＋Kit，自动记录经验）\n0  退出')
            selected=input('请选择：').strip()
            if selected=='0':return
            if selected=='6':
                from build_supervisor import run_supervision
                try:
                    candidates=[]
                    for root in (TEST_ROOT,Path('/Applications/.minecraft/config/twob2tkit/automation')):
                        try:
                            current=status(root)
                            if current.get('connected') and current.get('supervision_protocol',0)>=1:candidates.append((root,current))
                        except (DecisionError,OSError,ValueError):pass
                    if not candidates:raise DecisionError('先进入带 Kit 1.9.45 的游戏，并选中要托管的投影。')
                    for i,(root,s) in enumerate(candidates,1):print(f"{i}：{s['server']} / {s.get('world_name') or '多人世界'} / {(s.get('build_job',{}).get('name') if s.get('build_job',{}).get('active') else s.get('projection_selection',{}).get('name')) or '未选中投影'}")
                    index=0 if len(candidates)==1 else int(input('选择正在玩的实例：'))-1
                    if not 0<=index<len(candidates):raise DecisionError('实例选择无效。')
                    root,s=candidates[index]
                    print('只托管当前投影：可复查、重规划、从已允许的仓库补料、合成缺失木板并续建；不会恢复你手动停止的任务。')
                    print('正常进展不问模型；默认 Jev 上限 120 次/小时。ChatGPT 不会被自动轮询；新问题保存成合并案例。')
                    print('结束/失联：单人世界暂停，多人服自动退出；手动移动或急停撤销托管。')
                    run_supervision(root,s['server'],s.get('world_name') if s['server']=='singleplayer' else None,True,start_selected=not s.get('build_job',{}).get('active'))
                except (DecisionError,OSError,ValueError) as error:print('托管停止：'+str(error))
                continue
            if selected in ('4','5'):
                from survival import Runner
                from survival_bridge import Bridge,valid
                print('只用于名称以 Jev 开头的独立生存测试存档；需要附近有树、裸露石料、动物和 5×5 平地。')
                minutes=45 if selected=='5' else 30
                print(f'预算：最多 {minutes} 分钟、24 次模型调用。遇敌、卡住或人工接管会暂停；这不是无人值守防护。')
                print('切回游戏并关闭菜单，最多等 30 秒。U → 紧急停止全部，或 WASD 接管即可停止。',flush=True)
                try:
                    deadline=time.monotonic()+30;before=None
                    while time.monotonic()<deadline:
                        try:
                            before=status(TEST_ROOT)
                            valid(before,before.get('world_name',''))
                            if not before.get('world_name','').startswith('Jev '):raise DecisionError('请进入独立的 Jev 测试存档。')
                            if not before.get('screen'):break
                        except (DecisionError,OSError,ValueError):before=None
                        time.sleep(.25)
                    if before is None:raise DecisionError('没有等到可用的独立生存测试世界。')
                    if 'jev' not in clients:clients['jev']=provider('jev')
                    folder=PRIVATE/'survival'/time.strftime('%Y%m%d-%H%M%S')
                    previous=PRIVATE/'survival'/'resume.json';resume=None
                    if previous.exists():
                        saved=json.loads(previous.read_text())
                        if saved.get('world_name')==before['world_name'] and saved.get('world_id')==before.get('world_id') and math.hypot(saved['origin'][0]-before['pos'][0],saved['origin'][2]-before['pos'][2])<=24:resume=previous
                    runner=Runner(Bridge(TEST_ROOT,before['world_name']),clients['jev'],folder,max_minutes=minutes,resume=resume,iron=selected=='5')
                    try:runner.run()
                    finally:
                        if (folder/'status.json').exists():previous.write_text((folder/'status.json').read_text())
                except (DecisionError,OSError,ValueError) as error:print('已暂停：'+str(error))
                continue
            if selected not in ('1','2','3'):continue
            goal=input('输入一句话，如“走到黄色标记”或“原地等待”（回车用黄色）：').strip() or '走到黄色标记。'
            name='laya' if selected=='2' else 'jev'
            try:
                if name not in clients:
                    print('正在准备模型……');clients[name]=provider(name)
                before=None
                if selected=='3':
                    print('现在切回 Minecraft，进入游戏画面并松开移动键。最多等 30 秒；只执行一次，完成后回这个窗口查看结果。',flush=True)
                    before,blocks=scan_area(ready());plan=marker_plan(goal,before,blocks)
                else:plan={'goal':goal,'choices':CHOICES,'scene':{'game':'Minecraft','markers':['yellow','blue']}}
                result=choose(clients[name],goal,plan['choices'],plan['scene'])
                if before:
                    try:result['control']=execute_walk(plan,result,before,TEST_ROOT)
                    except DecisionError as error:result['control']={'executed':False,'phase':'rejected','reason':str(error)}
                else:result['control']={'executed':False,'mode':'advice'}
                results=PRIVATE/'results';results.mkdir(exist_ok=True)
                (results/'latest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
                show(result)
            except (DecisionError,OSError,ValueError) as error:print('未继续执行：'+MESSAGES.get(str(error),str(error)))
    finally:
        for client in clients.values():client.close()

if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError):print('\n已退出。若游戏仍有动作，请用 U → 紧急停止全部。')
