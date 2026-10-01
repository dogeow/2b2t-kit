"""Bounded real sources for dye ingredients; no cache counts or invented drops.

The caller retains its MaterialClient lease. A profile entry explicitly names
an authorized small patch; fresh native observations decide every excavation.
Unknown mining/pickup receipts remain durable and are never re-sent.
"""
from collections import Counter
import json
import math
from pathlib import Path

from drop_collection import collect_drop
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from .protocol import JobPaused


BLOCK_SOURCES = {"minecraft:clay_ball": {"minecraft:clay"},
                 "minecraft:clay": {"minecraft:clay"},
                 "minecraft:mud": {"minecraft:mud"},
                 "minecraft:wheat": {"minecraft:wheat"}}
for _name in ("cactus", "poppy", "dandelion", "blue_orchid", "allium",
              "azure_bluet", "oxeye_daisy", "white_tulip", "red_tulip",
              "orange_tulip", "pink_tulip", "cornflower", "lily_of_the_valley",
              "pink_petals", "wildflowers", "cactus_flower", "torchflower",
              "closed_eyeblossom", "open_eyeblossom", "rose_bush", "peony",
              "lilac", "sunflower", "pitcher_plant", "sea_pickle", "cocoa_beans"):
    BLOCK_SOURCES["minecraft:" + _name] = {"minecraft:cocoa" if _name == "cocoa_beans"
                                          else "minecraft:" + _name}
GROUND = {"minecraft:" + n for n in ("dirt", "grass_block", "clay", "stone",
          "sand", "red_sand", "coarse_dirt", "podzol", "rooted_dirt", "mud", "farmland")}


def _wait(item, target, code="WAIT_SOURCE", detail="No verified authorized source"):
    return {"phase": "waiting", "code": code, "detail": detail,
            "requirements": {item: target}}


def _name(row):
    state = row.get("state", "")
    return state.split("}", 1)[0].removeprefix("Block{") if state.startswith("Block{") else ""


def _point(value):
    return isinstance(value, list) and len(value) == 3 and all(type(n) is int for n in value)


def _protected(pos, profile, state):
    boxes = profile.get("protected_regions")
    if not isinstance(boxes, list) or not boxes:
        return True
    selected = state.get("projection_selection") or {}
    if selected:
        boxes = boxes + [selected]
    for box in boxes:
        lo, hi = box.get("min"), box.get("max")
        if not _point(lo) or not _point(hi) or any(a > b for a, b in zip(lo, hi)):
            return True
        if lo[0]-16 <= pos[0] <= hi[0]+16 and lo[2]-16 <= pos[2] <= hi[2]+16:
            return True
    sites = list(profile.get("depots", [])) + list(profile.get("furnace_positions", []))
    sites += [profile[k] for k in ("workbench", "ender_chest", "shulker_pad") if k in profile]
    return any(len(p) != 3 or math.hypot(pos[0]-p[0], pos[2]-p[2]) <= 48 for p in sites)


def _regions(profile, item):
    for region in profile.get("colored_source_regions", []):
        if not isinstance(region, dict) or region.get("item") != item or region.get("authorized") is not True:
            continue
        lo, hi = region.get("min"), region.get("max")
        if (not _point(lo) or not _point(hi) or any(a > b for a, b in zip(lo, hi))
                or not -64 <= lo[1] <= hi[1] <= 319
                or hi[0]-lo[0] > 15 or hi[1]-lo[1] > 15 or hi[2]-lo[2] > 15):
            continue
        yield region


def _safe(state, world):
    if state.get("world_session") != world or state.get("manual_movement"):
        raise JobPaused("Colored source world/control changed")
    return (state.get("connected") is True and state.get("health", 0) >= 19
            and state.get("food", 0) >= 8 and state.get("guard_armed") is True
            and state.get("guard_pve_only") is True and not state.get("guard_busy")
            and not state.get("under_water"))


def _fresh_scan(c, lo, hi, checkpoint):
    checkpoint()
    reply = c.request("scan", min=lo, max=hi, details=True)
    if reply.get("world_session") != c.world or reply.get("phase") not in (None, "done"):
        return None
    # Sparse air is normal; a native scan rejects unloaded requested chunks.
    if reply.get("unloaded_chunks", 0) or not isinstance(reply.get("blocks"), list):
        return None
    return reply["blocks"]


