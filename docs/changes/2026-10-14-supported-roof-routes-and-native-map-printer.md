# Supported roof routes and native map printer

Current-world roof harvesting stopped before mining because Flight settled at
Y61.784 for an integer Y62 target. The next body sweep correctly found the
adjacent Y61 floor. This was a navigation height problem, not a changed mine
target. The original stopped journals have no pending mining and were retained;
their exact owned leases were released before separate fresh intents.

Supported local air routes now optionally add 0.2 blocks to integer cell feet
and request the host's minimum material arrival radius of 0.2. A 1.8-block body
still fits the same two fully scanned air cells. Legacy callers retain their
original height and arrival defaults. Roof station, entry, and pickup calls use
the margin. Unknown movement intents still remain pending and are never replayed.
Seventy-nine local route, roof, and navigation tests pass, including reproduction
of the floor intersection after Flight settles below the target.

The hot worker update copied all 270 verified installed files and changed only
`material_jobs/local_air_path.py`, `roof_harvest.py`, and `navigation.py`.
Import checks passed, installation backed up the previous worker, and no game
restart was performed. Installed manifest SHA256:
`7300cc47caaf97c622a7d03275c5939edfbf822ed83fc018c0f6850fc91216dd`.

Live harvesting subsequently crossed the former stopping point, removed four
roof columns, and confirmed an exact two-block dripstone inventory gain. It
returned through the scanned original shaft and confirmed protected high
parking. The 64-item subtarget was not achieved; the accessible roof ran out.
Proof: `work/live-20261004/dripstone-current-roof-638/`.

The two actual blocks were returned to the original map. Native
`projection_start` ran with `auto_move=true`, the ProfessionalPrinter confirmed
both placements, and its queued work ended with missing materials. It used the
original 16512-cell selection without a reduced projection batch. An independent
complete loaded-server scan and original model hash then proved 14566/16512
matched, 1946 remaining. This is still incomplete and lacks final filled-map
pixel acceptance. Proof: `work/live-20261004/native-printer-carried-map-640/`.

Current Bobby hints were ranked by cached dripstone density, then the best
nearby region was scanned in the actual world. That live scan found 406
dripstone blocks, with dry exposed faces recorded separately. Access to that
region still needs a fresh safe route; neither cached counts nor exposed-face
offers are inventory credit. Proof:
`work/live-20261004/dripstone-rich-neighbor-live-639/`.
