# User-provided generation seed and bounded resource hints

The user supplied seed `1009504104802950675` and generation version `1.19.3`.
The full seed hashes to the current login hash `-2531438672007079198`.
All 169 loaded native biome samples matched both neighboring Cubiomes tables.
This supersedes the old saved seed, whose surface calibration matched 0/5.

`decision-runtime/versioned_biome_hints.py` now provides offline `calibrate` and
`search` commands. Full decimal seeds remain strings until conversion to a
64-bit integer. The requested terrain generation version is independent of the
current client version. Unsupported versions fail instead of substituting it.

Cubiomes currently exposes separate 1.19.2 and 1.19.4 table selectors. For the
1.19.3 request, the adapter compares both against actual XYZ samples and emits
only hints on which both agree. This is explicitly a compatibility check, not a
claim that a separate 1.19.3 generator was run. The upstream tree converter
documents the order-six tree as used by 1.19.3–1.20. Primary source:
https://github.com/Cubitect/cubiomes, pinned revision
`e61f90580cbdd883214a8054670dacae655e59c0`.

Build the standalone adapter against that library with `-O3 -fwrapv`, including
its headers and linking `libcubiomes.a -lm`. The retained adapter source is
`decision-runtime/native/kit_seed_biomes.c`. Pass the resulting executable with
`--generator`; no game restart or model/network call is used by either command.

Calibration requires a scoped successful native survey, consistent counts,
distinct valid positions, a matching login seed hash, at least two actual land
biomes, and complete agreement. Search requires that evidence, checks both
tables, applies the configured world boundary with a 32-block margin, and emits
at most 16 separated candidates. No material or construction credit is given.
Every candidate still needs actual loaded terrain and plant/block verification
before any harvest.

Current evidence is in `work/live-20261004/versioned-seed-calibration-586.json`
and `versioned-desert-hints-587.json`. The nearest predicted desert is
X755123 Z792335, 6700.2 blocks from the fresh survey origin. A single native
material actor is flying there with finite legs and opportunistic live plant
surveys. Actual desert/cactus acceptance is still pending at this writing.

Eight focused tests cover full seed precision, the known login hash, version
disagreement, wrong/unknown seed, ocean-only matches, incomplete/unscoped scans,
duplicate positions, unsupported generation versions, world bounds, omitted
generator responses, and zero inventory credit. The CLI was also run against
the compiled pinned Cubiomes library and the 169 actual native samples.
