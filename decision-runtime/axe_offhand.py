"""Temporarily store an offhand shield for vanilla axe use, then restore it.

Vanilla AxeItem passes main-hand use while a blocking offhand item is present
and secondary use is inactive. Inventory actions remain exact normal Kit clicks.
"""
from copy import deepcopy
from pathlib import Path
from kit_runtime.inventory import InventorySession
from kit_runtime.storage import move_amount
from kit_runtime.journal import write_json
from material_cleanup import register,complete


def _identity(row):return {k:v for k,v in row.items()if k!='slot'}


class AxeOffhand:
 def __init__(self,client,out):
  self.client=client;self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
  self.book={'pending':None,'stored':False,'restored':False};self.session=InventorySession(client)
  self.key='axe-offhand:'+str(self.out.resolve())
 def save(self):write_json(self.out/'progress.json',self.book)
 def state(self):
  s=self.client.status();m=s.get('menu',{})
  if (m.get('type')!='InventoryMenu'or m.get('id')!=0 or len(m.get('slots',[]))!=46
      or m.get('cursor',{}).get('count')or s.get('manual_movement')or s.get('screen')):
   raise RuntimeError('Exact idle inventory/cursor unavailable for shield storage')
  return s
 def park(self):
  s=self.state();off=s['menu']['slots'][45]
  if not off['count']:
   self.book.update(restored=True);self.save();return self
  if (off['item']!='minecraft:shield'or off['count']!=1 or s.get('health')!=20
      or s.get('guard_busy')or not s.get('guard_armed')or not s.get('guard_pve_only')):
   raise RuntimeError('Healthy idle guard and an actual shield are required before axe use')
  dest=next((r for r in s['menu']['slots'][9:36]if not r['count']),None)
  if dest is None:raise RuntimeError('Reserve one real main-backpack slot for shield restoration')
  self.book.update(world_session=s['world_session'],shield=deepcopy(off),storage_slot=dest['slot'],pending='store_offhand');self.save()
  move_amount(self.session,s,off,dest,1)
  q=self.session._wait(self.state(),0,lambda m:not m['slots'][45]['count']
       and _identity(m['slots'][dest['slot']])==_identity(off),'axe_shield_stored',confirmations=2,fresh=True)
  rows=q['menu']['slots']
  if rows[45]['count']or _identity(rows[dest['slot']])!=_identity(off):raise RuntimeError('Shield storage unconfirmed; no axe use')
  self.book.update(pending=None,stored=True);self.save();register(self.client,self.key,self.restore);return self
 def restore(self):
  if self.book['pending']:raise RuntimeError('Unknown shield click retained; no replay')
  if not self.book['stored']:return
  s=self.state();rows=s['menu']['slots'];source=rows[self.book['storage_slot']];off=rows[45]
  if s['world_session']!=self.book['world_session']or off['count']or _identity(source)!=_identity(self.book['shield']):
   raise RuntimeError('Stored shield/offhand changed; preserve player inventory')
  self.book['pending']='restore_offhand';self.save();move_amount(self.session,s,source,off,1)
  q=self.session._wait(self.state(),0,lambda m:_identity(m['slots'][45])==_identity(self.book['shield'])
       and not m['slots'][self.book['storage_slot']]['count'],'axe_shield_restored',confirmations=2,fresh=True)
  rows=q['menu']['slots']
  if _identity(rows[45])!=_identity(self.book['shield'])or rows[self.book['storage_slot']]['count']:
   raise RuntimeError('Shield restore unconfirmed; no repeat')
  self.book.update(pending=None,stored=False,restored=True);self.save();complete(self.client,self.key)
