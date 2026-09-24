"""Bounded high-air relay for material work beyond one Kit worksite scope."""

import math


def next_relay(start, destination, maximum_scope=400, leg=280, cruise_y=150):
    if not all(math.isfinite(v) for v in (*start, *destination)):
        raise ValueError('Finite start and destination are required')
    distance=math.hypot(destination[0]-start[0],destination[2]-start[2])
    if distance<=maximum_scope:
        return None
    if not 0<leg<maximum_scope:
        raise ValueError('Relay leg must be shorter than worksite scope')
    portion=leg/distance
    return [start[0]+portion*(destination[0]-start[0]),
            max(cruise_y,start[1],destination[1]),
            start[2]+portion*(destination[2]-start[2])]
