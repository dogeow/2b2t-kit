# Drain extra sources from original flowing-water cells

The live audit found ordinary level-0 water where the locked model requires levels 1–7. The explicit `projected_flow_source_drain` fill mode permits only those cells, with current server chunks and the same locked selection. Ordinary bucket validation still requires the real plain source and singleton empty bucket. No blocks are replaced.

The scoped correction proof also supports the existing exact waterlogging drain. It reuses the tested threat policy: current occluded distant supported mobs only, quiet window and no moving projectiles; nearby/visible/creeper/unknown threats still refuse. Health, ownership, one normal use, durable claims and dual server acknowledgements remain unchanged. A confirmed pickup from a regenerating source is not proof that the channel was corrected; the controller must separately observe the source is gone and later verify full flow.

Candidate 2026.11.01.4 passes 253 isolated Java tests including the actual compiled owner/preflight wiring and capability marker. The artifact changes three classes plus version metadata. Main-host changes require restart. Live acceptance is separate in the work checkpoint.


## Removal-only remote creeper admission (2026.11.01.5)

The removal proof permits an ordinary, current, occluded, non-ignited, non-swelling creeper strictly more than eight blocks from the player and seven from the exact modified water cell, below that cell's floor. The current quiet/projectile proof remains mandatory. This follows the existing short-source distance boundaries but applies only to water removal; it does not enable construction or source placement near creepers. Near, powered, visible, igniting, above-floor and stale creepers remain rejected. The isolated artifact passes 254 Java tests.

The worker saves the exact native identity and requires dual server acknowledgements. Three fresh source-absent frames and bucket conservation are a separate postcondition; a regenerating source is never marked corrected. Two focused adapter tests pass.


## Separated ground mobs (2026.11.01.6)

A fresh refusal showed a zombie six blocks below the player, an occluded zombie villager, and a visible spider over twelve blocks away. Original-water operations now distinguish those from close threats: known ordinary ground mobs may be admitted if occluded and their bounding box is at least four vertical blocks below the player's feet, or visible and at least twelve blocks away. Quiet/projectile/health/ownership and original geometry proofs remain. Ranged mobs, creepers and endermen do not use this ground-mob exception. This affects only the typed model-water source placement and correction guards. 255 isolated tests pass, including vertical/visible/stale/type boundaries.
