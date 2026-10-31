# Verified source-column bucket service

Host protocol: `projected_source_column_protocol=1` (introduced in **2026.10.30.6**). This is a host change and needs a full restart. Engine 1.8.40 is unchanged. An installed older host must be rejected before selecting or using a bucket. The first release is scoped to the measured **3×1×9 chamber with an unfilled westward overflow above it**; it is not a general water placer.

## Preconditions and scope

- The existing locked projection defines all 27 interior cells as ordinary source water. Bounds are three cells along X, one along Z, nine along Y.
- All three original **UP-facing droppers** seal the floor. Their triggered state may change with the clock, but their block type and orientation may not.
- The request supplies all **75 exact current boundary pins**: three floor cells and 72 wall cells. No missing/duplicate/foreign pins. Native validation checks actual loaded world geometry before sending and during confirmation.
- Walls are dry, inward-blocking full cubes or the exact original dry south-facing bottom cobblestone stairs on the north edge. Their boundary faces are checked against actual collision shapes. A pinned full-cube material substitution can remain a safe barrier without being counted as blueprint completion.
- The upper row must remain AIR during column repair; its projection must be the original westward levels 2/1/0. The upper overflow is a separate operation, not implicitly filled.
- Current cells can only be AIR or plain WATER; existing sources are preserved. A target already at level 0 is skipped by the caller, never poured again.
- Normal healthy guarded material ownership is required. The native source service additionally requires HP ≥19, food ≥16 and air ≥min(270,max air); the Python wrapper initially requires HP20. No lava or other living entities in the chamber. Target-cell entity exclusion remains in the ordinary bucket action.

This mode never moves the player, removes a source, refills a bucket, edits safety/combat records or changes module settings. The caller must provide a valid service pose, singleton water bucket and a normal visible support face adjacent to the target. Waterlogged blocks are not source cells.

## Sealed-work eligibility (2026.10.31.1)

`projected_source_column_shielded_work_protocol=1` scopes the legacy nearby-hostile admission rule for this source-column **placement only**. It first revalidates the complete 75-pin shell, floor, sources, actor reserve and absence of other living entities inside the chamber. The player's whole bounding box must remain horizontally inside the chamber and at/above its floor.

Only current server-loaded ordinary zombies, skeletons and slimes may be disregarded when invisible, with their whole body below the player's feet, no damage in the past five seconds and no moving foreign projectile nearby. From 2026.10.31.2, a player entirely inside the verified floor-and-wall shell can work even if such an outside enemy is above the floor: the recorded zombie at Y63 behind the glass exposed that earlier false rejection. Above the enclosure, enemies must still be entirely below the intact floor and meet the existing clearance margins (12 blocks for skeletons, 6 for melee mobs). Near creepers and all other unsupported species, visible enemies, enemies extending above the player's feet, incoming projectiles, active defense and missing boundary proof still block input. From 2026.10.31.3, the broad 16-block box query is narrowed for a remote ordinary creeper only: the actor must be entirely enclosed, the current server-loaded creeper must be unpowered, unignited, not swelling, invisible, entirely below the actor's feet, and its actual bounding-box distance must exceed 16 blocks. This addresses the recorded approximately 24-block diagonal false positive; it does not change close-creeper or exposed-work handling. PvE, health protection, ownership and manual takeover are unchanged. Ordinary bucket filling receives no such exception; supply can be relayed from a verified nearby natural pool.

Admission diagnostic protocol 2 explicitly reports `input_sent=false` when a particular request is rejected before construction/use of a bucket action. The Python executor requires matching request/world IDs, current ownership, no active bucket/navigation and no sent receipt for that request before clearing its pending-use marker and raising `SourceAdmissionRejected`. It never automatically retries. Absent/mismatched diagnostics or an actually dispatched use retain the original uncertain identity.

## One-cell call

Use the existing `RetainedUnknownMaterialClient` and the new reusable module:

```python
from projected_source_column import place

result = place(
    client,
    low=[761388,59,793986],
    high=[761390,67,793986],
    target=[761388,59,793986],
    support=[761387,59,793986],
    face='east',
    placement_key=live_selection_key,
    out=job_directory/'source-761388-59',
)
```

This example is **not ready to run against an unsealed floor**. The wrapper reads the current model/envelope and produces its boundary pins. On the currently recorded missing-droppers fixture it rejects before bucket selection or use.

Native request extension to `bucket_place`:

- `projected_source_column: true`
- `placement_key`: current locked projection
- `source_column_bounds: {min:[x,y,z],max:[x+2,y+8,z]}`
- `column_boundary_pins`: exactly 75 `{pos:[x,y,z],expected_state:"Block{...}"}` records from a fresh coherent scan

Ordinary `pos`, `expected_state`, singleton `expected_hand`, `support`, `face`, `expected_support_state` and current world/revision/material-lease fields remain required. This mode is place-only and exclusive with `projected_water_column`, `projected_water_channel` and `projected_waterlog_drain`.

## Explicit center-source supply (2026.10.31.4)

`projected_source_column_supply_protocol=1` enables a separate **fill-only** operation inside the same pinned chamber. It is exclusive with every placement/drain/other water mode. The chosen source must be the middle X cell of a currently complete three-source row, supported by source water below or the verified full dropper floor. The two outer seed sources cannot be selected.

The native guard retains every other captured source and all 75 seals through the fill. Only the selected center is omitted from that preservation set, because a normal fill may temporarily remove it. The ordinary singleton-bucket use, durable claim, current-connection block/slot acknowledgements and exact inventory delta remain mandatory. Only this verified supply FILL may target water containing the local player; all other entities, ordinary fills and every placement retain the existing entity exclusion.

