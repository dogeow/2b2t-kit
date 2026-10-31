# Exact original single-slab placement

The existing `interact` operation accepts `projected_slab_place: true`, `place_pos`
and the locked `placement_key`. Snapshot protocol: `projected_slab_place_protocol=1`.
It selects a real visible support ray only when vanilla `BlockPlaceContext` predicts
both the original position and the exact dry TOP/BOTTOM schematic slab state.
The same prediction is repeated after rotation, before one ordinary `useItemOn`.

The target must be original schematic air-to-single-slab repair, currently air,
server loaded, visible, without a living entity or block entity. Supports are dry
cobblestone, glass, or slabs, without containers. Existing healthy owned material,
manual input, UI, reach and occlusion checks remain. DOUBLE slabs, wet slabs,
occupied targets, competing terrain/observer guards, and wrong predictions fail.
Existing generic interactions retain their original targeting.

The short four-row source profile separately recognizes an ordinary calm unseen
creeper below its verified floor only when over eight blocks from the player and
over seven from every protected source/overflow boundary, with quiet/projectile
checks. Near, charged, swelling, visible and above-floor creepers still block.
The existing nine-row rule and global PvE protection are unchanged.

Validation: 198 related Java tests passed against the isolated 31.16 candidate,
including shape rays, guard wiring, remote-creeper distances and legacy water
regressions. Installation and actual water-flow acceptance are separate steps.
