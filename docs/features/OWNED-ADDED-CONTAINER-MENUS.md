# Owned dispenser and hopper menus

The Python material client accepts `DispenserScreen`/`DispenserMenu` and `HopperScreen`/`HopperMenu` only for its current world, material task, lease and revision. The native `material_owned` witness remains the normal path.

An ordinary native `interact` currently settles after eight ticks. A delayed server-open packet can arrive after that active request has ended, so the host no longer marks the new menu owned. The Python fallback correlates that menu with a ticket captured before our own normal sword interaction, the exact successful native block-use receipt and an unchanged Minecraft human-input serial. The first adoption has an twenty-second window matching the existing container wait. A bound menu retains its identity until our successful close, another opening, a scope change or real user input.

The fallback never rewrites `material_owned`, sends another block use, closes a foreign GUI, clears a safety lock or waives manual takeover. Failed uses, unmatched request IDs/positions, different menu kinds, worlds, tasks, lease IDs/revisions, expired first openings and later human input are rejected. Inventory transfers still use ordinary clicks and fresh acknowledgement checks.

This is a Python-only change. When the installed baseline is known and no material worker is active, the client and helper can be atomically replaced without restarting Minecraft. Tests cover both ordinary native ownership and the delayed-opening path; actual menu acceptance is separately recorded by the live caller.
