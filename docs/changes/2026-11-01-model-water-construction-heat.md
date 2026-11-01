# Original-source bucket construction exceptions

Original planar source repair previously rejected any fire or a small health drop from the action start, even when the existing thermal policy allowed construction. Recent thermal ticks also stopped the otherwise verified shielded workspace.

The original-source mode now accepts explicit boolean options, both off by default:

- `model_water_minor_thermal`: permits known recoverable campfire/hot-floor/fire damage only with health at least 19 and the existing food, lava and underwater checks. A real mob attack within 100 ticks, including one followed by fire, prevents the exception.
- `model_water_remote_calm_creeper`: reuses the existing flow-correction proof only after original model geometry passes. A current loaded, uncharged, occluded and unignited creeper must be below the source and outside both player and source distance margins. Close zombies retain existing checks.

The host advertises `model_water_construction_options_protocol=1`. The worker refuses opt-in calls on older hosts before any selection or bucket use. Ordinary bucket operations retain their prior behavior. Current lease, world, manual input, prediction settlement, durable one-use claim and real block plus inventory server receipts remain required.

This changes host classes and needs a full normal restart. The separately installed engine 1.8.42 and its standby heat ascent are unchanged.

Validation: isolated candidate compiled against installed 26.2 dependencies; 122 Java tests and 50 worker tests passed. Full required offline Gradle check stopped before compilation because Fabric Loom 1.17-SNAPSHOT is absent from the offline cache. Candidate jar comparison permits only the four changed host classes and version metadata, excluding unrelated worktree edits. Installation and live source repair remain separate acceptance steps.

## Worker follow-up from real play

The installed host exception was not enough: the Python idle-injury witness treated two fire ticks, 717ms apart at 19.689→19.533 health, as a stationary unknown injury during bucket selection and logged out before bucket use. Source placement had not dispatched. Two service slabs remain open and are recorded for restoration; the original selection receipt remains unresolved and is not replayed.

An explicit original-source call now carries at most 60 seconds of controller-local construction intent. Only the same world/task/projection with native thermal permission, health >=19 and food >=18 can suppress that idle witness; the original lease, no-hostile, lock and input checks remain. Finally restores the previous intent on failure; expired scopes and all ordinary standby observations retain the previous detection. This worker change is hot deployable. 111 relevant worker tests passed, including the recorded injury and observer integration. It does not clear an existing safety hold or authorize reconnection.
