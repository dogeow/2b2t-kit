"""Briefly re-observe transient client stalls without replaying any game operation."""
import json,time
from pathlib import Path


def read_fresh(root,max_age_ms=3000,wait_seconds=6):
    deadline=time.monotonic()+wait_seconds
    while True:
        try:
            state=json.loads((Path(root)/'status.json').read_text())
            age=time.time()*1000-state['time']
            if -1000<=age<=max_age_ms:return state
        except (OSError,ValueError,KeyError,TypeError):pass
        if time.monotonic()>=deadline:raise RuntimeError('Game state is stale after bounded observation retry')
        time.sleep(.15)
