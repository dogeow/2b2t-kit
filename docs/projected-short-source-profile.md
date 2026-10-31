# Explicit four-row source chamber and low-roof overflow

Host31.14 adds `projected_short_source_profile_protocol=1` and `projected_bent_collection_protocol=1`. This covers the verified original east chamber in the swamp-farm model. It does not complete the farm, its bubble column or its floor cleanup.

## Protocol

The existing source placement/supply and bent overflow operations accept an explicit string `source_column_profile="four_rows"`. Omission retains the nine-row legacy profile; `nine_rows` is an explicit alias. Four rows require exact3x1x4 integer bounds,12 projected source cells,3 original UP floor droppers and32 original side seals. Every current server-loaded seal and prior source is rechecked at admission/use and during receipt observation. Default nine-row bounds and27/75 proof remain unchanged.

The short overflow is the original eight-cell path starting over the high-X source:5 west then2 south, with levels0..7. Its first3 floors are preserved chamber sources; subsequent floors are original cobblestone. Original full cobblestone/glass and dry, straight bottom stairs may seal side faces only when the inward face is complete. The dry top trapdoor at the original terminal remains exact. The first3 original roofs must be dry BOTTOM cobblestone slabs; later roofs remain the original AIR.

`bent_service_ceiling=[x,y,z]` is optional only for this profile and must equal the current action target's `above()`. That exact original bottom slab must currently be AIR; every other roof remains original. Opening and restoring it are independent normal survival operations with their own verified receipts. This flag does not perform demolition or restoration.

For a temporary staged seed, the existing explicit bent seed placement targets path index2. `projected_bent_channel_collect_index=2` then`1` is a new exclusive fill-only operation, carrying the same profile, source bounds,35 seals, placement key and optional exact service roof. The pre-use gradient must match the respective seed stage. Index0 cannot be collected; unsupported/mixed operations are rejected. The Python helper verifies the post-collection gradients before advancing. Neither collection is an automatic retry.

Native receipts identify `source_column_profile` and the collection index. Normal vanilla bucket use, durable per-cell claims, current-connection block and selected-slot inventory packets, exact inventory delta and prediction settlement remain mandatory. Existing health, oxygen, manual input, control ownership and threat thresholds are unchanged. A short overflow/collection can use the existing source-chamber shield proof only after its entire current geometry is proved again.

## Python helpers

`projected_source_column.place/refill` and `projected_bent_channel.place/remove_seed/flow_after/path_for` accept `profile="four_rows"`. `place/remove_seed` on a bent path additionally accept `service_ceiling`. Old calls keep their legacy paths. Short helpers require advertised native support and check the returned profile/index; they never silently fall back to an ordinary bucket operation.

Intent journals separate preflight (`dispatch_started=false,pending=null`) from a dispatched native request. A dispatched unknown result retains its identity and is never repeated. A confirmed source with incomplete downstream observations remains a confirmed action with unfinished geometry proof; callers must inspect the original effect before deciding the next independent stage.

## Validation boundary

188 candidate Java tests and47 related Python tests passed before installation. They cover default-versus-explicit dimensions, all35 seals and source preservation, real stair/roof collision geometry, exact5+2 path, staged collection phase/index restrictions, protocol/receipt wiring, old-host rejection, wrong roof metadata and unknown-use retention. Candidate class entries are checked against the installed31.13 baseline; engine/Mixin files and unrelated worktree changes are excluded. Live acceptance, roof restoration and whole-farm production are separate required evidence.

## Shared middle service roof (host31.15)

`projected_bent_middle_service_protocol=1` additionally supports `bent_middle_ceiling`, only when the active service roof is present and distinct. The shared point must be exactly path index1's original bottom-slab roof. Both declared openings must be AIR, with every other original roof unchanged. The receipt returns both opening positions; Python requires the shared-position echo. This lets entry roof429 stay open through the staged pour/collections, while only the active outer roof changes; no roof above newly placed water needs to be mined. The ordinary fluid-neighbour mining prohibition stays intact.

For this profile the seed at path index2 uses the southern GLASS support and its NORTH face. The northern wall is a waterloggable stair and must not be clicked with a bucket as though it were glass. Legacy seed support remains unchanged. The follow-up candidate passed189 Java and49 Python tests, including the shared-roof restriction and the real north-stair/south-glass distinction. These are candidate tests, not live acceptance.
