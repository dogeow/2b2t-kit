# Air routes above water-covered magma

The local air planner added three blocked cells above every magma block. This
rejected a real canal workstation whose body cells were air, with water between
that air and magma. The independently checked native air-only route completed
two original canal-seal repairs with no health loss, then restored all hatches.

With a feet margin of at least 0.1, observed plain water or bubble-column fluid
immediately above magma now suppresses that additional heat padding. The magma
and water voxels themselves remain blocked, as do collision and other hazards.
Unknown fluid, lava, block entities, missing water and zero-margin routes retain
the previous padding. Campfire rules are unchanged. Native per-move collision,
dry body sweep, ownership, manual takeover and health protection still apply.

Validation: 124 related Python tests passed across local air paths, storage air
paths, material navigation and lighting routes. Offline replay of the exact
previously rejected scene now finds a four-waypoint route; it sends no input.
Python-only update; new worker/controller processes load it without a host restart.
