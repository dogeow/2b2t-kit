"""Select ready candidates, preserving the short native keeper quote window."""
def choose_ready(ready,last_used,preferred=None):
 if not ready:return None
 return next((slot for slot in ready if slot['id']==preferred),None)or min(ready,key=lambda slot:last_used.get(slot['id'],0))

def keeper_refresh_key(slot_id,enchantment,previous):
 return f"{slot_id}:{enchantment}:{(previous or{}).get('native_sequence',0)}"
