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

Only current server-loaded ordinary zombies, skeletons and slimes may be disregarded when all are invisible and entirely below the intact floor, with no damage in the past five seconds and no moving foreign projectile nearby. The player's whole body must be vertically enclosed; above that enclosure, the existing clearance margins are additionally required (12 blocks for skeletons, 6 for melee mobs). Creepers and all other species, visible/same-level enemies, incoming projectiles, active defense and missing boundary proof still block input. PvE, health protection, ownership and manual takeover are unchanged. Ordinary bucket filling receives no such exception; supply can be relayed from a verified nearby natural pool.

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

## Evidence and recovery

There is exactly one normal vanilla bucket use. The existing durable `BucketUseStore` claim, current-connection target block update, selected-slot inventory update, exact inventory delta and prediction-settling window remain unchanged. A receipt additionally identifies `bucket_water.projected_source_column=true`.

The wrapper journals intent and original request identity, then requires both native server confirmations. It independently obtains two fresh coherent scans, preserving prior sources and all boundary pins, confirming the new source and checking for new water/lava outside the chamber. It also checks one water bucket consumed and one empty bucket gained. A failure after input is **not retried**; an already confirmed source with incomplete subsequent observations must be inspected, not replaced.

Build rows bottom-up. At each row verify the end sources and then the center; observe any source regeneration rather than assuming a server rule. Preserve existing sources and completed rows. Do not use this workflow to place the top overflow or the farm's other waterlogged floors/trapdoors.

## Validation

- Candidate host compiled against the installed 30.5 host, engine 1.8.40 and the actual 26.2 version-manifest dependencies.
- 89 Java tests passed, including existing bucket receipt/store, falling-column, channel, waterlog-drain and new source-chamber policy/wiring regressions.
- 13 Python source-chamber tests and 12 existing channel-wrapper tests passed, including rejection on old hosts/missing floors and retention of an uncertain request without retry.
- These are local artifact/logic tests. They do **not** establish installation, live bucket acceptance, repaired water, successful downstream flow or whole-farm completion. Recheck the native protocol and field prerequisites after deployment.
