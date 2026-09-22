"""Vanilla recipe plans read from the installed client JAR, never guessed by a model."""
from dataclasses import dataclass
from collections import defaultdict,Counter
from pathlib import Path
import json,zipfile
@dataclass(frozen=True)
class Recipe:
    id:str
    output:str
    count:int
    width:int
    cells:tuple
    kind:str
class RecipeCatalog:
    def __init__(self,jar):
        self.jar=Path(jar);self.tags={};self.recipes=defaultdict(list)
        with zipfile.ZipFile(self.jar) as z:
            for name in z.namelist():
                if name.startswith('data/minecraft/tags/item/') and name.endswith('.json'):
                    self.tags['minecraft:'+name.removeprefix('data/minecraft/tags/item/').removesuffix('.json')]=json.loads(z.read(name)).get('values',[])
            for name in z.namelist():
                if not name.startswith('data/minecraft/recipe/') or not name.endswith('.json'):continue
                d=json.loads(z.read(name));kind=d.get('type','');result=d.get('result',{})
                if kind not in ('minecraft:crafting_shaped','minecraft:crafting_shapeless') or not isinstance(result,dict):continue
                if kind.endswith('shaped'):
                    pattern=d['pattern'];width=2 if max(len(pattern),max(map(len,pattern)))<=2 else 3
                    cells=tuple((y*width+x+1,tuple(self.expand(d['key'][char]))) for y,row in enumerate(pattern) for x,char in enumerate(row) if char!=' ')
                else:
                    width=2 if len(d['ingredients'])<=4 else 3
                    cells=tuple((i+1,tuple(self.expand(v))) for i,v in enumerate(d['ingredients']))
                if cells and all(opts for _,opts in cells):
                    r=Recipe(name.removeprefix('data/minecraft/recipe/').removesuffix('.json'),result['id'],result.get('count',1),width,cells,kind)
                    self.recipes[r.output].append(r)
    def expand(self,value,seen=frozenset()):
        if isinstance(value,list):return sorted(set(x for v in value for x in self.expand(v,seen)))
        if isinstance(value,dict):value=value.get('id') or value.get('item') or '#'+value['tag']
        if value.startswith('#'):
            tag=value[1:]
            if tag in seen:return []
            return self.expand(self.tags.get(tag,[]),seen|{tag})
        return [value]
    def candidates(self,output,inventory,menu_width=None):
        choices=[]
        preference=['minecraft:oak_planks','minecraft:oak_slab','minecraft:coal','minecraft:oak_log','minecraft:quartz_block','minecraft:cobblestone','minecraft:white_wool','minecraft:stone','minecraft:leather']
        for r in self.recipes.get(output,[]):
            if menu_width and r.width>menu_width:continue
            left=Counter(inventory);groups=defaultdict(list);missing=Counter()
            for slot,opts in sorted(r.cells,key=lambda c:len(c[1])):
                opts=tuple(i for i in opts if i!=output)
                if not opts:missing['unsupported_same_item_conversion']+=1;continue
                item=min(opts,key=lambda i:(left[i]<1,preference.index(i) if i in preference else len(preference),-left[i],i))
                if left[item]>0:left[item]-=1
                else:missing[item]+=1
                col=(slot-1)%r.width;row=(slot-1)//r.width;actual=row*(menu_width or r.width)+col+1;groups[item].append(actual)
            choices.append((sum(missing.values()),len(groups),r.id,r,dict(groups),dict(missing)))
        if not choices:raise ValueError('No ordinary crafting recipe for '+output)
        return [{'recipe_id':r.id,'output':r.output,'produces':r.count,'width':menu_width or r.width,'ingredients':groups,'missing_for_one':missing}
                for _,_,_,r,groups,missing in sorted(choices,key=lambda row:row[:3])]
    def choose(self,output,inventory,menu_width=None):
        return self.candidates(output,inventory,menu_width)[0]
