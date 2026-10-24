"""Recognize a grounded collection stance, including vanilla bed-top steps.

This is a workflow/collection precondition, not a replacement for owner, player
health, resident-health, enclosure or native collision checks.
"""
import math


def collecting_inside(state,slot):
    try:
        pos=state['pos'];work=slot['work_block'];bed=slot['bed_foot']
        if (not isinstance(pos,list)or len(pos)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in pos)
                or state.get('flight')is not False or state.get('on_ground')is not True):return False
        if bed[2]==work[2]:return False
        inward=1 if bed[2]>work[2]else -1
        edge=work[2]+(1 if inward>0 else 0);distance=inward*(pos[2]-edge)
        return (abs(pos[0]-(work[0]+.5))<=.4 and work[1]-.05<=pos[1]<=work[1]+.625
                and .1<=distance<=1.2)
    except(KeyError,TypeError,IndexError):return False
