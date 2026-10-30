# Air clearance above an open fence gate

The water-cycle route could not cross the central transport channels although both room-height AIR layers were clear. A fresh scan showed open spruce fence gates in the channel below the route. The planner had extended every fence gate into the voxel above it, including OPEN=true gates whose actual collision shape is empty.

Only the invented upper collider is now omitted for a gate with an explicitly parsed OPEN=true state. The stored gate voxel remains conservatively blocked; fences, walls, closed gates and gates without a known open state still retain the1.5-block exclusion. Native movement continues to check current real collision shapes, liquids and hazards before and during travel. No gate is toggled or removed, and magma clearance remains unchanged.

Validation:154 related Python path and bucket tests passed. Replaying only the failed scene data through the planner now yields a finite route through the existing open-gate corridor, avoiding the magma columns. This is read-only planning proof; live route execution is the deployment check.
