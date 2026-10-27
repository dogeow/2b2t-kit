"""Choose an intact roof anchor without aiming through its retained wall torch."""
from projection_completion import block_state

def options(rows,target):
 x,y,z=target;choices=[([x-1,y,z],'east'),([x+1,y,z],'west'),([x,y,z-1],'south'),([x,y,z+1],'north')]
 blocked=None
 kind,props=block_state(rows.get((x,y-1,z),{}).get('state','Block{minecraft:air}'))
 if kind in('minecraft:wall_torch','minecraft:redstone_wall_torch','minecraft:soul_wall_torch'):
  blocked={'east':'east','west':'west','north':'north','south':'south'}.get(props.get('facing'))
 return [(p,f)for p,f in choices if f!=blocked and rows.get(tuple(p),{}).get('state')=='Block{minecraft:dark_oak_planks}']
