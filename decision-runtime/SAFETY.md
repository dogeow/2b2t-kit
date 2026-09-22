# Unattended safety

The native mod owns the emergency response; a Python process or model response is never required to notice low health.

- Below 14 health during Kit work or armed defense, stop work and persist `automation/safety-hold.json` before attempting escape.
- Try a collision-checked flight route up about 12 blocks. Do not break blocks, descend through the route, or move closer to a nearby hostile.
- Stop waiting at 6 health, a blocked route, one second without movement, or the eight-second escape deadline. Disconnect even if the height could not be reached.
- Meteor KillAura stays restricted to hostile mobs; AutoEat remains available. Temporarily suspend AutoLog during the bounded ascent, then restore it. AutoReconnect remains disabled while the hold exists.
- The lock survives restarts. Do not launch/reconnect the client or resume automation when `require_unlocked(automation_root)` fails. A missing or stale status file is not permission to ignore the durable lock.
- The lock record includes the inventory at the trigger, for manual return checks. Routine status exposes only the compact safety summary.
- Only the player can acknowledge the hold in **保护 → 自动保护 → 我已回来，解除安全离线锁**, at 18 or more health. This does not start a task. Remote bridge requests cannot acknowledge it.
- Physical emergency stop cancels both escape movement and queued Kit logout. Manual movement cancels an active escape and restores physical input. Neither clears the safety hold.
- Ordinary task completion still waits for the existing quiet period; a network-disconnect receipt is not proof of server-side survival.

Bow selection checks the held bow as well as spare bows. Bows below eight remaining durability are not used. Zombies are engaged from above only after checking the whole ascent. A low ceiling or unavailable flight falls back to existing bow/melee defense while work remains paused; it must not force a healthy player to combat-log. An unusable bow pauses work while melee protection remains enabled. Actual low health still triggers the native emergency exit.

Verification: policy and persistence tests, real tick-wiring checks, Java build, and Python controller tests. These are not a guarantee against server lag, combat-logout plugins, or sudden lethal damage. Dangerous live tests must use a disposable local world, not valuable multiplayer inventory.

During owned guard work, AutoEat temporarily uses Any mode with health/hunger thresholds of 19 and inventory search. The previous values are restored conditionally on release and a receipt permits recovery if Meteor saved temporary settings first. After health falls below 18, normal work stays paused until health reaches 19; combat still has movement priority. Real low-health exit holds are never automatically cleared.
