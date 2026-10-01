"""Pure local projection geometry and caller-observed placement frontier.

Expected positions are already world coordinates: origin/rotation/mirror are
identity, never a second coordinate transformation. Static indices may persist
across world sessions. Actual observations never persist, omitted scan cells
remain unknown, and this module does not declare a build complete or send RPCs.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

from kit_runtime.journal import write_json

MAX_CELLS = 100000  # Current native full-model volume bound.
MAX_FILE_BYTES = 64 * 1024 * 1024
ROTATIONS = frozenset(('NONE','CLOCKWISE_90','CLOCKWISE_180','COUNTERCLOCKWISE_90'))
MIRRORS = frozenset(('NONE','LEFT_RIGHT','FRONT_BACK'))
DIRECTIONS = (('down', (0,-1,0)), ('up', (0,1,0)), ('north', (0,0,-1)),
              ('south', (0,0,1)), ('west', (-1,0,0)), ('east', (1,0,0)))


class CacheInvalidated(ValueError):
    """Source or geometry changed; the caller must obtain a new validated index."""


def _pos(value):
    if (not isinstance(value, (list,tuple)) or len(value) != 3
            or any(type(v) is not int or abs(v) > 30000000 for v in value)):
        raise ValueError('Expected a bounded integer XYZ position')
    return tuple(value)


def _text(value, limit=1024):
    if (not isinstance(value,str) or not value or len(value) > limit
            or any(c in value for c in '\n\r\t\0')):
        raise ValueError('Expected nonempty bounded exact text without hash delimiters')
    return value


def _state(value, *, expected=False):
    value=_text(value)
    if value=='AIR':block='minecraft:air'
    else:
        match=re.fullmatch(r'Block\{([a-z0-9_.-]+:[a-z0-9_./-]+)\}(?:\[([^\[\]]+)\])?',value)
        if not match:raise ValueError('Invalid exact Minecraft block-state text')
        block,properties=match.groups()
        names=set()
        for pair in properties.split(',') if properties is not None else ():
            parts=pair.split('=')
            if (len(parts)!=2 or not all(re.fullmatch(r'[a-z0-9_.:+/-]+',p) for p in parts)
                    or parts[0] in names):raise ValueError('Malformed or duplicate state property')
            names.add(parts[0])
    air=block in ('minecraft:air','minecraft:cave_air','minecraft:void_air')
    if expected and air:raise ValueError('Native complete expected table excludes air')
    return value,air


def _digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
                                    separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Scope:
    placement_key: str
    content_hash: str
    origin: tuple
    rotation: str
    mirror: str
    bounds: tuple | None
    def payload(self):
        return {'placement_key':self.placement_key,'content_hash':self.content_hash,
                'origin':list(self.origin),'rotation':self.rotation,'mirror':self.mirror,
                'bounds':None if self.bounds is None else {'min':list(self.bounds[0]),'max':list(self.bounds[1])}}
    @property
    def fingerprint(self):return _digest(self.payload())


def _scope(placement_key, content_hash, origin, rotation, mirror, bounds=None):
    if not isinstance(content_hash,str) or not re.fullmatch(r'[0-9a-f]{64}',content_hash):
        raise ValueError('Expected canonical SHA256 content_hash')
    rotation=_text(rotation,64);mirror=_text(mirror,64)
    if rotation not in ROTATIONS or mirror not in MIRRORS:raise ValueError('Unsupported rotation or mirror')
    box = None
    if bounds is not None:
        if not isinstance(bounds,dict) or set(bounds) != {'min','max'}:raise ValueError('Invalid model bounds')
        box = (_pos(bounds['min']),_pos(bounds['max']))
        if any(a>b for a,b in zip(*box)):raise ValueError('Inverted model bounds')
    return Scope(_text(placement_key,16384),content_hash,_pos(origin),
                 _text(rotation,64),_text(mirror,64),box)


@dataclass(frozen=True, slots=True)
class Cell:
    pos: tuple
    state: str
    item: str


def _cells(expected, total=None, max_cells=MAX_CELLS):
    if type(max_cells) is not int or not 1<=max_cells<=MAX_CELLS:raise ValueError('Invalid cell budget')
    if not isinstance(expected,(list,tuple)) or not 1<=len(expected)<=max_cells:
        raise ValueError('Expected one bounded complete non-air model table')
    if total is not None and (type(total) is not int or total!=len(expected)):
        raise ValueError('Full model total contradicts expected table')
    seen=set();result=[]
    for row in expected:
        if not isinstance(row,dict) or not {'pos','state','item'}<=row.keys():raise ValueError('Incomplete expected cell')
        pos=_pos(row['pos'])
        if pos in seen:raise ValueError('Duplicate expected coordinate')
        seen.add(pos)
        item=_text(row['item'],256)
        if not re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+',item):raise ValueError('Invalid item identifier')
        result.append(Cell(pos,_state(row['state'],expected=True)[0],item))
    return tuple(sorted(result,key=lambda c:(c.pos[1],c.pos[2],c.pos[0])))


def native_content_hash(expected):
    """Native model's lexicographically sorted lines, including every property."""
    cells=_cells(expected)
    return _cell_hash(cells)


