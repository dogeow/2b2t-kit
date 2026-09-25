# Dry sand collection for Starship

`surface_sand_harvest.py` is a bounded, guarded land-quarry runner. It requires
a fresh four-chest audit proving all 836 gravel before it claims game control.
This keeps the agreed material order: finish gravel, then collect sand, then
craft/concrete/build. The old 114-sand chest snapshot is not current stock.

Run only after an in-game scan has identified a **dry, unbuilt** 32×16×32 or
smaller patch at least 96 blocks from the Starship footprint. Park coordinates
must be above that patch and at least 25 blocks above its highest target. The
player must be within 480 horizontal blocks, healthy, guarded, and carrying a
diamond shovel with enough durability. The command itself validates the audit,
current world session, selected projection, safety lease, and inventory.

```sh
/usr/bin/python3 decision-runtime/surface_sand_harvest.py \
  --region MIN_X MIN_Y MIN_Z MAX_X MAX_Y MAX_Z \
  --site-center STARSHIP_X STARSHIP_Z \
  --park-high PARK_X PARK_Y PARK_Z \
  --gravel-audit /absolute/path/to/fresh-four-chest-audit.json \
  --target-carried 722 \
  --out /absolute/path/to/sand-run
```

The runner scans the patch once, then only a 7×6×7 neighborhood around each
candidate. It mines exposed sand from above, keeps a three-block water and
block-entity buffer, avoids the player's footing, and uses a direct native
mine call when close enough. An exact pre-dispatch out-of-reach response may
trigger one verified approach; ambiguous mine results are never replayed. A
server-confirmed break must yield an observed sand inventory increase before
the next block. It stops when the requested carried amount is reached, the
backpack cannot take another sand block, or no safe sand remains in the patch.
Each result records the actual inventory gain, not a count of attempted breaks.

This runner does **not** deposit sand or discover the next patch. The next
stage must use an approved chest and re-audit its capacity before transfer.
Do not infer 722 collected from an old stock snapshot or from a planned route.
It has Python simulation coverage but has not been validated against live
Simpcraft quarry terrain or server timing. First field run should be bounded
to a few blocks and inspected before allowing the full 722-carried target.
