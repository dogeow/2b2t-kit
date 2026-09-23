package dev.twob2tkit;

import dev.twob2tkit.cruise.CruiseCollisionPath;
import net.minecraft.world.phys.AABB;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Regression for a verified clear horizontal exit under a low rocket roof. */
final class CruiseCollisionPathTest {
    @Test
    void horizontalExitDoesNotMistakeTouchingRoofOrSideWallForCollision() {
        AABB player = new AABB(815.0, 84.2, 764.2, 815.6, 86.0, 764.8);
        AABB roof = new AABB(815.0, 86.0, 764.0, 819.0, 87.0, 765.0);
        AABB sideWall = new AABB(814.0, 83.0, 764.0, 815.0, 86.0, 765.0);
        AABB swept = CruiseCollisionPath.horizontal(player, 3.2, 0);

        assertFalse(swept.intersects(roof));
        assertFalse(swept.intersects(sideWall));
        assertTrue(CruiseCollisionPath.vertical(player, 16.0).intersects(roof));
    }

    @Test
    void sweptExitStillDetectsARealWallBetweenEndpoints() {
        AABB player = new AABB(815.0, 84.2, 764.2, 815.6, 86.0, 764.8);
        AABB wallAhead = new AABB(817.0, 84.0, 764.0, 818.0, 86.0, 765.0);
        assertTrue(CruiseCollisionPath.horizontal(player, 3.2, 0).intersects(wallAhead));
    }
}