def _cell_hash(cells):
    lines=sorted(f'{c.pos[0]},{c.pos[1]},{c.pos[2]}\t{c.state}\t{c.item}\n' for c in cells)
    digest=hashlib.sha256()
    for line in lines:digest.update(line.encode('utf-8'))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class XRun:
    item: str
    state: str
    y: int
    z: int
    min_x: int
    max_x: int
    def positions(self):return tuple((x,self.y,self.z) for x in range(self.min_x,self.max_x+1))


class SpatialIndex:
    def __init__(self,scope,cells,by_item,run_ids,neighbor_ids):
        self._scope=scope;self._cells=cells;self._invalid=False
        self._ids={c.pos:i for i,c in enumerate(cells)}
        self._by_item=MappingProxyType({item:tuple(cells[i].pos for i in ids) for item,ids in by_item.items()})
        self._item_ids={item:tuple(ids) for item,ids in by_item.items()}
        self._run_ids=tuple(tuple(v) for v in run_ids);self._neighbor_ids=tuple(tuple(v) for v in neighbor_ids)
        runs={item:[] for item in by_item};self._neighbors={};affected={}
        for first,last in self._run_ids:
            a,b=cells[first],cells[last]
            runs[a.item].append(XRun(a.item,a.state,a.pos[1],a.pos[2],a.pos[0],b.pos[0]))
        self._runs=MappingProxyType({item:tuple(values) for item,values in runs.items()})
        for cell in cells:
            adjacent=[];affected.setdefault(cell.pos,set()).add(cell.pos)
            for _,offset in DIRECTIONS:
                pos=tuple(a+b for a,b in zip(cell.pos,offset))
                adjacent.append(pos);affected.setdefault(pos,set()).add(cell.pos)
            self._neighbors[cell.pos]=tuple(adjacent)
        self._affected={pos:tuple(sorted(values)) for pos,values in affected.items()}
    def _valid(self):
        if self._invalid:raise CacheInvalidated('This index was invalidated; no cached coordinate may be reused')
    @property
    def scope(self):return self._scope
    def assert_scope(self,**geometry):
        try:wanted=_scope(**geometry)
        except (TypeError,ValueError) as error:
            self._invalid=True
            raise CacheInvalidated('Projection identity validation failed; previous index disabled') from error
        if wanted!=self.scope:
            self._invalid=True
            raise CacheInvalidated('Projection hash, selection, origin, direction or bounds changed')
        self._valid()
    @property
    def cells(self):self._valid();return self._cells
    @property
    def by_item(self):self._valid();return self._by_item
    @property
    def x_runs(self):self._valid();return self._runs
    def cell(self,pos):self._valid();return self._cells[self._ids[_pos(pos)]]
    def neighbors(self,pos):
        """Six world coordinates in DIRECTIONS order, including external support halo."""
        self._valid();return self._neighbors[_pos(pos)]
    def neighbor_cells(self,pos):
        self._valid();ids=self._neighbor_ids[self._ids[_pos(pos)]]
        return tuple(None if i<0 else self._cells[i] for i in ids)
    def save(self,path):
        self._valid()
        palette=sorted({(c.state,c.item) for c in self._cells});palette_ids={v:i for i,v in enumerate(palette)}
        payload={'schema':1,'scope':self.scope.payload(),'scope_fingerprint':self.scope.fingerprint,
                 'palette':palette,'cells':[[*c.pos,palette_ids[(c.state,c.item)]] for c in self._cells],
                 'by_item':self._item_ids,'runs':self._run_ids,'neighbors':self._neighbor_ids}
        payload['index_hash']=_digest(payload)
        if len(json.dumps(payload,ensure_ascii=False,indent=2).encode())+1>MAX_FILE_BYTES:
            raise ValueError('Persistent index exceeds bounded file size')
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);write_json(path,payload)


