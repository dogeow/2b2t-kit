# Crafting recovery incident, 2026-09-22

A real Simpcraft material session stopped while manufacturing iron chains. The initial inventory pickup reply still contained the prior cursor snapshot, so take_portion incorrectly reported an ingredient quantity mismatch. The actual cursor contained 16 iron nuggets.

The old finish path did not return an occupied cursor. On heartbeat termination, the native parking branch misclassified that owned workbench as manual UI takeover and cancelled automatic logout. A later skeleton attack triggered a new real low-health hold at 1790042109940 (health 13.82674). No new death was observed. A connection was established again shortly afterward; whether it was manual has not been confirmed. Do not clear the hold or infer authorization from the earlier unlock.

Fixes in Kit 1.9.61 and local decision-runtime:
- Wait for both pickup source balance and cursor contents before splitting ingredients; do not replay ambiguous clicks.
- Return an owned crafting cursor and grid using verified normal inventory clicks before releasing the heartbeat.
- Native parking recognizes its own menu independently of cursor contents, verifies scope, and checks return capacity. Unknown/manual menus still revoke control. If there is no capacity, stop and disconnect instead of leaving a player in a blocking GUI; vanilla overflow may need manual item recovery.

Validation: 912 Java tests, 15 focused Python tests, JAR and runtime-engine verification passed. Package installed; live game still 1.9.60 at installation. Runtime validation requires user restart and manual acknowledgment of the new safety hold. No restart/reconnect was performed by this task.

House audit last verified 2413/2880 matches. Phase4 retrieved 13 iron blocks, 211 stone bricks, 64 stone; crafted 2 chiseled stone bricks, 1 iron chain and intermediate ingredients. Surplus wood fittings were stored in the approved chest at 761014,65,797833. Continue from fresh actual inventory; do not re-withdraw the old full target or assume house completion.
