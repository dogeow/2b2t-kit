# Remove only incorrect waterlogging from original stairs

Two lower transport-channel floors currently contain waterlogged cobblestone stairs where the locked original requires the identical dry stair. The existing projected drain supported single slabs and trapdoors, so it could not correct these floors.

The same explicit projected drain now accepts stairs while preserving the exact block, facing, half and corner shape. It still rejects containers, changed geometry and non-source fluids, requires a singleton empty bucket, one normal use, both server confirmations and stable dry-state/inventory checks. The worker permits only original cobblestone stairs in addition to its existing types. No unknown action is replayed.

Candidate 2026.11.01.3: 251 isolated Java tests pass, including every stair facing/half/corner combination and rejection of changed shape or direction. The 16 related Python tests pass. Installation and live acceptance are tracked separately in the work checkpoint. Host class changes require full restart; the worker adapter alone can be updated in place.