def _candidate(rows, pos, item):
    by = {tuple(r["pos"]): r for r in rows}
    target = by.get(tuple(pos))
    if (not target or _name(target) not in BLOCK_SOURCES.get(item, set())
            or target.get("fluid") is not False or target.get("block_entity") is not False):
        return False
    x, y, z = pos
    below = by.get((x, y-1, z))
    if item == "minecraft:cocoa_beans":
        if not any(_name(by.get((x+dx,y,z+dz), {})) == "minecraft:jungle_log"
                   for dx,dz in ((1,0),(-1,0),(0,1),(0,-1))):
            return False
    elif below is None or _name(below) not in GROUND | ({"minecraft:cactus"} if item == "minecraft:cactus" else set()) or below.get("fluid") is not False:
        return False
    if item == "minecraft:cactus" and _name(below) != "minecraft:cactus":
        return False  # Retain the growing base; only harvest a verified top.
    if item == "minecraft:cocoa_beans" and "age=2" not in target["state"]:
        return False
    if item == "minecraft:wheat" and "age=7" not in target["state"]:
        return False
    # Harvest lower halves only; verify plant tops rather than credit two items.
    if "half=upper" in target["state"]:
        return False
    for p, row in by.items():
        if row.get("fluid") is not False or row.get("block_entity") is not False:
            return False
        allowed = GROUND | {"minecraft:cactus"} | ({"minecraft:jungle_log"} if item == "minecraft:cocoa_beans" else set())
        if p != tuple(pos) and row.get("solid") is True and _name(row) not in allowed:
            return False
    return True


