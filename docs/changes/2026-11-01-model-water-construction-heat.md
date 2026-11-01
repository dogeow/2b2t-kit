# Original-source bucket construction exceptions

Original planar source repair previously rejected any fire or a small health drop from the action start, even when the existing thermal policy allowed construction. Recent thermal ticks also stopped the otherwise verified shielded workspace.

The original-source mode now accepts explicit boolean options, both off by default:

- `model_water_minor_thermal`: permits known recoverable campfire/hot-floor/fire damage only with health at least 19 and the existing food, lava and underwater checks. A real mob attack within 100 ticks, including one followed by fire, prevents the exception.
- `model_water_remote_calm_creeper`: reuses the existing flow-correction proof only after original model geometry passes. A current loaded, uncharged, occluded and unignited creeper must be below the source and outside both player and source distance margins. Close zombies retain existing checks.

The host advertises `model_water_construction_options_protocol=1`. The worker refuses opt-in calls on older hosts before any selection or bucket use. Ordinary bucket operations retain their prior behavior. Current lease, world, manual input, prediction settlement, durable one-use claim and real block plus inventory server receipts remain required.

This changes host classes and needs a full normal restart. The separately installed engine 1.8.42 and its standby heat ascent are unchanged.

Validation: isolated candidate compiled against installed 26.2 dependencies; 122 Java tests and 50 worker tests passed. Full required offline Gradle check stopped before compilation because Fabric Loom 1.17-SNAPSHOT is absent from the offline cache. Candidate jar comparison permits only the four changed host classes and version metadata, excluding unrelated worktree edits. Installation and live source repair remain separate acceptance steps.
