# Portable-box drop catch floor

Material withdrawal and exact equipment batches now require a complete flat dry 3x3 surface beneath the temporary box. A single supported cell, an exposed edge, bottom/wet slabs, falling blocks, containers and hazardous blocks are rejected before opening the Ender chest. Existing exact center-support and empty pad/headroom requirements remain in force.

The nine observed ground states are recorded in `drop_catch_floor`. They must still match before box placement and immediately before requesting recovery mining. A changed floor leaves the box intact in its last verified location. This check does not build a platform, remove obstructions, or weaken existing ownership, inventory conservation, drop UUID, pickup-content or original-slot return checks.

This is a catch-surface admission check, not proof that pickup or return succeeded. Other entities and subsequent world changes can still move items. The workflow must retain its original journal until actual carried contents and the original Ender slot are confirmed. Legacy incomplete journals must not be marked returned or replayed by this patch.

Verification: `python -m unittest discover -s decision-runtime -p 'test_packed*.py'`. Includes the single-cell incident shape, missing corners, wet/hazardous/low ground, pre-withdrawal refusal and ground removal after tool selection. No actual player assets are used in these tests. Python worker updates apply to subsequent worker processes without restarting Minecraft.
