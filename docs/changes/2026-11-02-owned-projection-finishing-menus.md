# Owned projection finishing menus

Host 2026.11.01.15 extends the already prepared owned Hopper/Dispenser menu fix with two opt-in finishing operations. Engine1.8.44/API3 are unchanged. A full game restart is required; this is not a hot update.

## Blank sign editor

`professional_print` accepts `close_owned_blank_sign: true` only with a current material-owned single-target batch whose schematic goal is a spruce wall sign and actual cell is air. The intent expires after30seconds. Before interface pause handling, normal `screen.onClose()` may close only the matching new sign editor: same request/task/revision/world/connection/batch, expected local placement and printer interaction proposal, exactly one sign consumed, empty cursor/crafting slots, and four exactly empty editor lines. It requires an inactive game window and no manual movement, so focused user interaction and any text, including whitespace, remain untouched. Closing the editor does not confirm placement; normal server placement confirmation still applies. Reflection failure consumes the intent without retrying input. No keyboard events or direct packet construction are used.

## Empty single chest repair

`mine_block` accepts `recover_empty_chest: true`, `tool_slot`, `expected_menu_id`, `expected_content_serial`, and `placement_key`. First normally open the target single chest in the same material task. `empty_chest_recovery` reports a current server content serial and emptiness. Proof expires after30seconds, is consumed before closing the menu, and is never a standalone authorization to break arbitrary containers.

The locked loaded projection must require two correctly facing connected chest halves while both actual halves are matching dry single chests. All27 target slots must be empty in both the observed server content/slot packets and current menu. Cursor and crafting slots must be empty, with a durable hotbar axe, pickup space, at least19 health/18food, no nearby other player, no adjacent fluid or automated hopper/dropper/dispenser. Other excavation exceptions cannot combine with this mode. Surroundings, pair geometry, player and tool are rechecked while mining; ordinary block-update and sequence acknowledgements remain mandatory. The other chest is not opened, emptied or mined by this operation. Replacement is a separate normal placement and requires fresh verification.

## Validation and delivery boundary

The actual candidate jar compiles against the installed26.2 host and1.8.44 engine and passes37 related tests, including real sign-screen field/callback signatures and actual bridge wiring. Full prescribed Gradle tasks stop before compilation because offline Fabric Loom1.17-SNAPSHOT is unavailable. Existing unrelated component-bootstrap test failures were previously reproduced on the unchanged host; they are not counted as passed. No live sign closure or chest break has yet been credited. Candidate builds patch only AutomationBridge, these helpers, the existing owned-added-menu helper, and Fabric version metadata; unrelated BorerThreats bytes stay identical to the installed host.
