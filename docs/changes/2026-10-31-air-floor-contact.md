# Air-route contact at a waterlogged floor

Live construction descended onto a top slab and reported feet Y62.999999999999986 instead of63. The physical player was above its water, at HP20/air300, but the air-only voxel loop floored that value into the lower fluid cell. The following return route also used that occupied cell as its start. No new water use or mining followed the stopped navigation; the owned service hatches remain separately journaled for restoration.

The native air gate now applies a symmetric1e-7 contact tolerance to its collision sweep and voxel min/max bounds. Python body-sweep and start/end node quantization use the same vertical contact convention. The observed rounding contact is accepted; actual1e-5 penetration still includes the liquid/solid cell and is rejected. Collision, complete loaded-world checks, fluid, fire, cobweb and powder-snow exclusions remain. World blocks, native bucket guards and health protection are not altered.

Candidate validation:164 Java tests, including actual slab-shape overlap and air-gate wiring, and150 Python path/water regressions passed. Live navigation and hatch restoration remain deployment acceptance stages.
