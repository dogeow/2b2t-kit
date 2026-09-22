"""Save/replace the TypeSafe credential without displaying it or placing it in argv/source files."""
import getpass,os
from pathlib import Path
root=Path.home()/'Library/Application Support/MinecraftDecisions';root.mkdir(parents=True,exist_ok=True);root.chmod(0o700)
key=getpass.getpass('TypeSafe API key (hidden): ').strip()
if not key.startswith('apikey_') or len(key)>256:raise SystemExit('Invalid TypeSafe key format')
temp=root/'typesafe.key.new'
fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
try:os.write(fd,key.encode())
finally:os.close(fd)
temp.replace(root/'typesafe.key');print('Saved. Key value remains hidden.')
