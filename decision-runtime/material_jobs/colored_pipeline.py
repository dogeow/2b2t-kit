"""Exact vanilla colored blocks through the existing sole material backend.

32 outputs share a small stock-driven dependency walk. All counts are absolute
backpack totals. Recipe data comes from the installed JAR; every action has a
durable in-flight marker and must finish with fresh material conservation.
"""
from collections import Counter
import copy
import json
import math
from pathlib import Path

from craft_recipe import execute as execute_recipe
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_material_plan import ProcessingCatalog
from recipe_catalog import RecipeCatalog
from . import colored_sources
from .planning import COLORS
from .protocol import JobBlocked, JobPaused


OUTPUTS = frozenset("minecraft:" + color + suffix for color in COLORS
                    for suffix in ("_concrete", "_terracotta"))
RAW = frozenset(colored_sources.BLOCK_SOURCES) | {
    "minecraft:sand", "minecraft:gravel", "minecraft:ink_sac", "minecraft:lapis_lazuli",
    "minecraft:bone", "minecraft:bone_block", "minecraft:coal", "minecraft:beetroot",
    "minecraft:wither_rose"}
INTERMEDIATE = {"minecraft:terracotta", "minecraft:bone_meal"} | {
    "minecraft:" + color + "_dye" for color in COLORS}


class Pending(Exception):
    def __init__(self, receipt):
        self.receipt = receipt


def _ingredients(recipe, rounds):
    result = Counter()
    for _, options in recipe.cells:
        if len(options) != 1:
            raise JobBlocked("Colored pipeline requires unambiguous vanilla ingredients")
        result[options[0]] += rounds
    return result


def _recipes(catalog, item):
    if item == "minecraft:clay":
        return [r for r in catalog.recipes.get(item, []) if r.id == "clay"]
    if item == "minecraft:bone_meal":
        return [r for r in catalog.recipes.get(item, [])
                if all(set(opts) <= {"minecraft:bone", "minecraft:bone_block"} for _, opts in r.cells)]
    if item in INTERMEDIATE or item.endswith(("_concrete_powder", "_terracotta")):
        return list(catalog.recipes.get(item, []))
    return []


def choose_recipe(catalog, item, amount, stock):
    """Prefer real carried ingredient ancestry, then missing leaf cost.

    A carried lapis source favors blue+green cyan; carried poppies favor poppy
    red. An absent pitcher/rose species is never made mandatory by recipe ID.
    """
    def score(output, needed, ancestors):
        held = min(needed, stock.get(output, 0))
        remaining = needed-held
        if not remaining:
            return 0, held
        if output in ancestors:
            return 10**9, held
        choices = _recipes(catalog, output)
        if not choices or output in RAW and output != "minecraft:clay":
            return remaining, held
        rows = []
        for recipe in choices:
            ing = _ingredients(recipe, math.ceil(remaining/recipe.count))
            parts = [score(i, n, ancestors+(output,)) for i, n in ing.items()]
            missing, credit = sum(p[0] for p in parts), held+sum(p[1] for p in parts)
            rows.append((credit == held, missing, -credit, recipe.id, missing, credit))
        best = min(rows)
        return best[-2], best[-1]
    choices = []
    for recipe in _recipes(catalog, item):
        ing = _ingredients(recipe, math.ceil(amount/recipe.count))
        parts = [score(i, n, (item,)) for i, n in ing.items()]
        missing, credit = sum(p[0] for p in parts), sum(p[1] for p in parts)
        choices.append((credit == 0, missing, -credit, recipe.id, recipe))
    if not choices:
        raise JobBlocked("No installed vanilla colored recipe for " + item)
    return min(choices, key=lambda row:row[:-1])[-1]


def coverage(jar):
    catalog = ProcessingCatalog(jar)
    result = []
    for color in COLORS:
        for suffix in ("_concrete", "_terracotta"):
            item = "minecraft:" + color + suffix
            powder = item+"_powder" if suffix == "_concrete" else item
            result.append({"item":item, "pipeline_implemented":bool(catalog.recipes.get(powder)),
                           "craft_recipe_ids":[r.id for r in catalog.recipes.get(powder,[])],
                           "processing_reused":"harden" if suffix == "_concrete" else "smelt/terracotta",
                           "actual_source_required":True,
                           "ink_entity_attack_implemented":False})
    return result


def _process(kind, *args):
    # Recipe planning and offline tests do not load provider/network modules.
    from . import processing
    return getattr(processing, kind)(*args)


