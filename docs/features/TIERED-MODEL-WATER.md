# Opt-in sealed tiered water envelope

`bucket_place` retains the normal bucket interaction, singleton requirement, durable one-use receipt, loaded-chunk checks, locked projection, exact target/support, live entity checks and server confirmation.

The existing `projected_model_water_source: true` mode stays planar by default. A caller may additionally request the strict boolean `model_water_tiered_containment: true`. `model_water_bounds` must then cover exactly source Y−4 through Y+1, at most 33×33 horizontally and 8192 cells. The requested source must be an original model level-zero water cell, inside the horizontal boundary.

The tiered proof traverses unlimited horizontal reach and downward flow through declared wet cells. This over-approximates source regeneration rather than assuming the usual seven-block reach. Every exit must meet an unchanged dry modeled fluid barrier; escaping the envelope, unmodeled air, changed blocks, lava, block entities in wet cells, living entities, bubble-producing floors and potentially waterlogged regenerated boundaries fail closed. The projection's wet cells represent a potential envelope, not a promise of exact flowing levels or a completed construction audit.

Supports remain dry inert full blocks. This change does **not** allow clicking a waterloggable slab: vanilla would waterlog it instead of placing water above. Use a real full-block side anchor that belongs to the locked projection.

This is a host change and requires a full client restart. It cannot be installed through an engine-only hot reload. Geometry validation does not replace downstream live flow checks, dry-drain checks, actual spawning, player kill/XP measurements or storage verification.
