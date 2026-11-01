# Scoped normal Minecraft gate input

Ordinary useItemOn, vanilla follow-up swing, and a side-face click all changed the local gate prediction but did not preserve the requested state. This opt-in path tests the actual normal Minecraft client input entrypoint instead of adding further direct interaction variants.

`interact` with `vanilla_block_input=true` requires the current guarded healthy dry material owner, the real player camera, an empty cursor/inventory menu, no mining/hands-busy/item-use state, and no physical mouse takeover. Only diamond/netherite swords with empty/totem offhand are allowed. The locked visible original model must require the exact same fence gate open, and the actual player direction's single vanilla open transition must reach that full goal state. Placement/mining exceptions and consumptive items are excluded.

The path resolves the real mapped `Minecraft.pick(float)` and `startUseItem()` methods, checks normal right-click delay, recomputes the actual vanilla crosshair including entities, and invokes the input handler exactly once only for the expected block and face. It never sets a fake hit result, sends synthetic packets, performs direct useItem/useItemOn fallback, or adds another swing; vanilla owns its ordinary hand fallback and swing. Method lookup failures are normal errors, not static-initializer crashes.

Read-only evidence records whether the handler was invoked and returned, including preflight rejection. The void handler has no invented consumed-result or client-swing boolean. Current mining/hands/item-use flags are exposed in snapshots. Client evidence still does not claim server acceptance; actual world and post-rejoin checks remain required. Old operations and unknown water claims are unchanged.

Candidate 2026.11.01.13 passes 273 isolated Java tests, covering exact one-click gate transitions, exclusive types, malformed flags, all standard busy combinations, actual vanilla method signatures, no direct-use/world-mutation fallback and no-owner rejection. Engine, Mixins and unrelated worktree changes are excluded from the installed-host patch. Full host restart is required; live acceptance is separate.
