# Projection-locked observer placement

`projected_observer_place_protocol=1` adds an opt-in orientation step to ordinary `interact`. It uses the locked original observer facing, a real visible support face and one normal `gameMode.useItemOn` call. It does not create block results, place in air or change coordinates.

The existing support-state, hand, distance and eye-to-support collision checks remain. The guard runs before rotation and again immediately before input: current guarded material owner, healthy dry survival player, enough food/oxygen, empty cursor, no manual input, original visible/server-loaded observer cell, AIR target, dry full non-container support and no target living entity. The target must equal `support.relative(face)`. It cannot combine terrain/paving operations.

Like a printer placement, the look direction comes from the desired observer facing while the normal clicked face remains independently visible from the actual eye position. Immediately before use, a normal `BlockPlaceContext` must predict the original observer facing. The changing POWERED bit is not an installation direction. The actual 26.2 observer placement implementation uses its nearest looking direction (two opposite transformations cancel); this was also observed as a NORTH placement from the south side. Do not reuse an opposite-direction assumption from another release.

Request additions to normal `interact`:

- `projected_observer_place: true`
- `place_pos: [x,y,z]`, exactly adjacent to normal `pos`/`face`
- `placement_key`: current locked projection key

The executor `projected_observer_place.place(client,target,support,face,key,out)` selects a carried observer, journals the sole request and waits for three current loaded prediction-free frames plus an exact observer inventory decrement. A generic DONE reply means the interaction finished its settling interval; it is not itself a server block-packet acknowledgement. The executor never treats that reply alone as construction success, and never repeats an unknown action.

Validation: candidate host136 Java tests and45 Python tests, including old-host/occupied-cell rejection, waiting for prediction retirement, retaining an uncertain request without retry and preserving the existing water workflows. Live31.8 acceptance installed three SOUTH observers and one DOWN observer through this entry, with three settled frames and exact inventory deltas per cell; existing temporary supports were recovered and27 water sources plus the0..7 bent channel were rechecked afterward. This is component acceptance, not full-farm completion.

Protocol1 has one uniquely identified early rejection: `Target interaction face is occluded or out of reach` is thrown before active rotation or `useItemOn`. The executor requires matching request/world IDs and protocol1 before recording this as no-input and releasing its pending-use marker. It still raises without retry; a different pose must be independently scanned. Other errors/timeouts and post-input failures retain their original pending identity. This prevents a known support-visibility refusal from accidentally leaving a finished controller's heartbeat to expire.
