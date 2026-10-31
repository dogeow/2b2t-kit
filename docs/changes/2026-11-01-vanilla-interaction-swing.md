# Preserve vanilla client swings after ordinary successful use

The mapped Minecraft 26.2 `startUseItem` method calls `LocalPlayer.swing` after a successful interaction whose swing source is CLIENT. Kit's ordinary `interact` called the game-mode use method but omitted that follow-up.

The bridge now makes the same pure decision as vanilla and requests one MAIN_HAND swing in the unchanged current world. PASS, FAIL, empty-hand fallback, server-swing success, consume-only success and null results request no client swing. Existing mutually exclusive useItem/useItemOn branches still execute exactly once; no use fallback, block mutation, health exception or protection bypass is added. Read-only interaction evidence includes `client_swing_requested`, with its existing explicit local-only scope. An animation request is not a server acknowledgement.

Candidate 2026.11.01.12 passes 267 isolated Java tests: real vanilla result constants, mapped client bytecode contract, and compiled bridge one-use/one-swing wiring, plus the existing water/navigation/placement suites. The candidate is patched from the installed host; engine, Mixins, configuration and unrelated worktree changes are excluded. Full host restart is required. This fixes a demonstrated vanilla-behavior omission; whether it explains the observed gate rollback requires live validation and is not claimed by the tests.
