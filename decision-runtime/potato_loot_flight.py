"""Caller-injected registered crop pickup flight; movement receipts never prove pickup."""
import math

from potato_farm import FarmWait, POTATO, crop_descriptor, plan
from potato_harvest import _lease

class PickupObservationChanged(FarmWait):
    """The callback has sent only a read snapshot, never navigation."""
    no_navigation_sent=True
    def __init__(self,detail,observation,fresh,drop):
        super().__init__('WAIT_LOOT',detail)
        self.refusal={'no_navigation_sent':True,'uuid':drop['uuid'],
                      'observation_time':observation.get('time'),'fresh_time':fresh.get('time'),
                      'observed_drop':drop,'fresh_player':fresh.get('pos')}


def make_plant_access(center, *, radius=2, checkpoint=lambda:None, existing_source=None):
    """Normal flight above one confirmed harvested AIR cell, then center return."""
    request={'authorized':True,'center':center,'radius':radius,'crop':'wheat'}
    if existing_source is not None:request['existing_source']=existing_source
    layout=plan(request)
    offset=2.6 if existing_source is not None else 1.6
    home=[center[0]+.5,center[1]+offset,center[2]+.5]
    def access(c,pos,observation,stage):
        if pos not in layout['cells']or stage not in ('before_harvest','before_plant','after_plant'):
            raise FarmWait('WAIT_ROUTE','Plant access must stay in the exact original field')
        checkpoint();_lease(c,observation,observation['recent_hurt_at'])
        target=[pos[0]+.5,pos[1]+offset,pos[2]+.5]if stage in('before_harvest','before_plant')else home
        current=c.status();safe_y=max(current['pos'][1],target[1])
        # Ground pickup may end one block below the planted field. Rise within
        # that actual clear column before crossing the higher farmland edge.
        if current['pos'][1]<target[1]-.15:
            c.checked('navigate',target=[current['pos'][0],safe_y,current['pos'][2]],arrival=.15,seconds=15,air_only=True)
            current=c.status();checkpoint();_lease(c,current,observation['recent_hurt_at'])
        reply=c.checked('navigate',target=target,arrival=.15,seconds=15,air_only=True)
        actual=c.status();checkpoint();_lease(c,actual,observation['recent_hurt_at'])
        if math.dist(actual['pos'],target)>.6:
            raise FarmWait('WAIT_RECONCILE','Actual planting access pose is unproved; no repeated flight')
        return {'request_id':reply.get('id'),'movement_only':True,'stage':stage}
    return access


