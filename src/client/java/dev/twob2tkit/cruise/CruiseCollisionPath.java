package dev.twob2tkit.cruise;

import net.minecraft.world.phys.AABB;

/** The player's real collision envelope swept along a proposed flight step. */
public final class CruiseCollisionPath {
    private CruiseCollisionPath() {}

    public static AABB horizontal(AABB body, double dx, double dz) {
        return body.expandTowards(dx, 0.0, dz);
    }

    public static AABB vertical(AABB body, double dy) {
        return body.expandTowards(0.0, dy, 0.0);
    }
}
