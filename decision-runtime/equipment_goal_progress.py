"""Display recorded equipment milestones; never completes a goal or sends input."""
from anvil_enchant_preview import enchantments


def summary(project,acceptance):
    targets=acceptance.get('targets');done=project.get('completed_equipment',[])
    if not isinstance(targets,list)or not 1<=len(targets)<=128 or not isinstance(done,list):
        raise ValueError('Bounded equipment targets and recorded milestones required')
    required={v['key']:v for v in targets}
    if len(required)!=len(targets):raise ValueError('Duplicate target keys')
    keys=[]
    for row in done:
        target=required.get(row.get('key'));item=row.get('item')or{}
        if (not target or item.get('count')!=1 or item.get('item')!=target.get('item')
                or enchantments(item)!=target.get('enchantments')or not row.get('proof')):
            raise ValueError('Equipment milestone does not match its maximum-enchantment target')
        keys.append(row['key'])
    if len(set(keys))!=len(keys):raise ValueError('Duplicate completed equipment')
    phase='准备装备与核验费用'
    if project.get('pending_chestplate_book',{}).get('applied')is False:phase='胸甲附魔书已合成，补充经验'
    if len(keys)==len(targets):phase='逐件进行最终实机核验'
    return {'done':len(keys),'total':len(targets),'phase':phase}
