# Contained original trapdoor-row waterlogging

`projected_trapdoor_waterlog_protocol=1` adds an explicit place-only mode to `bucket_place`. It still sends one normal vanilla bucket use, records the durable bucket claim and requires independent current-connection block and selected-slot updates, exact inventory transformation and prediction retirement plus eight settling ticks. Other bucket modes keep their existing admission rules.

This mode supports only the measured translated layout: one original29-cell X row of closed, unpowered, bottom-half spruce trapdoors, all facing north or all south. The model requires WATERLOGGED=true; actual states may differ only in that bit. The selected target must still be dry before input, and every previously wet row cell is preserved.

Every admission and poll rechecks the whole loaded/visible row. Closed bottom faces seal downward flow; the original back wall and both end caps must be exact dry full blocks. The original inward top slabs must remain exact and dry. They cannot accept FLOWING_WATER, and their other horizontal neighbors must have no fluid, preventing a second source from synthesizing source water in an inward slab. The outer redstone control wire above the back wall must exist and have POWER=0 throughout the operation. This is closed-row construction containment, not permission to open gates or start the farm's flushing cycle.

Request fields extend ordinary `bucket_place`:

- `projected_trapdoor_waterlog: true`
- `placement_key`, `expected_wet_state`: original locked goal
- `trapdoor_row_bounds: {min:[x,y,z],max:[x+28,y,z]}`
- `pos` and `support`: the same actual dry trapdoor cell
- `face: "down"`, `expected_state` and `expected_support_state`: exact current dry state
- singleton `expected_hand: "minecraft:water_bucket"` and normal owner/world/revision fields

The clicked cell itself receives its source water through vanilla SimpleWaterloggedBlock handling. Ordinary basin placement still requires an adjacent non-waterloggable support and an actual dry bounded hole. The receipt adds `bucket_water.projected_trapdoor_waterlog` and `expected_wet_state`; source-water placement cannot be substituted for waterlogged-block acknowledgement.

`projected_trapdoor_waterlog.waterlog` uses the cached immutable model only for goals, refreshes current nearby world data and delegates full-row safety to native checks. It then requires three coherent local frames, preservation of already-wet neighbors, no newly wet cells outside the row and exact water-bucket−1/empty-bucket+1. `drain` reuses the existing strict `projected_waterlog_drain` operation to remove only a wrong water bit from an otherwise matching original dry slab/trapdoor, proving the opposite bucket delta. It never changes material, orientation or slab shape.

Preflight journals start with no pending use. Once dispatch begins, an uncertain identity remains pending without retry. Explicit protocol2 no-input admission rejection can be retired; confirmed native use with failed later state proof remains recorded as confirmed but not complete. Refill or later geometry changes invalidate current completion evidence without erasing the old receipt.

Validation:144 Java tests against the candidate artifact and52 Python tests passed. These cover all seals/source/control flags, exclusive mode, native one-use/receipt wiring, wrong-shape/plain-water rejection, old-host and already-wet rejection, preserved unknown identities and new external water detection. Deployment and live water transfer are separate acceptance stages.

## Live acceptance

Host31.10 completed a closed-loop small batch: five original trapdoors waterlogged, three wrong wet top slabs drained and their water reused. Each transfer had the native independent packet receipts and three settled local frames. All three owned service hatches were restored to their original half-slab states. A later whole-machine audit confirmed169 trapdoors and191 wrong wet top slabs still remaining, so this is not full-row or whole-farm acceptance. The original27 source cells and0..7 bent channel were reverified unchanged.

For a floor drain, use a dry adjacent stance outside the target cell's entity box, with a fresh unobstructed source ray. At a supported floor, the air-route primitive now handles1e-7 rounding contact consistently; it still rejects real liquid/solid penetration. Final related host/path/water regression set:164 Java and150 Python tests passed.