def acquire(c, item, target_count, profile, out, checkpoint):
    """Acquire at most four source blocks, or an existing freshly observed drop.

Ink has no entity-attack native protocol: collect a real authorized ink drop,
otherwise WAIT_SOURCE. Wet clay is rejected by the current native mine guard.
"""
    if type(target_count) is not int or not 1 <= target_count <= 2304:
        raise ValueError("Colored source target must be an absolute carried count 1..2304")
    checkpoint(); state = c.status()
    if not _safe(state, c.world):
        return _wait(item, target_count, "WAIT_SAFETY", "Source collection safety preconditions missing")
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path = out / ("colored-source-" + item.split(":")[-1] + ".json")
    book = json.loads(path.read_text()) if path.exists() else {
        "schema": 1, "world_session": c.world, "item": item, "receipts": []}
    if book.get("world_session") != c.world or book.get("item") != item:
        raise JobPaused("Colored source journal belongs to another world/item")
    if any(r.get("state") == "inflight" for r in book["receipts"]):
        return _wait(item, target_count, "WAIT_RECONCILE", "Unconfirmed previous source action; no replay")
    before = inventory_counts(state)[item]
    if before >= target_count:
        return {"phase": "done", "item": item, "before": before, "after": before}
    regions = list(_regions(profile, item))
    if not regions:
        return _wait(item, target_count)
    if item == "minecraft:ink_sac":
        for drop in state.get("entities", []):
            pos = drop.get("pos", [])
            if (drop.get("type") != "minecraft:item" or drop.get("stack", {}).get("item") != item
                    or not isinstance(drop.get("uuid"), str) or len(pos) != 3
                    or _protected(pos, profile, state)
                    or not any(all(r["min"][i] <= pos[i] <= r["max"][i] for i in range(3)) for r in regions)):
                continue
            entry = {"state": "inflight", "kind": "pickup", "uuid": drop["uuid"], "before": before}
            book["receipts"].append(entry); write_json(path, book)
            checkpoint(); confirmed = collect_drop(c, drop, state)
            after = inventory_counts(c.status())[item]
            if not confirmed or after <= before:
                return _wait(item, target_count, "WAIT_RECONCILE", "Ink pickup gain not confirmed")
            entry.update(state="done", after=after); write_json(path, book)
            return {"phase": "done" if after >= target_count else "waiting", "before": before, "after": after}
        return _wait(item, target_count, detail="No authorized real ink drop; no native squid-attack protocol")
    if item not in BLOCK_SOURCES:
        return _wait(item, target_count)
    spent = {tuple(r["pos"]) for r in book["receipts"] if r.get("state") == "done" and "pos" in r}
    mined = 0
    for region in regions:
        rows = _fresh_scan(c, region["min"], region["max"], checkpoint)
        if rows is None:
            continue
        for row in rows:
            pos = row["pos"]
            if tuple(pos) in spent or _name(row) not in BLOCK_SOURCES[item]:
                continue
            checkpoint(); state = c.status()
            if not _safe(state, c.world):
                return _wait(item, target_count, "WAIT_SAFETY")
            if _protected(pos, profile, state):
                continue
            local = _fresh_scan(c, [pos[0]-1,pos[1]-1,pos[2]-1],
                                [pos[0]+1,pos[1]+2,pos[2]+1], checkpoint)
            if local is None or not _candidate(local, pos, item):
                continue
            if room_for_item(state, item) < (4 if item == "minecraft:clay_ball" else 1):
                return _wait(item, target_count, "WAIT_CAPACITY")
            if item == "minecraft:wheat" and inventory_counts(state)["minecraft:wheat_seeds"] < 1:
                return _wait("minecraft:wheat_seeds",1,"WAIT_SEED","Keep one real seed for immediate field restoration")
            # Native approach verifies reach/visibility; it does not excavate.
            from work_access import approach_faces
            face = approach_faces(c, pos, row["state"], ("up","north","south","west","east"), seconds=45)
            checkpoint(); state = c.status()
            if not _safe(state, c.world) or _protected(pos, profile, state):
                return _wait(item, target_count, "WAIT_SAFETY")
            if item in ("minecraft:clay", "minecraft:clay_ball"):
                silk = item == "minecraft:clay"
                tools = [r for r in state["inventory"] if r.get("slot",99)<36
                         and r.get("item") in ("minecraft:diamond_shovel","minecraft:netherite_shovel")
                         and r.get("count") == 1 and r.get("durability",0)>=33
                         and any(e.get("id") == "minecraft:silk_touch" and e.get("level",0)>0
                                 for e in r.get("enchantments",[])) == silk]
                if not tools:
                    return _wait(item, target_count, "WAIT_TOOL", "Required clay shovel/drop mode missing")
                tool = max(tools, key=lambda r:r["durability"])
                c.checked("select_item", item=tool["item"], slot=tool["slot"])
                actual_hand = c.status().get("hand") or {}
                if (actual_hand.get("item") != tool["item"] or actual_hand.get("count") != 1
                        or actual_hand.get("durability") != tool["durability"]
                        or actual_hand.get("enchantments",[]) != tool.get("enchantments",[])):
                    return _wait(item,target_count,"WAIT_TOOL","Actual clay shovel hand/drop mode not verified")
            else:
                c.checked("select_item", item="minecraft:diamond_sword")
            local = _fresh_scan(c, [pos[0]-1,pos[1]-1,pos[2]-1],
                                [pos[0]+1,pos[1]+2,pos[2]+1], checkpoint)
            if local is None or not _candidate(local, pos, item):
                continue
            actual = next(r for r in local if r["pos"] == pos)
            before_state = c.status(); old_count = inventory_counts(before_state)[item]
            entry = {"state":"inflight", "kind":"mine", "pos":pos,
                     "expected_state":actual["state"], "before":old_count}
            book["receipts"].append(entry); write_json(path, book)
            checkpoint()
            reply = c.request("mine_block", pos=pos, face=face, expected_state=actual["state"], seconds=20)
            if reply.get("phase") != "done":
                return _wait(item, target_count, "WAIT_RECONCILE", "Mining receipt uncertain; no replay")
            after_state = c.status()
            for drop in after_state.get("entities", []):
                if (drop.get("type") == "minecraft:item" and drop.get("stack",{}).get("item") in
                        ({item,"minecraft:wheat_seeds"} if item == "minecraft:wheat" else {item})
                        and drop.get("uuid") not in {e.get("uuid") for e in before_state.get("entities",[])}
                        and len(drop.get("pos",[])) == 3 and math.dist(drop["pos"],pos)<=6):
                    checkpoint(); collect_drop(c, drop, after_state)
            after = inventory_counts(c.status())[item]
            observed = _fresh_scan(c, pos, pos, checkpoint)
            if observed is None or any(r["pos"] == pos and _name(r) in BLOCK_SOURCES[item] for r in observed) or after <= old_count:
                return _wait(item, target_count, "WAIT_RECONCILE", "Block/drop net gain not confirmed")
            if item == "minecraft:wheat":
                # Restore the explicitly authorized crop, never start unbounded
                # planting/growth or leave a field stripped after one harvest.
                floor=[pos[0],pos[1]-1,pos[2]]
                floor_rows=_fresh_scan(c,floor,floor,checkpoint)
                farmland=next((r for r in floor_rows or [] if r['pos']==floor
                               and _name(r)=="minecraft:farmland"),None)
                if farmland is None:
                    return _wait(item,target_count,"WAIT_RECONCILE","Harvest footing changed before reseeding")
                seed_before=inventory_counts(c.status())["minecraft:wheat_seeds"]
                entry.update(stage="reseeding",seed_before=seed_before);write_json(path,book)
                c.checked("select_item",item="minecraft:wheat_seeds")
                checkpoint()
                planted=c.request("interact",pos=floor,face="up",expected_state=farmland['state'],
                                  expected_hand="minecraft:wheat_seeds")
                replanted=_fresh_scan(c,pos,pos,checkpoint)
                if (planted.get("phase")!="done" or replanted is None
                        or not any(_name(r)=="minecraft:wheat" and "age=0" in r['state'] for r in replanted)
                        or inventory_counts(c.status())["minecraft:wheat_seeds"]!=seed_before-1):
                    return _wait(item,target_count,"WAIT_RECONCILE","Reseeding state/seed delta unconfirmed; no replay")
            entry.update(state="done", after=after, gained=after-old_count); write_json(path, book)
            mined += 1
            if after >= target_count:
                return {"phase":"done", "item":item, "before":before, "after":after}
            if mined >= 4:
                return {"phase":"waiting", "code":"SOURCE_BATCH", "before":before, "after":after,
                        "requirements":{item:target_count}}
    return _wait(item, target_count)
