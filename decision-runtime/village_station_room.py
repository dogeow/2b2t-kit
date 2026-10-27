"""Derive a sealed south stall's relocation coordinates from its own layout row."""
def _south_room(slot, allowed):
    """Support only an original workstation two blocks ahead of its south bed."""
    def point(name):
        value=slot.get(name)
        if not isinstance(value,list)or len(value)!=3 or any(type(n)is not int for n in value):
            raise ValueError('Exact integer stall coordinates required')
        return list(value)
    foot,head,work=point('bed_foot'),point('bed_head'),point('work_block')
    x,y,z=foot
    if(head!=[x,y,z+1]or work!=[x,y,z-2]
            or not isinstance(slot.get('occupant_uuid'),str)or not slot['occupant_uuid']):
        raise ValueError('Original south workstation and its own enclosed resident required')
    item=allowed.get(slot.get('profession'))
    if item is None:raise ValueError('This profession is not admitted for the requested station operation')
    return dict(old=work,new=[x,y,z-1],public_roof=[x,y+3,z-3],private_roof=[x,y+3,z],
                scan_min=[x-1,y-1,z-2],scan_max=[x+1,y+3,z+2],item='minecraft:'+item,
                occupant_uuid=slot['occupant_uuid'])


def south_relocation(slot):
    """Admit recovery only for the explicitly supported non-container stations."""
    if slot.get('closer_station_experiment') is True:
        raise ValueError('This workstation was already relocated; inspect its current layout')
    return _south_room(slot, {'shepherd':'loom','mason':'stonecutter','leatherworker':'cauldron'})


def south_installation(slot):
    """Derive an additional inner station; the original container stays intact."""
    if slot.get('original_container_preserved') is True:
        raise ValueError('An inner station already exists; do not install another')
    room = _south_room(slot, {'butcher':'smoker','fisherman':'barrel'})
    room['preserve_original_workstation'] = True
    return room
