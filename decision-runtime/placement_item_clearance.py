"""Permit only dropped items wholly below a planned closed top trapdoor collision plane."""
import math
from projection_completion import block_state

def safely_below_top_trapdoor(entity,pos,item,expected):
 try:
  kind,props=block_state(expected);box=entity['bounds']
  return(entity.get('type')=='minecraft:item'and kind==item and kind.endswith('_trapdoor')
   and props.get('half')=='top'and props.get('open')=='false'and props.get('waterlogged')=='false'
   and all(len(box[k])==3 and all(type(v)in(int,float)and math.isfinite(v)for v in box[k])for k in('min','max'))
   and all(box['min'][i]<box['max'][i]for i in range(3))and box['max'][1]<=pos[1]+.8)
 except(KeyError,TypeError,ValueError):return False
