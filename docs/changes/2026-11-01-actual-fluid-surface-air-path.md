# Use the actual fluid surface for dry air navigation

The player was observed at Y62.94375 above water in voxel Y62. The air-only swept-body check rejected the whole voxel, so an upward move was stopped even though the body did not intersect water. A normal cruise request also does not provide the precise vertical-arrival contract used by air-only navigation.

The air-only native check now compares the swept body's vertical interval with the vanilla fluid state's actual height. Full-height water above another water cell still blocks real immersion. Invalid/unknown fluid evidence, unloaded chunks, block collisions, fire, cobweb and powder snow remain rejected. This does not permit swimming in the dry route or change oxygen protection.

Candidate 2026.11.01.8 passes 258 isolated Java tests including the recorded body height, partial flow, full-height water, real overlap and invalid evidence. The artifact changes MaterialAirContactPolicy, the bridge and its compiler-generated nested classes plus metadata; no engine or Mixin change. A full restart is required. The one known open west service cap must be restored first after restart; no water request is replayed.
