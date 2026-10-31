# Sealed north-canal wall admission

`material_jobs.canal_seals.plan_seal` performs read-only checks before the verified
natural-obstruction/cobblestone replacement loop. It requires a complete coherent
45-cell frame without pending predictions, original matching cobblestone above
and below, three full dry non-container sides, existing plain water to the north,
and an unobstructed air work body. Only dirt or stone at an original cobblestone
target is eligible. Its work pose includes the observed north offset needed for
the normal visible support-face ray. Pins are the actual six neighboring states.

Original air below the target is an explicit skip, not a missing dictionary key.
Existing correct blocks and protected unknown targets are never proposed again.
Gates, partial/open sides, containers, other fluids and blocked work bodies are
kept unchanged. This planner does not send movement or block interactions; the
caller still uses the native owned health/manual/sequence/placement checks and
must verify current state again before input and restore service hatches.

Seven Python tests passed. Pure replay of four independently confirmed real
repairs admitted them; the original-air bottom at X761422 was correctly skipped.
Recorded replay sends no game input. Python-only module, no host restart needed.
