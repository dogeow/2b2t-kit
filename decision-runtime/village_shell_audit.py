"""Physical cell shells, independently of resident positions or workstation trade history."""
from projection_completion import block_state

def audit_cell(rows,slot):
 name=slot['id'];x,y,z=slot['work_block'];floor=slot.get('interior_floor_y',y);inward=1 if name[1]=='S'else-1
 if floor!=y:return {'slot':name,'verified':False,'issues':[{'reason':'original_floor_requires_specific_geometry'}]}
 expected=set();interior=[z+n*inward for n in(1,2,3)]
 for zz in interior:
  expected.update([(x,floor-1,zz),(x,floor+3,zz)])
  for yy in range(floor,floor+3):expected.update([(x-1,yy,zz),(x+1,yy,zz)])
 expected.update((x,yy,z+4*inward)for yy in range(floor,floor+3));expected.update([(x,floor-1,z),(x,floor+2,z)])
 issues=[]
 for pos in sorted(expected):
  row=rows.get(pos)
  if row is None:issues.append({'pos':list(pos),'reason':'missing_shell_block','state':'Block{minecraft:air}'})
  elif row.get('solid')is not True or row.get('fluid')is not False or row.get('block_entity')is not False:issues.append({'pos':list(pos),'reason':'not_a_full_dry_cube','state':row.get('state')})
 cap=(x,floor+1,z);row=rows.get(cap,{})
 try:kind,props=block_state(row.get('state','Block{minecraft:air}'))
 except(ValueError,TypeError):kind,props='',{}
 closed=(row.get('solid')is True and row.get('fluid')is False and row.get('block_entity')is False
         or kind.endswith('_slab')and props.get('type')=='bottom'and props.get('waterlogged')=='false'
         or kind.endswith('_trapdoor')and props.get('half')=='top'and props.get('open')=='false'and props.get('waterlogged')=='false')
 if not closed:issues.append({'pos':list(cap),'reason':'closed_adult_trade_cap_unverified','state':row.get('state','Block{minecraft:air}')})
 return {'slot':name,'verified':not issues,'issues':issues,'full_cube_shell_cells_checked':len(expected),'trade_cap_checked':list(cap),'resident_position_alone_not_used':True,'scope':'full_cube_floor_sides_rear_roof_and_closed_adult_trade_cap'}
