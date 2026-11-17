"""Locate exactly one installed Kit host by mod metadata, never a guessed filename."""
import json,zipfile
from pathlib import Path

def find(mods,version):
 def numeric(v):
  parts=v.split('.')
  if not parts or any(not x.isdigit() for x in parts):raise ValueError('Expected numeric Kit version')
  return tuple(int(x) for x in parts)
 wanted=numeric(version);found=[]
 for path in Path(mods).glob('*.jar'):
  try:
   with zipfile.ZipFile(path) as z:
    if 'fabric.mod.json' not in z.namelist():continue
    m=json.loads(z.read('fabric.mod.json'))
   if m.get('id')=='twob2tkit':found.append((path,numeric(m['version'])))
  except (OSError,ValueError,KeyError,zipfile.BadZipFile):
   if path.name.startswith('twob2tkit'):raise ValueError('Unreadable Kit host')
 if len(found)!=1 or found[0][1]!=wanted:raise ValueError('Kit host missing, duplicated, or version mismatch')
 return found[0][0]