def build_index(expected, *, placement_key, content_hash, origin, rotation, mirror,
                bounds=None, total=None, max_cells=MAX_CELLS):
    scope=_scope(placement_key,content_hash,origin,rotation,mirror,bounds)
    cells=_cells(expected,total,max_cells)
    if _cell_hash(cells)!=scope.content_hash:raise CacheInvalidated('Claimed content_hash contradicts exact model cells')
    if scope.bounds and any(any(not a<=v<=b for a,v,b in zip(scope.bounds[0],c.pos,scope.bounds[1])) for c in cells):
        raise ValueError('Expected position outside declared model bounds')
    ids={c.pos:i for i,c in enumerate(cells)};items={};runs=[];neighbors=[]
    for i,c in enumerate(cells):
        items.setdefault(c.item,[]).append(i)
        if i and (c.item,c.state,c.pos[1:])==(cells[i-1].item,cells[i-1].state,cells[i-1].pos[1:]) and c.pos[0]==cells[i-1].pos[0]+1:
            runs[-1][1]=i
        else:runs.append([i,i])
        neighbors.append([ids.get(tuple(a+b for a,b in zip(c.pos,offset)),-1) for _,offset in DIRECTIONS])
    return SpatialIndex(scope,cells,items,runs,neighbors)


def index_from_model(model, *, origin, rotation, mirror, max_cells=MAX_CELLS):
    if (not isinstance(model,dict) or type(model.get('model_schema')) is not int or model['model_schema']!=1
            or model.get('loaded_chunks_verified') is not True
            or type(model.get('total')) is not int):raise ValueError('Require a complete validated native model receipt')
    return build_index(model['expected'],placement_key=model['placement_key'],content_hash=model['content_hash'],
                       origin=origin,rotation=rotation,mirror=mirror,bounds=model.get('bounds'),total=model['total'],max_cells=max_cells)


def load_index(path, *, placement_key, content_hash, origin, rotation, mirror, bounds=None):
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>MAX_FILE_BYTES:raise ValueError('Unsafe or oversized cache file')
    with path.open('rb') as stream:encoded=stream.read(MAX_FILE_BYTES+1)
    if len(encoded)>MAX_FILE_BYTES:raise ValueError('Cache file grew beyond its bound')
    data=json.loads(encoded)
    if not isinstance(data,dict) or type(data.get('schema')) is not int or data['schema']!=1:raise ValueError('Unsupported cache schema')
    claimed=data.pop('index_hash',None)
    if claimed!=_digest(data):raise CacheInvalidated('Persistent index checksum changed')
    scope=_scope(**data['scope']);wanted=_scope(placement_key,content_hash,origin,rotation,mirror,bounds)
    if scope!=wanted or data.get('scope_fingerprint')!=scope.fingerprint:raise CacheInvalidated('Cached source or geometry changed')
    packed=data.get('cells');palette=data.get('palette')
    if not isinstance(packed,list) or not 1<=len(packed)<=MAX_CELLS or not isinstance(palette,list) or not 1<=len(palette)<=len(packed):
        raise ValueError('Invalid bounded cell/palette table')
    expected=[]
    for row in packed:
        if not isinstance(row,list) or len(row)!=4 or type(row[3]) is not int or not 0<=row[3]<len(palette):raise ValueError('Invalid packed cell')
        entry=palette[row[3]]
        if not isinstance(entry,list) or len(entry)!=2:raise ValueError('Invalid palette entry')
        expected.append({'pos':row[:3],'state':entry[0],'item':entry[1]})
    cells=_cells(expected)
    if [c.pos for c in cells]!=[tuple(v[:3]) for v in packed] or _cell_hash(cells)!=scope.content_hash:
        raise CacheInvalidated('Cached cells contradict pinned model/order')
    if scope.bounds and any(any(not a<=v<=b for a,v,b in zip(scope.bounds[0],c.pos,scope.bounds[1])) for c in cells):raise ValueError('Cached cell outside bounds')
    ids={c.pos:i for i,c in enumerate(cells)};covered=set();by_item=data.get('by_item')
    if not isinstance(by_item,dict):raise ValueError('Invalid item index')
    for item,values in by_item.items():
        if not isinstance(values,list) or not values:raise ValueError('Invalid item positions')
        last=-1
        for i in values:
            if type(i) is not int or not 0<=i<len(cells) or i<=last or i in covered or cells[i].item!=item:raise ValueError('Item index differs from source cells')
            covered.add(i);last=i
    if len(covered)!=len(cells):raise ValueError('Incomplete item index')
    runs=data.get('runs');last=-1
    if not isinstance(runs,list) or not 1<=len(runs)<=len(cells):raise ValueError('Invalid run index')
    for run in runs:
        if not isinstance(run,list) or len(run)!=2 or any(type(v) is not int for v in run):raise ValueError('Invalid run endpoints')
        first,end=run
        if first!=last+1 or not first<=end<len(cells):raise ValueError('Run coverage overlaps or is incomplete')
        a=cells[first]
        if first:
            previous=cells[first-1]
            if (a.item,a.state,a.pos[1:])==(previous.item,previous.state,previous.pos[1:]) and a.pos[0]==previous.pos[0]+1:
                raise ValueError('Run index is not maximal')
        for i in range(first,end+1):
            c=cells[i]
            if (c.item,c.state,c.pos[1:],c.pos[0]-a.pos[0])!=(a.item,a.state,a.pos[1:],i-first):raise ValueError('Run crosses a gap or exact-state boundary')
        last=end
    if last!=len(cells)-1:raise ValueError('Incomplete run index')
    neighbors=data.get('neighbors')
    if not isinstance(neighbors,list) or len(neighbors)!=len(cells):raise ValueError('Invalid neighbor index')
    for cell,values in zip(cells,neighbors):
        if not isinstance(values,list) or len(values)!=6 or any(type(i) is not int for i in values):raise ValueError('Invalid six-neighbor row')
        if values!=[ids.get(tuple(a+b for a,b in zip(cell.pos,offset)),-1) for _,offset in DIRECTIONS]:raise ValueError('Neighbor index differs from world geometry')
    return SpatialIndex(scope,cells,by_item,runs,neighbors)


