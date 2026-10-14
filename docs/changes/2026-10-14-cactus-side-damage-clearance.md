# Cactus side access and ordinary pickup

The user corrected the previous overhead harvesting plan: standing on a cactus
also causes damage. A collision-free pose above the smaller collision shape is
not sufficient. `renewable_cactus.side_pose_clear` now treats the complete cactus
cell as a damage hazard, with a padded player body and bounded complete scans.
The rule also rejects neighboring cactus, liquids, unobserved space, and containers.

`harvest_top` stages outside the plant, enters a checked side pose, then makes a
second checked side adjustment before mining. This compensates for the native
arrival stopping approximately 0.15 blocks short: the ordinary pickup box can
then reach randomly offset cactus drops immediately. It never invokes the generic
`collect_item` route, which could choose a pose above a remaining cactus.

Only an explicitly authorized current natural patch is used. The highest cactus
must have another cactus below it. A harmless cactus flower above is allowed;
another cactus or an unknown block above is rejected. Before and after the normal
mine action, full native scans verify the target and retained base. Success needs
an exact backpack increase of one. All intents are journaled before dispatch;
unknown or missing pickup gains are preserved and never counted or replayed.

The generic colored-source acquisition path now delegates cactus to this kernel,
tries the highest segments first, and keeps its existing limit of four source
blocks per call. Other plant, clay and ink behavior is unchanged.

Twenty-seven focused source and cactus tests pass, including damaging top faces,
neighboring cactus, incomplete geometry, flowering tops, retained roots, generic
pipeline routing, and non-replay after an unknown side-harvest receipt.

Live evidence: the first side pose kept health at 20 but missed one drop; it has
zero inventory credit and its terminated observer was released exactly. The
adjusted side pose then produced four separately verified cactus gains while
retaining their bases and keeping health/food at 20. Evidence lives under
`work/live-20261004/cactus-side-pickup-harvest-598/`. The side kernel is hot installed;
the generic pipeline bundle `cactus-side-pipeline-worker-599` was installed after
the sole actor ended on manual takeover. Its manifest SHA256 is
`8bd14b381c8d441e7362f1c7cd79a47d88310dc8546b481e194a414f347a5a15`.
No game restart was used and no game action was sent after manual takeover.

Current inventory at this verification was seven cactus. Local planting and the
original map's remaining 1990 cells are still pending; this change does not claim
map completion or a planted farm.
