"""Observed opportunities and a small, cached Jev decision. No ChatGPT calls."""
from dataclasses import dataclass,field
import hashlib,json,time
from decisions import choose,DecisionError

@dataclass
class Opportunity:
    key:str
    description:str
    parameters:dict=field(default_factory=dict)

class Coordinator:
    def __init__(self,model,event,max_calls=24):
        self.model=model;self.event=event;self.max_calls=max_calls;self.calls=0;self.cache={}
    def select(self,options,scene):
        if not options:raise DecisionError('没有可执行的已观察任务，需要重新扫描。')
        if len(options)==1:
            self.event('local_choice',choice=options[0].key,reason='only one validated opportunity')
            return options[0]
        options=options[:5];criteria={o.key:o.description for o in options};criteria['wait']='Wait: none of these currently offered tasks is suitable for the survival goal.'
        signature=hashlib.sha256(json.dumps({'options':criteria,'scene':scene},sort_keys=True).encode()).hexdigest()
        if signature in self.cache:
            key=self.cache[signature];self.event('cached_choice',choice=key)
            return next(o for o in options if o.key==key)
        if self.calls>=self.max_calls:raise DecisionError('Jev 本轮决策预算已用完；保存现场，不调用 ChatGPT 接管。')
        answer=choose(self.model,'Survive and progress toward iron equipment in this ordinary Minecraft world. Select the next useful task from the feasible options, using the current observations.',criteria,scene)
        self.calls+=1
        self.event('jev_choice',options=criteria,scene=scene,signature=signature,**answer)
        if answer['choice']=='wait' or answer['confidence']<.75 or answer['elapsed_ms']>6000:raise DecisionError('Jev 对当前分支不确定，保存现场供复查。')
        self.cache[signature]=answer['choice']
        return next(o for o in options if o.key==answer['choice'])

def day_phase(ticks):
    t=ticks%24000
    return 'morning' if t<6000 else 'afternoon' if t<10000 else 'sunset soon' if t<12500 else 'night' if t<23000 else 'dawn'

def scene_summary(snapshot,inventory,camp):
    return {'day_phase':day_phase(snapshot.get('day_time',0)),
            'health':'healthy' if snapshot['health']>=18 else 'hurt',
            'food_bar':'full' if snapshot['food']>=18 else 'needs food',
            'equipment':'iron' if inventory.get('iron_pickaxe') else 'stone' if inventory.get('stone_pickaxe') else 'wood' if inventory.get('wooden_pickaxe') else 'empty handed',
            'camp':'established' if camp else 'not established',
            'food_reserve':'available' if any(inventory.get(n,0)>0 for n in ('cooked_beef','cooked_porkchop','cooked_mutton','cooked_chicken','bread','apple')) else 'none',
            'hostile_visible':any(e.get('hostile') and e.get('visible') for e in snapshot.get('entities',[]))}
