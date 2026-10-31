# One inert server echo after an extra-source pickup

A live pickup sent one normal bucket use, changed the predicted local inventory, but obtained neither original server block nor selected-slot confirmation. It remains unknown as materials-16e09af36172 at 761421/62/793982. Its original receipt and durable claim must not be changed or replayed.

Protocol 2 now preflights the original dry, full, inert floor under a flowing-water target and its visible top face before dispatch. After exactly one normal bucket use, it issues exactly one useItemOn interaction with that unchanged floor while holding the transformed full bucket. Vanilla full-bucket useOn is PASS; there is no fallback useItem, artificial packet or block mutation. This reuses the established source-return echo mechanism. A consumed interaction or changed world, owner, hand or floor stops with the original claim retained.

The adapter requires one actual probe plus the original dual server acknowledgements, then separately checks three source-absent frames and bucket conservation. A regenerated source is not a corrected channel. Candidate 2026.11.01.9 passes 259 isolated Java tests, including actual vanilla PASS and compiled no-second-use wiring. Two focused adapter tests pass. Installation and live acceptance remain separate in the work checkpoint.


## Original cobblestone floor shapes (2026.11.01.10)

The actual floor below the east source is an original cobblestone stair, so the full-block-only preflight correctly refused before any use. The inert echo now permits original cobblestone stairs and slabs, including an independently wrong waterlogging bit only when every material/facing/half/corner property matches the model. The echo itself does not alter that bit. Doors, gates, trapdoors, containers, mismatched stone and other interactive blocks remain excluded. The visible actual top face still has to be reachable. 260 isolated tests pass, including every original stair state and rejection boundaries. The three ground-work ports were restored before this switch.
