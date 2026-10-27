"""Bounded observations around the existing coastal bait boat, without capture credit."""
BOAT_POSITION = [760953.5, 63.0, 797725.5]
WATCH_POSITION = [760953.5, 76.2, 797753.5]
CAPTURABLE_TYPES = frozenset(('minecraft:zombie', 'minecraft:drowned'))


def scan_tiles():
    # All four scans fit the native 32768-cell bound. The older 49x18x49
    # request exceeded it, and the old Y95 vantage lost the low boat entities.
    return [([x0, 50, z0], [x1, 78, z1])
            for x0, x1 in ((760929, 760952), (760953, 760977))
            for z0, z1 in ((797725, 797750), (797751, 797777))]


def eligible(actor):
    return (actor.get('type') in CAPTURABLE_TYPES and actor.get('alive') is True
            and actor.get('health') == 20 and actor.get('is_baby') is False
            and actor.get('has_custom_name') is False
            and isinstance(actor.get('uuid'), str) and bool(actor['uuid']))


def inland_tiles():
    """Cover the west bank and shallow caves; never infer mobs from terrain alone."""
    return [([x0,y0,z0],[x1,y1,z1])
            for x0,x1 in ((760940,760960),(760961,760981))
            for z0,z1 in ((797778,797798),(797799,797819))
            for y0,y1 in ((20,49),(50,80))]


def deep_inland_tiles():
    """Same west cave footprint below Y20, observed from a dry low air column."""
    return [([x0,y0,z0],[x1,y1,z1])
            for x0,x1 in ((760940,760960),(760961,760981))
            for z0,z1 in ((797820,797840),(797841,797861))
            for y0,y1 in ((-60,-21),(-20,19))]
