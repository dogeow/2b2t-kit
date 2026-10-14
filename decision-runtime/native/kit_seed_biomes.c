/* Small stdin adapter to the separately built MIT-licensed Cubiomes library.
 * Compile with -fwrapv to preserve Java integer overflow semantics.
 */
#include "generator.h"
#include "util.h"
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    char *end;
    errno = 0;
    uint64_t seed = strtoull(argv[1], &end, 10);
    if (errno || end == argv[1] || *end) return 3;
    int mc = str2mc(argv[2]);
    if (mc <= MC_UNDEF) return 4;
    Generator generator;
    setupGenerator(&generator, mc, 0);
    applySeed(&generator, DIM_OVERWORLD, seed);
    int x, y, z;
    while (scanf("%d %d %d", &x, &y, &z) == 3) {
        int id = getBiomeAt(&generator, 1, x, y, z);
        const char *name = biome2str(mc, id);
        printf("%d %d %d %d %s\n", x, y, z, id, name ? name : "unknown");
    }
    return ferror(stdin) ? 5 : 0;
}
