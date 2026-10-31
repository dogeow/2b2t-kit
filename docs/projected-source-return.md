# Returning collected water to an unchanged original source chamber

Native protocol `projected_source_return_protocol=1` is an exclusive `bucket_place`
mode with `projected_source_return: true`. It requires a middle source inside an
original completed nine-row or explicit four-row source chamber, all existing
boundary pins and original sources, exact completed overflow levels 2/1/0, and an
adjacent original inert glass/cobblestone support. No container support is allowed.
Ownership, health, UI, manual takeover, real ray, reach, entity and durable claims
remain in the ordinary bucket path. Other modes keep their current semantics.

The operation sends exactly one normal BucketItem use. Returning water to an
already identical source may produce no block-change packet. After that single
use, the transformed empty bucket performs one normal inert support-block use,
with no item-use fallback. Vanilla replies to block interactions with real support
and adjacent block updates. This supplies an actual current-connection source
packet; it does not synthesize an acknowledgement or mutate the source directly.
The original selected-slot empty-bucket packet is independently required. Missing
packets remain pending and the original water use is never repeated.

The probe only accepts the original visible inert face and one empty bucket.
`projected_source_return.py` then verifies the unchanged source envelope in three
coherent frames and the exact water/empty-bucket delta. It has no retry loop.

Validation: 222 related Java tests and 5 new Python tests passed. Tests also inspect
actual local vanilla behavior: existing water is replaceable, empty-bucket block
use is PASS, and the server handler emits support and adjacent block updates.
This is candidate validation; installation and real-server acceptance are separate.
