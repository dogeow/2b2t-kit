"""Conservative geometry check for dry hover work above observed ground melee mobs.

Does not change guard policy, clear threats or claim a kill. Ranged and unknown
mobs remain blockers. Every actual action still needs the native PvE/health gate.
"""
import math

def separated(threats, minimum_work_poses):
    if not isinstance(threats,list) or not isinstance(minimum_work_poses,list) or not minimum_work_poses:
        return False
    try:
        if any(not isinstance(p,list) or len(p)!=3 or any(type(v)not in(int,float) or not math.isfinite(v) for v in p) for p in minimum_work_poses):return False
        for mob in threats:
            if mob.get('type') not in {'minecraft:creeper','minecraft:spider','minecraft:zombie','minecraft:husk','minecraft:slime'} or mob.get('alive') is not True or mob.get('hostile') is not True:return False
            point=mob['pos'];top=mob['bounds']['max'][1]
            if not isinstance(point,list) or len(point)!=3 or any(type(v)not in(int,float) or not math.isfinite(v) for v in point+[top]):return False
            # Native blast threat policy includes powered creepers out to 12m;
            # retain 2m extra blast distance. Ordinary melee work also admits distant mobs;
            # close melee mobs still require 8m clear air below working feet.
            if mob['type']=='minecraft:creeper':
                if any(math.dist(p,point)<14 for p in minimum_work_poses):return False
            elif any(p[1]-top<8 and math.dist(p,point)<14 for p in minimum_work_poses):return False
        return True
    except (KeyError,TypeError,ValueError,IndexError):
        return False
