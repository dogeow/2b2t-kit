"""Bounded local Survival bootstrap: observed resources, normal interactions, verified milestones.

This is deliberately not a speedrun or an unattended hostile-world controller.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

from decisions import PRIVATE,DecisionError,Jev,choose
from survival_bridge import Bridge,Paused,inventory,valid
from survival_world import World,block_id,cell,center,distance,shelter

ROOT=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation')
LOGS={s+'_log' for s in ('oak','birch','spruce','acacia','dark_oak','jungle','mangrove','cherry','pale_oak')}
RAW={'beef':'cooked_beef','porkchop':'cooked_porkchop','chicken':'cooked_chicken','mutton':'cooked_mutton'}
FOOD=set(RAW.values())|{'apple','bread','baked_potato','cooked_salmon','cooked_cod'}
FACES=[((0,-1,0),'up'),((1,0,0),'west'),((-1,0,0),'east'),((0,0,1),'north'),((0,0,-1),'south')]
TASKS={
 'bootstrap_iron':('Establish a starter camp and obtain iron armor, an iron pickaxe, an iron sword and a shield.', 'Run the local starter-camp workflow, then gather accessible iron ore, smelt it, craft the specified iron equipment, equip the armor and shield, and return inside the shelter. Stop on unhandled risks or missing resources.'),
 'bootstrap':('Establish a Survival starter camp with tools, cooked food and an enclosed shelter.', 'Run the bounded local starter-camp routine: collect starting materials, craft wood and stone tools, obtain cooked food, and build and enter a small enclosed shelter. Stop on any unhandled risk or missing prerequisite.'),
 'wood':('Collect the required starting logs.','Find reachable logs, mine them with normal interactions and pick up the drops until the supplied inventory target is reached.'),
 'craft':('Make a crafting table and wooden pickaxe from the collected logs.','Convert logs to planks, craft sticks and a table, place the table, then craft a wooden pickaxe.'),
 'stone':('Collect cobblestone for stone tools and a furnace.','Use the wooden pickaxe to mine reachable stone and collect the required cobblestone.'),
 'tools':('Make stone tools and a furnace from the collected materials.','Use the table to craft a stone pickaxe, stone axe and furnace; the workflow crafts prerequisite sticks from logs when needed.'),
 'food':('Get a reserve of cooked food.','Use the stone axe to hunt nearby food animals, collect raw meat, place the furnace, fuel it with planks and collect cooked food.'),
 'shelter_material':('Collect the remaining dirt needed for the starter shelter.','Mine reachable dirt outside the protected camp footprint and collect the specified quantity.'),
 'shelter':('Build the planned starter shelter and go inside.','Place the planned dirt walls and roof, install the crafted wooden door, enter and close the door. Recheck every placement.'),
}

class Runner:
    def __init__(self,bridge,model,output,max_minutes=30,max_calls=24,resume=None,iron=False):
        self.b=bridge;self.model=model;self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.start=time.monotonic();self.deadline=self.start+max_minutes*60;self.max_calls=max_calls;self.calls=0
        self.camp=None;self.stations={};self.owned={};self.world=None;self.excluded=set();self.stage='starting';self.iron_target=iron;self.camp_completed=False;self.progress={}
        if resume:
            saved=json.loads(Path(resume).read_text())
            if saved['world_name']!=self.b.world or saved['automation']!=str(self.b.root) or saved.get('world_id')!=self.b.state.get('world_id') or math.hypot(saved['origin'][0]-self.b.origin[0],saved['origin'][2]-self.b.origin[2])>24:raise Paused('续跑记录与当前存档或位置不匹配。')
            self.b.origin=saved['origin']
            self.camp=saved['camp'];self.stations=saved['stations'];self.owned=saved.get('owned',{})
        self.b.events=self.event
    def event(self,kind,**data):
        with (self.output/'events.jsonl').open('a') as stream:stream.write(json.dumps({'time':time.time(),'event':kind,**data},ensure_ascii=False)+'\n')
    def save(self,phase,reason=''):
        state={'phase':phase,'stage':self.stage,'reason':reason,'world_name':self.b.world,'automation':str(self.b.root),
               'origin':self.b.origin,'world_id':self.b.state.get('world_id'),'camp':self.camp,'stations':self.stations,'owned':self.owned,'model_calls':self.calls,
               'inventory':inventory(self.b.state),'elapsed_seconds':round(time.monotonic()-self.start,1),
               'target':'iron' if self.iron_target else 'camp','camp_completed':self.camp_completed,'progress':self.progress}
        temp=self.output/'status.tmp';temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.replace(self.output/'status.json')
    def check(self):
        if time.monotonic()>self.deadline:raise Paused('本轮时间预算用完，已保存进度。')
        self.b.read()
    def scan(self):
        self.check();x,y,z=cell(self.b.state['pos'])
        lo=[x-16,y-7,z-16];hi=[x+16,y+9,z+16]
        result=self.b.request('scan',min=lo,max=hi,details=True)
        self.world=World(result['blocks'],lo,hi);return self.world
    def count(self,item):return inventory(self.b.read()).get(item,0)
    def decide(self,key,label,details):
        self.check()
        if self.calls>=self.max_calls:raise Paused('本轮模型调用预算用完，已保存进度。')
        before=self.b.read();goal,workflow=TASKS[key]
        choices={key:'Run this workflow: '+workflow,'wait':'The request does not match this supported workflow, or the user explicitly asks to wait.'}
        result=choose(self.model,goal,choices,
                      {'purpose':'Route the user request to a supported workflow. The local executor separately verifies every prerequisite and game action.'})
        self.calls+=1;self.event('decision',**result);after=self.b.read()
        if result['elapsed_ms']>5000 or distance(before['pos'],after['pos'])>.3:raise Paused('模型回复过期或角色移动，本次未执行。')
        if result['choice']=='wait' or result['confidence']<.75:raise Paused('Jev 本次选择等待或判断不确定。')
        self.stage=label;self.save('running');print(label,flush=True)
    def planned(self,key,label,details):
        self.check();self.stage=label;self.progress={};self.event('local_stage',skill=key,details=details);self.save('running');print(label,flush=True)
    def report_progress(self,item,done,total):
        progress={'item':item,'done':done,'total':total}
        if progress==self.progress:return
        self.progress=progress;self.event('progress',**progress);self.save('running')
        if done==total or done%5==0:print(f'{item}：{done}/{total}',flush=True)
    def walk(self,path):
        if path and self.b.state.get('bridge_version',0)>=3:
            for offset in range(0,len(path),24):
                batch=path[offset:offset+24];self.check()
                result=self.b.request('walk_path',path=[center(p) for p in batch],arrival=.18,seconds=max(10,len(batch)*3),restore_flight=False)
                if distance(result['pos'],center(batch[-1]))>.7:raise Paused('Kit 路径技能没有到达已检查的终点。')
            return
        for p in path:
            self.check()
            result=self.b.request('walk',target=center(p),arrival=.23,seconds=5,restore_flight=False)
            if distance(result['pos'],center(p))>.7:raise Paused('没有到达已检查的站位。')
    def go_near(self,target,reach=3.6):
        w=self.scan();parents=w.paths(self.b.state['pos']);stance=w.approach(parents,target,reach)
        if stance is None:raise Paused('当前扫描范围内没有安全可达的操作位置。')
        self.walk(w.route(parents,stance))
    def collect(self,wanted):
        self.b.wait(.8)
        for _ in range(20):
            self.check();s=self.b.read();drops=[e for e in s.get('entities',[]) if e.get('stack',{}).get('item','').removeprefix('minecraft:') in wanted]
            if not drops:return
            w=self.scan();parents=w.paths(self.b.state['pos']);options=[]
            for e in drops:
                near=[p for p in parents if distance(center(p),e['pos'])<1.15]
                for p in near:options.append((len(w.route(parents,p)),p))
            if not options:return
            _,p=min(options);self.walk(w.route(parents,p));self.b.wait(.8)
    def equip_tool(self,resource):
        inv=inventory(self.b.read())
        candidates=['stone_axe','wooden_axe'] if resource in LOGS else ['iron_pickaxe','stone_pickaxe','wooden_pickaxe'] if resource in ('stone','coal_ore','iron_ore') else ['stone_shovel','wooden_shovel']
        selected=next((name for name in candidates if inv.get(name)),None)
        if selected:self.b.select(selected)
    def gather(self,names,wanted,total):
        def amount():return sum(inventory(self.b.read()).get(i,0) for i in wanted)
        failures=0;pending_blocks=0
        while amount()<total:
            self.check();self.b.close();w=self.scan()
            protected=set(self.excluded)
            if self.camp:
                cx,cy,cz=self.camp
                protected.update(p for p in w.blocks if abs(p[0]-cx)<=3 and abs(p[2]-cz)<=3)
                # Obtain building soil from banks/mounds instead of hollowing the camp's approach floor.
                if wanted=={'dirt'}:protected.update(p for p in w.blocks if p[1]<cy)
            for station in self.stations.values():
                protected.update({tuple(station),(station[0],station[1]-1,station[2])})
            found=w.resource(self.b.state['pos'],names,protected)
            if not found:raise Paused('附近没有可安全触及的 '+ '/'.join(sorted(names))+'；请在资源附近重新开始。')
            target,path=found;before=amount();self.walk(path);w=self.scan();row=w.row(target)
            if not row:continue
            self.equip_tool(w.name(target));w=self.scan()
            try:self.b.request('mine_block',pos=list(target),expected_state=w.row(target)['state'],seconds=18)
            except Paused as error:
                if str(error) not in ('mining target is occluded','Mining target out of reach','mining target moved out of reach'):raise
                failures+=1;self.excluded.add(target);self.event('skip_occluded_target',target=target,reason=str(error))
                if failures>=3:raise Paused('连续三个候选位置不可操作，暂停检查。') from error
                continue
            self.b.wait(.4);w=self.scan()
            if w.name(target)!='air':raise Paused('挖掘没有得到稳定的方块消失确认。')
            self.collect(wanted)
            if amount()<=before:
                visible=sum(e.get('stack',{}).get('count',0) for e in self.b.read().get('entities',[]) if e.get('stack',{}).get('item','').removeprefix('minecraft:') in wanted)
                if visible:
                    pending_blocks+=1;self.event('drops_pending',count=visible,cleared_blocks=pending_blocks)
                    if pending_blocks>=12:raise Paused('已有掉落物但暂时不可达，暂停避免继续堆积。')
                else:
                    failures+=1;self.excluded.add(target)
                    if failures>=3:raise Paused('连续三次未确认材料入包，暂停检查。')
            else:failures=0;pending_blocks=0
            self.event('material',items=sorted(wanted),count=amount(),target=total);self.report_progress('/'.join(sorted(wanted)),amount(),total)
    def interact(self,pos,face='up'):
        w=self.scan();row=w.row(tuple(pos))
        if not row:raise Paused('交互方块已改变。')
        return self.b.request('interact',pos=list(pos),face=face,expected_state=row['state'],expected_hand=self.b.state['hand']['item'])
    def place(self,item,target):
        target=tuple(target);self.b.close();w=self.scan()
        if w.name(target)==item or item=='dirt' and w.earth(target):return
        if w.name(target)!='air':raise Paused('放置位置被占用，保留原方块。')
        parents=w.paths(self.b.state['pos']);options=[]
        for delta,face in FACES:
            support=tuple(a+b for a,b in zip(target,delta))
            if not w.full(support) or w.row(support).get('block_entity'):continue
            for stance in parents:
                if target in (stance,(stance[0],stance[1]+1,stance[2])):continue
                eye=[stance[0]+.5,stance[1]+1.62,stance[2]+.5]
                if distance(eye,[v+.5 for v in support])<=3.8 and w.sight(stance,support):options.append((len(w.route(parents,stance)),support,face,stance))
        if not options:raise Paused('放置位置没有安全可达的支撑面。')
        _,support,face,stance=min(options);self.walk(w.route(parents,stance));self.b.select(item);self.interact(support,face)
        w=self.scan()
        if w.name(target)!=item:raise Paused('放置结果与目标不符，未继续。')
        self.owned[','.join(map(str,target))]=item;self.save('running')
    def station(self,name):
        self.b.close()
        if name not in self.stations:
            w=self.scan();parents=w.paths(self.b.state['pos']);cx,cy,cz=self.camp
            spots=[p for p in parents if w.name(p)=='air' and (abs(p[0]-cx)>2 or abs(p[2]-cz)>2) and distance(center(p),center(self.camp))<8]
            spots.sort(key=lambda p:len(w.route(parents,p)))
            if not spots:raise Paused('没有空置的工作台/熔炉位置。')
            target=next((p for p in spots if p!=cell(self.b.state['pos'])),None)
            if target is None:raise Paused('没有空置的工作位置。')
            self.place(name,target);self.stations[name]=list(target);self.save('running')
        target=self.stations[name];self.go_near(target);w=self.scan()
        if w.name(tuple(target))!=name:raise Paused('已记录的工作台或熔炉被改变。')
        self.interact(target)
        expected='CraftingMenu' if name=='crafting_table' else 'FurnaceMenu'
        if self.b.state['menu']['type']!=expected:raise Paused('没有打开预期工作界面。')
    def craft(self,output,cells,width=3,produces=1):
        if width==3:self.station('crafting_table')
        else:self.b.close()
        s=self.b.read();grid=range(1,10 if width==3 else 5);slots=s['menu']['slots']
        if any(slots[i]['count'] for i in grid) or s['menu']['cursor']['count']:raise Paused('合成栏或鼠标已有物品，保留现场。')
        needed=Counter(cells.values());inv=inventory(s)
        if any(inv.get(name,0)<n for name,n in needed.items()):raise Paused('合成材料不足：'+output)
        before=inv.get(output,0)
        if s.get('bridge_version',0)>=3:
            self.b.request('craft_recipe',width=width,output='minecraft:'+output,produces=produces,
                           ingredients={str(1+row*width+col):'minecraft:'+item for (row,col),item in cells.items()},seconds=60)
            if inventory(self.b.read()).get(output,0)<before+produces:raise Paused('Kit 合成技能没有确认产物入包。')
            self.b.close();self.event('crafted',item=output,count=produces,engine='kit_native');return
        for (row,col),item in cells.items():
            s=self.b.read();start=10 if width==3 else 9
            source=next((v['slot'] for v in s['menu']['slots'][start:start+36] if v['item']=='minecraft:'+item and v['count']),None)
            if source is None:raise Paused('合成材料位置改变。')
            self.b.click(source);self.b.click(1+row*width+col,button=1)
            if self.b.read()['menu']['cursor']['count']:self.b.click(source)
        s=self.b.read()
        if s['menu']['slots'][0]['item']!='minecraft:'+output:raise Paused('合成输出不符，已保留材料。')
        self.b.click(0,kind='quick_move')
        if inventory(self.b.read()).get(output,0)<before+produces:raise Paused('未确认合成品进入背包。')
        self.b.close();self.event('crafted',item=output,count=produces)
    def planks(self,amount):
        inv=inventory(self.b.read());wood=next((n for n in LOGS if inv.get(n)),None)
        existing=next((n for n,v in inv.items() if n.endswith('_planks') and v>=amount),None)
        if existing:return existing
        if wood is None:raise Paused('需要更多原木。')
        plank=wood.removesuffix('_log')+'_planks'
        while self.count(plank)<amount:self.craft(plank,{(0,0):wood},width=2,produces=4)
        return plank
    def sticks(self,n):
        while self.count('stick')<n:
            plank=self.planks(2);self.craft('stick',{(0,0):plank,(1,0):plank},width=2,produces=4)
    def tool(self,name,material):
        if self.count(name):return
        self.sticks(2)
        cells={(0,0):material,(0,1):material,(0,2):material,(1,1):'stick',(2,1):'stick'} if name.endswith('pickaxe') else {(0,0):material,(0,1):material,(1,0):material,(1,1):'stick',(2,1):'stick'}
        self.craft(name,cells)
    def food(self):
        def amount(names):return sum(inventory(self.b.read()).get(n,0) for n in names)
        while amount(FOOD)+amount(RAW)<4:
            self.b.close();s=self.b.read();animals=[e for e in s.get('entities',[]) if e['type'] in ('minecraft:cow','minecraft:pig','minecraft:sheep','minecraft:chicken') and e.get('health',0)>0]
            if not animals:raise Paused('附近没有可获取的食物，已保存开局进度。')
            animal=min(animals,key=lambda e:distance(s['pos'],e['pos']));identity=animal['uuid'];self.b.select('stone_axe')
            for _ in range(15):
                s=self.b.read();e=next((v for v in s['entities'] if v['uuid']==identity and v.get('health',0)>0),None)
                if not e:break
                self.go_near(cell(e['pos']),reach=2.1);self.b.wait(1.1)
                e=next((v for v in self.b.read()['entities'] if v['uuid']==identity and v.get('health',0)>0),None)
                if e:self.b.request('attack_passive',entity_id=e['id'],expected_uuid=identity)
            else:raise Paused('未确认食物目标已结束，停止追逐。')
            self.collect(set(RAW)|{'leather','feather','white_wool','black_wool','gray_wool'})
        if amount(FOOD)>=4:return
        fuel=self.planks(6)
        for raw,cooked in RAW.items():
            n=self.count(raw)
            if not n:continue
            self.station('furnace');s=self.b.read()
            if any(s['menu']['slots'][i]['count'] for i in (0,1,2)):raise Paused('熔炉已有物品，保留原内容。')
            for item,target in ((raw,0),(fuel,1)):
                s=self.b.read();source=next(v['slot'] for v in s['menu']['slots'][3:39] if v['item']=='minecraft:'+item)
                self.b.click(source);self.b.click(target)
            before=self.count(cooked);limit=time.monotonic()+n*12+15
            while time.monotonic()<limit:
                self.check();s=self.b.read()
                if s['menu']['slots'][2]['item']=='minecraft:'+cooked:self.b.click(2,'quick_move')
                self.report_progress('烹饪食物',self.count(cooked)-before,n)
                if self.count(cooked)>=before+n:break
                self.b.wait(.8)
            else:raise Paused('烹饪未按期完成，保留熔炉内容。')
            if self.b.read()['menu']['slots'][1]['count']:self.b.click(1,'quick_move')
            self.b.close()
        if amount(FOOD)<4:raise Paused('还没有确认足够的可食用储备。')
    def eat_if_needed(self):
        s=self.b.read()
        if s['food']<16:
            food=next((n for n in FOOD if inventory(s).get(n)),None)
            if food:self.b.close();self.b.select(food);self.b.request('use_item',item='minecraft:'+food)
    def iron_equipment(self):
        _,door=shelter(self.camp)
        if 'open=false' in self.scan().row(door).get('state',''):self.interact(door,face='north')
        recipes={
          'iron_helmet':['III','I I'], 'iron_chestplate':['I I','III','III'],
          'iron_leggings':['III','I I','I I'], 'iron_boots':['I I','I I'],
          'iron_pickaxe':['III',' S ',' S '], 'iron_sword':[' I ',' I ',' S '],
          'shield':['PIP','PPP',' P ']}
        armor={'iron_helmet':5,'iron_chestplate':6,'iron_leggings':7,'iron_boots':8,'shield':45}
        self.b.close();s=self.b.read();inv=inventory(s)
        missing={name:pattern for name,pattern in recipes.items() if not inv.get(name) and not (name in armor and s['menu']['slots'][armor[name]]['item']=='minecraft:'+name)}
        needed=sum(''.join(pattern).count('I') for pattern in missing.values())
        deficit=max(0,needed-inv.get('iron_ingot',0))
        if deficit:
            self.planned('iron_ore','采集铁矿并核对入包',{'raw_iron':deficit})
            if self.count('raw_iron')<deficit:self.gather({'iron_ore','deepslate_iron_ore'},{'raw_iron'},deficit)
            self.planned('smelt_iron','熔炼铁锭',{'iron_ingots':deficit})
            fuel=self.planks(math.ceil(deficit/1.5)+1);self.station('furnace');s=self.b.read()
            if any(s['menu']['slots'][i]['count'] for i in (0,1,2)):raise Paused('熔炉已有内容，请先整理后续跑。')
            for item,target in (('raw_iron',0),(fuel,1)):
                source=next(v['slot'] for v in self.b.read()['menu']['slots'][3:39] if v['item']=='minecraft:'+item)
                self.b.click(source);self.b.click(target)
            before=self.count('iron_ingot');limit=time.monotonic()+self.b.read()['menu']['slots'][0]['count']*12+15
            while time.monotonic()<limit:
                self.check();s=self.b.read()
                if s['menu']['slots'][2]['item']=='minecraft:iron_ingot':self.b.click(2,'quick_move')
                self.report_progress('铁锭',self.count('iron_ingot')-before,deficit)
                if not self.b.read()['menu']['slots'][0]['count'] and self.count('iron_ingot')>=before+deficit:break
                self.b.wait(.8)
            else:raise Paused('铁锭尚未确认全部熔炼完成。')
            if self.b.read()['menu']['slots'][1]['count']:self.b.click(1,'quick_move')
            self.b.close()
        self.planned('iron_craft','制作并穿戴铁装备',{'items':list(missing)})
        sticks=sum(''.join(pattern).count('S') for pattern in missing.values());self.sticks(sticks)
        plank=self.planks(6) if 'shield' in missing else 'oak_planks'
        for name,pattern in missing.items():
            keys={'I':'iron_ingot','S':'stick','P':plank}
            self.craft(name,{(r,c):keys[ch] for r,line in enumerate(pattern) for c,ch in enumerate(line) if ch!=' '})
        self.b.close()
        for name,target in armor.items():
            s=self.b.read()
            if s['menu']['slots'][target]['item']=='minecraft:'+name:continue
            if s['menu']['slots'][target]['count']:raise Paused('装备槽已有其他装备，保留原物品。')
            source=next(v['slot'] for v in s['menu']['slots'][9:45] if v['item']=='minecraft:'+name)
            self.b.click(source);self.b.click(target)
            if self.b.read()['menu']['slots'][target]['item']!='minecraft:'+name:raise Paused('装备穿戴结果未确认。')
        self.go_near(door)
        if 'open=false' in self.scan().row(door).get('state',''):self.interact(door,face='south')
        w=self.scan();parents=w.paths(self.b.state['pos'])
        if tuple(self.camp) not in parents:raise Paused('回营地路径不可达。')
        self.walk(w.route(parents,tuple(self.camp)))
        if 'open=true' in self.scan().row(door).get('state',''):self.interact(door,face='north')
        self.b.select('iron_pickaxe');s=self.b.read();inv=inventory(s)
        checks={name:s['menu']['slots'][slot]['item']=='minecraft:'+name for name,slot in armor.items()}
        checks.update(iron_pickaxe=inv.get('iron_pickaxe',0)>0,iron_sword=inv.get('iron_sword',0)>0,alive=s['health']>=16)
        self.event('iron_milestones',**checks)
        if not all(checks.values()):raise Paused('铁装备验收未全部通过。')
    def run(self):
        self.event('start',world=self.b.world,origin=self.b.origin)
        try:
            w=self.scan()
            if self.camp is None:self.camp=w.camp(self.b.state['pos'])
            if self.camp is None:raise Paused('附近没有可用的 5×5 平地，请先换到开阔出生点。')
            self.save('running')
            self.decide('bootstrap_iron' if self.iron_target else 'bootstrap','开始本机生存开局任务',{'camp':self.camp,'scope':'observed nearby materials only'})
            inv=inventory(self.b.read())
            if not inv.get('wooden_pickaxe') and not inv.get('stone_pickaxe'):
                if sum(inv.get(n,0) for n in LOGS)<12:
                    self.planned('wood','采集开局木材',{'needed_logs':12});self.gather(LOGS,LOGS,12)
                self.planned('craft','制作工作台和木镐',{})
                plank=self.planks(12)
                if not self.count('crafting_table') and 'crafting_table' not in self.stations:self.craft('crafting_table',{(0,0):plank,(0,1):plank,(1,0):plank,(1,1):plank},2)
                self.tool('wooden_pickaxe',plank)
            needed=(0 if self.count('stone_pickaxe') else 3)+(0 if self.count('stone_axe') else 3)+(0 if self.count('furnace') or 'furnace' in self.stations else 8)
            if self.count('cobblestone')<needed:
                self.planned('stone','采集石料',{'required_cobblestone':needed});self.gather({'stone','cobblestone'},{'cobblestone'},needed)
            self.planned('tools','制作石工具和熔炉',{})
            self.tool('stone_pickaxe','cobblestone');self.tool('stone_axe','cobblestone')
            if not self.count('furnace') and 'furnace' not in self.stations:self.craft('furnace',{(r,c):'cobblestone' for r in range(3) for c in range(3) if (r,c)!=(1,1)})
            self.planned('food','获取并烹饪食物',{'goal':'four edible food items'});self.food();self.eat_if_needed()
            layout,door=shelter(self.camp);w=self.scan();missing=[p for p in layout if not w.earth(p)]
            if missing:
                self.planned('shelter_material','准备庇护所材料',{'dirt_blocks':len(missing)})
                if self.count('dirt')<len(missing):self.gather({'dirt','grass_block'},{'dirt'},len(missing))
            existing_door=self.scan().name(door)
            if existing_door.endswith('_door'):door_item=existing_door
            else:
                plank=self.planks(6);door_item=plank.removesuffix('_planks')+'_door'
                if not self.count(door_item):self.craft(door_item,{(r,c):plank for r in range(3) for c in range(2)},produces=3)
            self.planned('shelter','搭建带门和屋顶的庇护所',{'camp':self.camp,'blocks':len(missing)})
            for p in layout:self.eat_if_needed();self.place('dirt',p)
            self.place(door_item,door)
            self.b.close();self.go_near(door)
            if 'open=false' in self.scan().row(door).get('state',''):self.interact(door,face='south')
            w=self.scan();parents=w.paths(self.b.state['pos']);inside=tuple(self.camp)
            if inside not in parents:raise Paused('庇护所入口不可达。')
            self.walk(w.route(parents,inside))
            if 'open=true' in self.scan().row(door).get('state',''):self.interact(door,face='north')
            w=self.scan();inv=inventory(self.b.read())
            checks={'stone_pickaxe':inv.get('stone_pickaxe',0)>0,'stone_axe':inv.get('stone_axe',0)>0,
                    'food':sum(inv.get(n,0) for n in FOOD)>=1,'shelter':all(w.earth(p) for p in layout),
                    'closed_door':'open=false' in w.row(door).get('state',''),'alive':self.b.state['health']>=16,
                    'inside':distance(self.b.state['pos'],center(self.camp))<1}
            self.event('milestones',**checks)
            if not all(checks.values()):raise Paused('开局验收有未完成项目：'+str(checks))
            self.camp_completed=True;self.stage='木石工具、食物与庇护所已验收';self.save('running' if self.iron_target else 'done');print(self.stage,flush=True)
            if self.iron_target:
                self.iron_equipment();self.stage='铁装备已穿戴，已回到庇护所';self.save('done');print(self.stage,flush=True)
        except (DecisionError,OSError,ValueError,KeyboardInterrupt) as error:
            self.save('paused',str(error) or '用户停止');self.event('paused',reason=str(error));raise
        finally:self.b.stop_owned()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--world',required=True);parser.add_argument('--automation',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,default=PRIVATE/'survival'/'latest');parser.add_argument('--resume',type=Path)
    parser.add_argument('--minutes',type=int,default=30);parser.add_argument('--max-calls',type=int,default=24)
    parser.add_argument('--iron',action='store_true',help='Continue from the camp to iron equipment using nearby exposed ore')
    args=parser.parse_args()
    if not 1<=args.minutes<=60 or not 1<=args.max_calls<=60:raise Paused('时间和模型调用预算必须在 1–60 之间。')
    model=Jev()
    try:Runner(Bridge(args.automation,args.world),model,args.output,args.minutes,args.max_calls,args.resume,args.iron).run()
    finally:model.close()

if __name__=='__main__':
    try:main()
    except (DecisionError,OSError,ValueError,KeyboardInterrupt) as error:raise SystemExit('已暂停：'+str(error)) from None