def make_pickup(center, *, radius=2, checkpoint=lambda: None, crop='potato'):
    """Return run(pickup=...) for a caller already hovering above source water.

    Native air_only validates the actual complete player-body path. This callback
    offers no fallback, reconnect, mining or anonymous loot collection.
    """
    descriptor=crop_descriptor(crop)
    accepted={POTATO} if descriptor.name=='potato' else {descriptor.item,descriptor.harvest_item}
    layout = plan({'authorized': True, 'center': center, 'radius': radius,'crop':descriptor.name})
    center = layout['center']
    home = [center[0]+.5, center[1]+1.6, center[2]+.5]
    claimed = set()

    def point(value):
        return (isinstance(value, list) and len(value) == 3
                and all(type(v) in (int, float) and math.isfinite(v) for v in value))

    def bounded(pos):
        return (point(pos) and all(layout['scan_min'][i] <= pos[i] < layout['scan_max'][i]+1 for i in (0, 2))
                and center[1]-(1 if descriptor.name=='wheat'else 0) <= pos[1] <= center[1]+2)

    def pickup(c, drop, observation):
        uuid = drop.get('uuid'); stack = drop.get('stack') or {}
        if (not isinstance(uuid, str) or not uuid or uuid in claimed
                or type(drop.get('id')) is not int
                or stack.get('item') not in accepted or type(stack.get('count')) is not int
                or not 1 <= stack['count'] <= 64 or drop.get('remaining_count') != stack['count']
                or not bounded(drop.get('pos'))):
            raise FarmWait('WAIT_LOOT', 'Fresh exact unclaimed '+descriptor.name+' UUID/count within the field is required')
        hurt = observation.get('recent_hurt_at')
        if type(hurt) is not int:
            raise FarmWait('WAIT_SAFETY', 'Original injury marker is unavailable')

        def safe(state):
            checkpoint(); _lease(c, state, hurt)
            if state.get('flight') is not True or state.get('health') != 20:
                raise FarmWait('WAIT_SAFETY', 'Full-health guarded flight must remain active')

        safe(observation); safe(c.status())
        fresh = c.request('snapshot'); safe(fresh)
        if (type(fresh.get('time')) is not int or type(observation.get('time')) is not int
                or not 0 <= fresh['time']-observation['time'] <= 2500):
            raise FarmWait('WAIT_LOOT', 'Known drop observation became stale before movement')
        current = next((e for e in fresh.get('entities', []) if e.get('uuid') == uuid), None)
        if current is None:
            return {'movement_request': None, 'movement_only': True,
                    'scope': 'known UUID no longer loaded; helper must prove actual pickup'}
        actual = current.get('stack') or {}
        if (current.get('type') != 'minecraft:item' or current.get('id') != drop.get('id')
                or actual.get('item') != stack['item'] or type(actual.get('count')) is not int
                or actual['count'] != stack['count'] or not bounded(current.get('pos'))
                or math.dist(current['pos'], drop['pos']) > (3 if descriptor.name=='wheat'else 1)
                or not point(fresh.get('pos')) or math.dist(fresh['pos'], home) > .65):
            raise PickupObservationChanged('Known UUID/stack or bounded center-hover context changed',observation,fresh,drop)
        target = [current['pos'][0], home[1], current['pos'][2]]
        lower=None
        if home[1]-current['pos'][1]>1.3:
            lo=[math.floor(target[0])-1,center[1]-2,math.floor(target[2])-1]
            hi=[lo[0]+2,center[1]+3,lo[2]+2]
            scan=c.request('scan',min=lo,max=hi,details=True);safe(scan)
            total=math.prod(b-a+1 for a,b in zip(lo,hi))
            if (scan.get('phase')!='done'or scan.get('world_session')!=c.world
                    or scan.get('scan_cells_read')!=total or scan.get('scan_total_cells')!=total):
                raise FarmWait('WAIT_LOOT','Lower field-edge pickup needs a complete current dry support scan')
            rows={tuple(r['pos']):r for r in scan.get('blocks',[])}
            x,z=math.floor(target[0]),math.floor(target[2]);y=math.floor(current['pos'][1]-.001)
            floor=rows.get((x,y,z),{})
            if (floor.get('fluid')is not False or floor.get('block_entity')is not False
                    or not (floor.get('state')in ('Block{minecraft:dirt}','Block{minecraft:grass_block}[snowy=false]')
                            or floor.get('state','').startswith('Block{minecraft:farmland}[moisture='))
                    or any(r.get('fluid')or r.get('block_entity')for p,r in rows.items()if p[0]==x and p[2]==z and p[1]>y)):
                raise FarmWait('WAIT_LOOT','Lower field edge changed or has water/container hazards')
            target=[x+.5,home[1],z+.5]
            lower=[x+.5,current['pos'][1]+.2,z+.5]
        claimed.add(uuid)  # Helper journals this callback before invocation.
        safe(c.status())
        outward = c.checked('navigate', target=target, arrival=.25, seconds=10, air_only=True)
        reached = c.request('snapshot'); safe(reached)
        if not point(reached.get('pos')) or math.dist(reached['pos'], target) > .6:
            raise FarmWait('WAIT_RECONCILE', 'Outward flight arrival is unproved; no movement replay')
        if lower is not None:
            c.checked('navigate',target=lower,arrival=.1,seconds=10,air_only=True)
            actual=c.request('snapshot');safe(actual)
            if math.dist(actual['pos'],lower)>.4:
                raise FarmWait('WAIT_RECONCILE','Lower field-edge arrival is unproved')
            c.checked('navigate',target=target,arrival=.15,seconds=10,air_only=True)
        safe(c.status())
        inward = c.checked('navigate', target=home, arrival=.25, seconds=10, air_only=True)
        returned = c.request('snapshot'); safe(returned)
        if not point(returned.get('pos')) or math.dist(returned['pos'], home) > .6:
            raise FarmWait('WAIT_RECONCILE', 'Center return is unproved; no movement replay')
        return {'movement_request': outward.get('id'), 'return_request': inward.get('id'),
                'movement_only': True, 'scope': 'bounded native flight; helper must prove actual pickup'}

    return pickup