@dataclass(frozen=True, slots=True)
class Actual:
    state: str
    replaceable: bool
    support: bool


@dataclass(frozen=True, slots=True)
class FrontierDelta:
    changed: frozenset
    affected: frozenset
    added: frozenset
    removed: frozenset


class SupportedFrontier:
    """Observed replaceable targets with caller-proved real neighbor support.

The caller must supply complete current-world scan/ACK evidence; no automatic
inference from omitted air, non-air state, planned cells or predicted inventory.
An exact observed match is retained as observation, not a goal-completion claim.
"""
    def __init__(self,index,world_session):
        index._valid();self._index=index;self._world=None;self.bind_world(world_session)
    @property
    def index(self):return self._index
    @property
    def world_session(self):return self._world
    def bind_world(self,world_session):
        self.index._valid();world_session=_text(world_session,256)
        if world_session!=self._world:
            self._world=world_session;self._actual={};self._matched=set();self._frontier=set()
            self._by_item={item:set() for item in self.index.by_item};self._last_at=-1
    @property
    def observed_matches(self):self.index._valid();return frozenset(self._matched)
    def positions(self,item=None):
        self.index._valid();return frozenset(self._frontier if item is None else self._by_item.get(item,()))
    def actual(self,pos):self.index._valid();return self._actual.get(_pos(pos))
    def observe(self,world_session,updates,*,evidence,observed_at):
        self.index._valid()
        if world_session!=self._world:raise CacheInvalidated('Stale world observation; bind_world is explicit')
        if evidence not in ('scan','server_ack') or type(observed_at) is not int or observed_at<=0 or observed_at<=self._last_at:
            raise ValueError('Require new ordered caller scan/server ACK evidence')
        if not isinstance(updates,(list,tuple)) or len(updates)>MAX_CELLS:raise ValueError('Observation batch exceeds its bound')
        parsed={}
        for row in updates:
            if not isinstance(row,dict) or not {'pos','state','replaceable','support'}<=row.keys():raise ValueError('Incomplete actual observation')
            pos=_pos(row['pos'])
            if pos in parsed or pos not in self.index._affected:raise ValueError('Duplicate or outside-halo actual observation')
            if type(row['replaceable']) is not bool or type(row['support']) is not bool or row['replaceable'] and row['support']:
                raise ValueError('Support and replaceability must be explicit and consistent')
            state,air=_state(row['state'])
            if air and (row['support'] or not row['replaceable']):raise ValueError('Air observation cannot supply solid support')
            parsed[pos]=Actual(state,row['replaceable'],row['support'])
        changed={p for p,value in parsed.items() if self._actual.get(p)!=value};affected=set()
        for pos in changed:affected.update(self.index._affected[pos])
        self._actual.update(parsed);added=set();removed=set()
        for pos in affected:
            cell=self.index._cells[self.index._ids[pos]];actual=self._actual.get(pos)
            matched=actual is not None and actual.state==cell.state
            if matched:self._matched.add(pos)
            else:self._matched.discard(pos)
            supported=actual is not None and actual.replaceable and not matched and any(
                self._actual.get(neighbor) is not None and self._actual[neighbor].support
                for neighbor in self.index._neighbors[pos])
            if supported:
                if pos not in self._frontier:added.add(pos)
                self._frontier.add(pos);self._by_item[cell.item].add(pos)
            else:
                if pos in self._frontier:removed.add(pos)
                self._frontier.discard(pos);self._by_item[cell.item].discard(pos)
        self._last_at=observed_at
        return FrontierDelta(frozenset(changed),frozenset(affected),frozenset(added),frozenset(removed))
