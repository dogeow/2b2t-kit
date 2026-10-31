# Observe ordinary block-use results without changing interaction behavior

A normal `interact` command reached its existing settled `done` state, while a fence gate's expected state was not observed afterward. Command completion alone does not prove that vanilla consumed the click or that the server accepted a block change.

The host now exposes `block_interaction_observation_protocol=1` and request/world-scoped `last_block_interaction` evidence. It records the selected hand and slot, requested block state before and immediately after the local call, actual hit face and player direction, secondary-use state, physical sneak key, forced placement sneak, build ability, and the actual returned interaction result. A null result remains unknown, rather than becoming a fabricated PASS. Current sneak/build flags are also available in passive snapshots.

The observation explicitly has `local_client_call_only_not_server_confirmation` scope. It does not repeat an interaction, change input, loosen protection, mutate blocks, create packets, or alter the existing command lifecycle. Boat item use and ordinary block use retain their original mutually exclusive single calls. Old unknown operations stay unchanged.

Candidate 2026.11.01.11 passes 264 isolated Java tests, including the actual bridge wiring, one-call counts, immutable target evidence, PASS/consumed/null semantics, and distinction between physical sneak and forced secondary use. The patch is built from the installed host and changes only the observation class, bridge (including compiler-generated nested classes), and version metadata. Runtime engine and Mixins remain unchanged. A full host restart is required; live observation is recorded separately in the work checkpoint.
