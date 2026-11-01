# Batch white wool from existing materials

The villa XP farm needs108 white carpets. Add only the installed26.2 ordinary recipes for white wool from four string and for recoloring nonwhite wool with white dye. Exact recipe id, shape, output quantity, real integer slots and valid color input remain mandatory; white-on-white dye and wrong materials stay rejected. Both reuse existing grouped distribution and capacity/conservation checks. No animals are recolored or killed.

Forty-seven related tests pass, including recipe-catalog checks against the actual26.2 data, one-stack string distribution, dye/wool balance, trapdoors, carpets, storage, cobblestone shapes and portion frames. This Python-only hot update requires no restart. In-game conversion still needs its own inventory receipt.