The new `projected_source_column.refill(client,low,high,source,key,out)` executor expects a prepared singleton empty bucket and valid service pose. It requires both native confirmations and two further scans proving the center and the whole former source set have remained or regenerated as level-0 water, with no seal change or new external fluid. An actual fill that is acknowledged but does not regenerate is recorded as **restore required**; it is not retried or called a successful renewable supply. Existing original endpoints remain untouched. This removes the need for repeated hazardous trips to an external pond.

## Evidence and recovery

There is exactly one normal vanilla bucket use. The existing durable `BucketUseStore` claim, current-connection target block update, selected-slot inventory update, exact inventory delta and prediction-settling window remain unchanged. A receipt additionally identifies `bucket_water.projected_source_column=true`.

The wrapper journals intent and original request identity, then requires both native server confirmations. It independently obtains two fresh coherent scans, preserving prior sources and all boundary pins, confirming the new source and checking for new water/lava outside the chamber. It also checks one water bucket consumed and one empty bucket gained. A failure after input is **not retried**; an already confirmed source with incomplete subsequent observations must be inspected, not replaced.

Build rows bottom-up. At each row verify the end sources and then the center; observe any source regeneration rather than assuming a server rule. Preserve existing sources and completed rows. Do not use this workflow to place the top overflow or the farm's other waterlogged floors/trapdoors.

## Validation

- Candidate host compiled against the installed 30.5 host, engine 1.8.40 and the actual 26.2 version-manifest dependencies.
- 96 Java tests passed, including existing bucket receipt/store, falling-column, channel, waterlog-drain and new source-chamber policy/wiring regressions.
- 17 Python source-chamber tests and 12 existing channel-wrapper tests passed, including rejection on old hosts/missing floors and retention of an uncertain request without retry.
- These are local artifact/logic tests. They do **not** establish installation, live bucket acceptance, repaired water, successful downstream flow or whole-farm completion. Recheck the native protocol and field prerequisites after deployment.

## Original bent overflow (2026.10.31.6)

After all27 chamber sources are confirmed, the separate `projected_bent_channel_protocol=1` supports exactly eight original open-top cells: source at the upper east corner, three steps west then four south, model water levels0..7. This is an exclusive place-only bucket mode. Native validation retains all27 source cells and75 seals, requires original glass floors after the turn, every original dry glass side wall and the exact closed dry spruce terminal trapdoor. All cells must be visible/server-loaded and contain no interfering entities. Existing source repair and supply modes still require their dry top; this does not relax their admission.

`projected_bent_channel.place(client,low,high,key,out)` journals one normal use, requires current-connection block and inventory confirmations, then three coherent504-cell frames with exact0..7 downstream flow, all27 prior sources, unchanged boundaries and no new external fluid. Dynamic dropper trigger phases are compared without treating a clock transition as damage. An unknown use is retained without replay. A source-confirmed but incomplete-flow result is not a completed channel.

Relevant candidate verification:131 Java and36 Python tests passed. These do not substitute for live downstream flow or whole-farm production acceptance.

### Staged third-cell source (31.7)

Live31.6 confirmed the original top source and preserved all27 chamber sources, but water stopped at level1:26.2 FlowingFluid.spread skips lateral spreading from a non-source over the same fluid below (`isWaterHole`). Therefore the initial pour is not complete downstream acceptance. Preserve its original receipt; do not pour it again.

`projected_bent_channel_seed_protocol=1` admits a separate single placement only at original path index2, with original index0 source present, index2 still AIR, all27 chamber sources and75 seals intact. The live phase regenerates the middle source and observes levels0,0,0,1,2,3,4,5. Ordinary singleton empty-bucket fills collect index2 first (observed0,0,1,2,3,4,5,6), then the regenerated index1 source. The original index0 is never collected. Three coherent frames must then show the original0..7 gradient, preserved27 sources, unchanged boundaries and no new external fluid. The executor retains source-confirmed or fill-confirmed receipts even if later flow verification fails. No implicit retry, dismantling or original-source removal is involved.

A renewable bucket can first be taken from completed center67 using the ordinary fill path from a dry pose above the level1 top cell, with both native acknowledgements and independent regenerated-source observations. This is separate from the source-only dry-top supply extension. Relevant candidate tests:132 Java and39 Python passed; the two collection stages were subsequently confirmed live with three0..7 frames and all27 chamber sources preserved.

## Supply after the original top flow is present (31.11)

`projected_source_column_overflow_supply_protocol=1` adds explicit `source_supply_completed_overflow:true` to the existing fill-only supply mode. Default supply still requires a dry top. The new mode requires every other interior cell to remain source water, all75 original seals, and the exact original top three levels2/1/0. The middle selected cell is the sole transient exception; before input its complete three-source row and source/full support are still required. Thus every27th cell is source before use, while that one center can temporarily become AIR/flow during regeneration. Outer seed cells cannot be excluded.

This is a geometry/context extension to a completed source column, not a change to danger thresholds. `shieldedActor` and SourceColumnThreatPolicy are reused unchanged: current physical isolation, supported enemy type, invisibility, below-floor/distance conditions, no recent injury or moving foreign projectile remain mandatory. Health, food, oxygen, manual takeover and native life locks are untouched. In the recorded supply refusal, an invisible zombie was below the sealed floor; the former ordinary fill did not have this proof and was correctly rejected before input.

`refill(...,completed_overflow=True)` requires the new native protocol and receipt flag. It still requires both native server confirmations and fresh preservation/regeneration observations of all27 sources and existing top water. The construction caller separately verifies the full eight-cell downstream path; this supply proof alone does not assert that entire transport path is complete.

Candidate validation:169 Java and157 Python tests passed, including rejection of outer/invalid exceptions, wrong top gradients, old-host scope rejection and receipt separation from dry-top supply. Installation and live refilling acceptance are separate.
