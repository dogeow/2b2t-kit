"""Settle one bottle at a time under an existing native material lease."""
import json
import time
import uuid
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from native_outcome_fence import wait_exact_idle_terminal

ITEM = "minecraft:experience_bottle"


def _ready(state, client, origin):
    lease = state.get("supervision_lease") or {}
    point = state.get("pos") or []
    return (
        state.get("connected") is True and state.get("world_session") == client.world
        and lease.get("job_session") == client.task
        and lease.get("id") == client.heartbeat.id
        and lease.get("revision") == state.get("control_revision")
        and state.get("health") == 20 and state.get("guard_armed") is True
        and state.get("guard_pve_only") is True and state.get("auto_log") is True
        and not state.get("safety_hold", {}).get("active")
        and not any(state.get(key) for key in ("screen", "manual_movement", "guard_busy", "flight", "navigating"))
        and state.get("on_ground") is True and state.get("pitch", 0) >= 80
        and len(point) == 3 and all(abs(a - b) < .075 for a, b in zip(point, origin))
    )


def consume(client, count, out):
    """Use a bounded number of already held bottles at an approved work position."""
    if type(count) is not int or not 1 <= count <= 64:
        raise ValueError("An exact batch of one to 64 experience bottles is required")
    root = Path(client.root)
    path = Path(out) / "experience-bottles.json"
    intent = root / "experience-bottle-intent.json"
    pointer = root / "experience-bottle-active.json"
    if path.exists() or intent.exists():
        raise RuntimeError("Original bottle work must be reconciled before another batch")
    if pointer.exists():
        previous = Path(json.loads(pointer.read_text())["journal"])
        saved = json.loads(previous.read_text())
        if not saved.get("complete") or saved.get("pending"):
            raise RuntimeError("Previous bottle batch is unresolved; preserve its receipt")

    initial = wait_exact_idle_terminal(client)
    origin = initial["pos"]
    before = inventory_counts(initial)[ITEM]
    if not _ready(initial, client, origin) or initial["hand"]["item"] != ITEM or initial["hand"]["count"] < count:
        raise RuntimeError("Grounded guarded owner and exact bottle stack required")
    book = {"world_session": client.world, "before": before, "before_xp": initial["experience_total"],
            "requested": count, "pending": None, "receipts": [], "complete": False}
    write_json(path, book)
    write_json(pointer, {"journal": str(path.resolve())})
    for _ in range(count):
        state = client.status()
        held = inventory_counts(state)[ITEM]
        xp = state["experience_total"]
        if (not _ready(state, client, origin) or state["hand"]["item"] != ITEM
                or held != before - len(book["receipts"])):
            raise RuntimeError("Bottle workspace or exact inventory changed")
        request_id = str(uuid.uuid4())
        issued = int(time.time() * 1000)
        request = {
            "id": request_id, "protocol": 1, "world_session": client.world,
            "lease_id": client.heartbeat.id, "task_session": client.task,
            "control_revision": state["control_revision"], "player_uuid": state["player_uuid"],
            "input_serial": state["game_interaction"]["interaction_serial"], "issued_at": issued,
            "expires_at": issued + 4500, "player_pos": origin,
            "expected_count": state["hand"]["count"],
        }
        claim = root / "experience-bottle-claims" / (request_id + ".json")
        book["pending"] = {"intent": request, "bottles_before": held, "xp_before": xp}
        write_json(path, book)
        write_json(intent, request)
        try:
            deadline = time.monotonic() + 6
            frames = []
            while len(frames) < 2:
                observation = client.status()
                if not _ready(observation, client, origin):
                    raise RuntimeError("Bottle workspace changed with an outstanding intent")
                if (claim.is_file() and inventory_counts(observation)[ITEM] == held - 1
                        and observation["experience_total"] > xp):
                    if not frames or observation["time"] > frames[-1]:
                        frames.append(observation["time"])
                else:
                    frames.clear()
                if time.monotonic() >= deadline:
                    raise RuntimeError("Original bottle debit or experience unconfirmed; no replay")
                time.sleep(.12)
        finally:
            if intent.exists() and json.loads(intent.read_text()).get("id") == request_id:
                intent.unlink()
        book["receipts"].append({**book["pending"], "xp_after": observation["experience_total"],
                                 "bottles_after": held - 1, "frames": frames})
        book["pending"] = None
        write_json(path, book)
    book.update(complete=True, after=before - count, xp_after=observation["experience_total"],
                level_after=observation["experience_level"])
    write_json(path, book)
    return book
