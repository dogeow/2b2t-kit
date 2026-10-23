"""Create one exact lectern projection using the previously verified Litematic format."""
from pathlib import Path
import gzip,hashlib,json,struct,time

def _text(value):
    raw=value.encode();return struct.pack('>H',len(raw))+raw

def _payload(kind,value):
    if kind==3:return struct.pack('>i',value)
    if kind==4:return struct.pack('>q',value)
    if kind==8:return _text(value)
    if kind==9:return bytes([value[0]])+struct.pack('>i',len(value[1]))+b''.join(_payload(value[0],v)for v in value[1])
    if kind==10:return b''.join(bytes([k])+_text(name)+_payload(k,v)for name,(k,v)in value.items())+b'\0'
    if kind==12:return struct.pack('>i',len(value))+b''.join(struct.pack('>q',v)for v in value)
    raise ValueError('Unsupported exact workstation NBT tag')

def create(directory,origin,facing,data_version,*,file,name):
    if (not isinstance(origin,list)or len(origin)!=3 or any(type(v)is not int for v in origin)
            or facing not in ('north','south','east','west')or type(data_version)is not int or data_version<=0):raise ValueError('Exact integer workpoint, current data version and facing required')
    if Path(file).is_absolute()or '..'in Path(file).parts or not file.endswith('.litematic'):raise ValueError('Relative schematic path required')
    out=Path(directory);out.mkdir(exist_ok=False);xyz=lambda values:(10,{k:(3,v)for k,v in zip('xyz',values)})
    props={k:(8,v)for k,v in {'facing':facing,'has_book':'false','powered':'false'}.items()}
    region={'Position':xyz([0,0,0]),'Size':xyz([1,1,1]),'BlockStatePalette':(9,(10,[{'Name':(8,'minecraft:air')},{'Name':(8,'minecraft:lectern'),'Properties':(10,props)}])),'BlockStates':(12,[1])}
    region.update({k:(9,(10,[]))for k in ['TileEntities','Entities','PendingBlockTicks','PendingFluidTicks']})
    now=int(time.time()*1000);metadata={'Name':(8,name),'Author':(8,'Kit'),'Description':(8,'Independent workpoint; quarantined old targets excluded'),'RegionCount':(3,1),'TimeCreated':(4,now),'TimeModified':(4,now),'TotalBlocks':(3,1),'TotalVolume':(3,1),'EnclosingSize':xyz([1,1,1])}
    root={'Version':(3,6),'SubVersion':(3,1),'MinecraftDataVersion':(3,data_version),'Metadata':(10,metadata),'Regions':(10,{'Counters':(10,region)})}
    raw=b'\x0a\x00\x00'+_payload(10,root)
    from material_jobs.bobby_snow_cache import _NBTReader
    parsed=_NBTReader(raw).root();assert parsed['Regions']['Counters']['BlockStates']==[1]
    path=out/'workstation.litematic';path.write_bytes(gzip.compress(raw,mtime=0))
    manifest={'schema':1,'source':str(path.resolve()),'file':file,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'origin':origin,'regions':['Counters'],'name':name,'expected':[{'pos':origin,'item':'minecraft:lectern','state':'Block{minecraft:lectern}[facing='+facing+',has_book=false,powered=false]'}]}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');return manifest