def run(c, profile, item, target_count, out, checkpoint, *, acquire=None, craft=None, fetch=None):
    """Produce a bounded colored target; reuse c.colored_backend if attached.

    A backend binding reuses its existing client and real workbench/supply paths.
    No backend is constructed here. Without it, crafting requires an already
    owned verified crafting menu; gravel needs the backend's lease handoff.
    """
    if item not in OUTPUTS or type(target_count) is not int or not 1 <= target_count <= 2304:
        raise ValueError("Expected vanilla concrete/colored terra and absolute target 1..2304")
    backend = getattr(c, "colored_backend", None)
    if backend is not None and getattr(backend, "client", None) is not c:
        raise JobBlocked("Colored backend must already own this exact material client")
    catalog = ProcessingCatalog(profile["recipe_jar"])
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path = out/"colored-pipeline.json"
    book = json.loads(path.read_text()) if path.exists() else {
        "schema":1, "world_session":c.world, "item":item, "target":target_count,
        "inflight":None, "receipts":[]}
    if any(book.get(k) != v for k,v in (("world_session",c.world),("item",item),("target",target_count))):
        raise JobPaused("Colored pipeline journal world/target changed")
    if book.get("inflight"):
        return {"phase":"waiting", "code":"WAIT_RECONCILE", "detail":"Prior colored action unconfirmed; no replay", "journal":str(path)}
    if book.get("complete"):
        return {"phase":"done" if inventory_counts(c.status())[item]>=target_count else "blocked",
                "code":"COMPLETED_RECEIPT", "journal":str(path)}
    original_world = c.world
    actions = 0
    fetched = set()

    def client():
        nonlocal c
        if backend is not None:
            c = backend.ensure_client()
        return c

    def stock():
        checkpoint(); state = client().status()
        if state.get("world_session") != original_world or state.get("manual_movement"):
            raise JobPaused("Colored pipeline world/control changed")
        return inventory_counts(state)

    def action(kind, output, target, call, *, ingredient_totals=None, output_multiple=1):
        nonlocal actions
        if actions >= 32:
            raise Pending({"phase":"waiting", "code":"COLORED_BATCH", "requirements":{item:target_count}})
        before = stock(); book["inflight"] = {"kind":kind, "item":output, "target":target,
                                              "before":dict(before), "ordinal":len(book["receipts"])+1}
        write_json(path,book); checkpoint()
        result = call()  # Exceptions preserve the in-flight marker.
        actions += 1
        after = stock()
        safe_wait = result.get("phase") == "waiting" and (
            result.get("code", "").startswith("WAIT_") and result.get("code") != "WAIT_RECONCILE"
            or result.get("code") in ("SOURCE_BATCH", "COLORED_BATCH")
            or kind == "smelt" and bool(result.get("requirements"))
            or kind == "fetch" and "missing" in result
            or kind == "acquire" and after[output] > before[output]
               and not client().status().get("gravel", {}).get("active"))
        if result.get("phase") == "done" or safe_wait:
            if result.get("phase") == "done" and after[output] < target:
                raise Pending({"phase":"waiting", "code":"WAIT_RECONCILE", "detail":"Native done lacks fresh final inventory"})
            if ingredient_totals is not None and result.get("phase") == "done":
                gain = after[output]-before[output]
                if gain <= 0 or gain % output_multiple:
                    raise Pending({"phase":"waiting", "code":"WAIT_RECONCILE", "detail":"Craft output net delta is invalid"})
                rounds = gain//output_multiple
                if any(before[i]-after[i] != n*rounds for i,n in ingredient_totals.items()):
                    raise Pending({"phase":"waiting", "code":"WAIT_RECONCILE", "detail":"Craft ingredient/output conservation differs"})
            book["receipts"].append({**book["inflight"], "receipt":result, "after":dict(after)})
            book["inflight"] = None; write_json(path,book)
        else:
            raise Pending({**result, "code":"WAIT_RECONCILE", "detail":result.get("detail","Action not confirmed")})
        return result

    def acquire_raw(output, target):
        if output in colored_sources.BLOCK_SOURCES or output == "minecraft:ink_sac":
            fn = lambda:colored_sources.acquire(client(),output,target,profile,out/"sources",checkpoint)
        elif acquire is not None:
            fn = lambda:acquire(output,target)
        elif backend is not None:
            fn = lambda:backend.acquire(output,target)
        elif output == "minecraft:sand":
            from .acquisition import acquire as collect_sand
            fn = lambda:collect_sand(client(),output,target,profile,out/"sand",checkpoint)
        else:
            raise Pending({"phase":"waiting", "code":"WAIT_SOURCE", "requirements":{output:target},
                           "detail":"Need verified raw source or existing backend acquisition"})
        result = action("acquire",output,target,fn)
        if stock()[output] < target:
            raise Pending(result if result.get("phase") != "done" else {
                "phase":"waiting", "code":"WAIT_SOURCE", "requirements":{output:target}})

    def ensure(output, target, ancestors=()):
        held = stock()
        if held[output] >= target:
            return
        if output in ancestors:
            raise JobBlocked("Colored ingredient cycle")
        if (fetch is not None or backend is not None) and output not in fetched:
            fetched.add(output)
            fn = (lambda:fetch({output:target})) if fetch is not None else lambda:backend.fetch({output:target})
            result = action("fetch",output,target,fn); held = stock()
            if result.get("phase") in ("blocked","paused"):
                raise Pending(result)
            if held[output] >= target:
                return
        if output.endswith("_concrete"):
            deficit = target-held[output]
            ensure(output+"_powder", deficit, ancestors+(output,))
            fn = (lambda:backend.harden(output,target)) if backend is not None else lambda:_process("harden",client(),output,target,profile,out/("harden-"+output.split(":")[-1]),checkpoint)
            result = action("harden",output,target,fn,
                            ingredient_totals={output+"_powder":1})
            if result.get("phase") != "done":
                raise Pending(result)
            return
        if output in RAW and output != "minecraft:clay":
            acquire_raw(output,target); return
        if output == "minecraft:clay" and held["minecraft:clay_ball"] < 4:
            # Prefer actual silk clay stock/source only if explicitly configured.
            if any(r.get("item")==output and r.get("authorized") is True for r in profile.get("colored_source_regions",[])):
                acquire_raw(output,target); return
        recipe = choose_recipe(catalog, output, target-held[output], held)
        rounds = math.ceil((target-held[output])/recipe.count)
        ingredients = _ingredients(recipe,rounds)
        for raw, n in ingredients.items():
            ensure(raw,n,ancestors+(output,))
        if recipe.id in catalog.smelting:
            raw = next(iter(ingredients))
            ensure("minecraft:coal", sum(math.ceil(n/8) for n in _distribution(rounds,len(profile.get("furnace_positions",[])))),ancestors+(output,))
            spec = {"recipe_id":recipe.id,"source":raw,"output":output}
            directory=out/("smelt-"+output.split(":")[-1])
            fn = (lambda:backend.smelt(spec,target)) if backend is not None else lambda:_process("smelt",client(),spec,target,profile,directory,checkpoint)
            result = action("smelt",output,target,fn,
                            ingredient_totals=_ingredients(recipe,1),output_multiple=recipe.count)
        else:
            actual = stock(); options = RecipeCatalog(profile["recipe_jar"]).candidates(output,actual,3)
            plan = next(p for p in options if p["recipe_id"] == recipe.id)
            if craft is not None:
                fn = lambda:craft(plan,target)
            elif backend is not None:
                def fn():
                    original=backend.crafting_catalog
                    pinned=copy.copy(original); pinned.recipes=copy.copy(original.recipes)
                    pinned.recipes[output]=[r for r in original.recipes[output] if r.id==recipe.id]
                    backend.crafting_catalog=pinned
                    try:return backend.craft({output:target})
                    finally:backend.crafting_catalog=original
            else:
                state=client().status(); menu=state.get("menu",{})
                if menu.get("type") not in ("CraftingMenu","InventoryMenu") or not state.get("screen"):
                    raise Pending({"phase":"waiting", "code":"WAIT_WORKBENCH", "detail":"Existing owned workbench required"})
                if menu.get("id") != getattr(client(),"owned_material_menu",None):
                    raise Pending({"phase":"waiting", "code":"WAIT_WORKBENCH", "detail":"Crafting menu is not owned by this client"})
                def fn():
                    execute_recipe(client(),plan,target)
                    return {"phase":"done"}
            result=action("craft",output,target,fn,ingredient_totals=_ingredients(recipe,1),output_multiple=recipe.count)
        if result.get("phase") != "done":
            raise Pending(result)

    try:
        before=stock()[item]
        while stock()[item] < target_count:
            # Keep four-ball clay dependencies and powder stacks physically
            # bounded even when the final item order spans many batches.
            ensure(item,min(target_count,stock()[item]+128))
            fetched.clear()
        after=stock()[item]
        if after < target_count:
            raise Pending({"phase":"waiting","code":"WAIT_RECONCILE"})
        book.update(complete=True,verified_output=after); write_json(path,book)
        return {"phase":"done","item":item,"before":before,"after":after,"gained":after-before,"journal":str(path)}
    except Pending as stop:
        return {**stop.receipt,"journal":str(path)}


def _distribution(amount, count):
    if not 1 <= count <= 16:
        raise Pending({"phase":"waiting","code":"WAIT_FURNACE","detail":"Configure1–16 verified ordinary furnaces"})
    # processing.smelt loads at most 64 per furnace per wave; later waves ask
    # for new fuel as a prerequisite. This predicts only its next actual wave.
    amount=min(amount,count*64)
    q,r=divmod(amount,count)
    return [q+(i<r) for i in range(count)]
