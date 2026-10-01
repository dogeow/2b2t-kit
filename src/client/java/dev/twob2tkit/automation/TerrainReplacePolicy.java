package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.Set;

/** Four guarded, server-confirmed steps for restoring dirt under an existing grass surface. */
final class TerrainReplacePolicy {
    private TerrainReplacePolicy() {}
    private static final Set<Integer> FIRST_PHASE_X = Set.of(
        760988,760993,760994,760995,760996,760997,760998,760999,761003,761008);

    enum Stage { LIFT_GRASS, MINE_STONE, PLACE_DIRT, RESTORE_GRASS }

    static boolean scopeValid(String requestedWorld, String currentWorld, long expectedRevision,
                              long currentRevision, boolean miningContinuation, long expiresAt, long now) {
        return requestedWorld.equals(currentWorld) && expectedRevision >= 0
            && currentRevision == expectedRevision + (miningContinuation ? 1 : 0)
            && (miningContinuation || expiresAt >= now && expiresAt - now <= 15000);
    }

    interface World {
        boolean loaded(BlockPos pos);
        boolean air(BlockPos pos);
        boolean solid(BlockPos pos);
        boolean fluid(BlockPos pos);
        boolean blockEntity(BlockPos pos);
        String state(BlockPos pos);
        boolean selectedDirtAndGrassColumn(BlockPos pos, String placementKey);
        Iterable<AABB> nearbyEntityBoxes(BlockPos pos);
        AABB playerBody();
        Vec3 playerPosition();
        double playerEyeY();
        boolean standingPose();
        boolean guardedFlight();
        boolean silkShovelReady();
        boolean pickReady();
        boolean dirtReady();
        boolean grassReady();
    }

    static String rejection(World world, BlockPos target, Stage stage, String placementKey,
                            String expectedSurface, String expectedBelow, String expectedAction) {
        if (target.getY() != 62 || target.getZ() != 797865 || !FIRST_PHASE_X.contains(target.getX())
                || placementKey.isBlank()
                || !world.selectedDirtAndGrassColumn(target, placementKey))
            return "Terrain replacement is outside the ten approved south-edge dirt-and-grass columns";
        BlockPos surface = target.above(), below = target.below();
        if (!world.loaded(target) || !world.loaded(surface) || !world.loaded(below))
            return "Terrain replacement column is unloaded";
        if (expectedSurface.isBlank() || !expectedSurface.startsWith("Block{minecraft:grass_block}")
                || !"Block{minecraft:stone}".equals(expectedBelow)
                || !expectedBelow.equals(world.state(below))
                || !world.solid(below))
            return "Terrain replacement surface or foundation changed";
        String targetState = world.state(target), surfaceState = world.state(surface);
        boolean statesMatch = switch (stage) {
            case LIFT_GRASS -> "Block{minecraft:stone}".equals(targetState)
                && expectedSurface.equals(expectedAction) && expectedSurface.equals(surfaceState)
                && world.solid(target) && world.solid(surface);
            case MINE_STONE -> "Block{minecraft:stone}".equals(targetState)
                && targetState.equals(expectedAction) && world.solid(target) && world.air(surface);
            case PLACE_DIRT -> expectedBelow.equals(expectedAction) && world.air(target) && world.air(surface);
            case RESTORE_GRASS -> targetState.equals(expectedAction)
                && ("Block{minecraft:dirt}".equals(targetState)
                    || targetState.startsWith("Block{minecraft:grass_block}"))
                && world.solid(target) && world.air(surface);
        };
        if (!statesMatch)return "Terrain replacement stage no longer matches confirmed stone, dirt, grass or air";
        for (int x = target.getX() - 1; x <= target.getX() + 1; x++)
            for (int z = target.getZ() - 1; z <= target.getZ() + 1; z++)
                for (int y = 61; y <= 66; y++) {
                    BlockPos neighbor = new BlockPos(x, y, z);
                    if (!world.loaded(neighbor) || world.fluid(neighbor) || world.blockEntity(neighbor))
                        return "Terrain replacement neighbor is unloaded, wet, or a block entity";
                }
        for (int y = 64; y <= 66; y++)
            if (!world.air(new BlockPos(target.getX(),y,target.getZ())))
                return "Terrain replacement flight column is obstructed";
        for (Direction side : Direction.Plane.HORIZONTAL)
            for (int y = 62; y <= 63; y++) {
                BlockPos neighbor = new BlockPos(target.getX() + side.getStepX(),y,
                    target.getZ() + side.getStepZ());
                if (!world.air(neighbor) && !world.solid(neighbor))
                    return "A nearby non-solid feature may be attached to the terrain column";
            }
        Vec3 player = world.playerPosition();
        if (!world.guardedFlight() || !world.standingPose()
                || Math.abs(player.x - target.getX() - .5) > .2
                || Math.abs(player.z - target.getZ() - .5) > .2
                || player.y < 64.08 || player.y > 64.50
                || world.playerEyeY() < 65.40 || world.playerEyeY() > 66.20)
            return "Terrain replacement requires guarded flight above the exact column";
        if (world.playerBody().intersects(new AABB(target))
                || world.playerBody().intersects(new AABB(surface)))
            return "Player body overlaps the terrain replacement column";
        AABB protectedArea = new AABB(surface).inflate(4);
        for (AABB entity : world.nearbyEntityBoxes(surface))
            if (entity.intersects(protectedArea))
                return "An entity or loose item approached the terrain replacement";
        boolean supplyReady = switch (stage) {
            case LIFT_GRASS -> world.silkShovelReady();
            case MINE_STONE -> world.pickReady();
            case PLACE_DIRT -> world.dirtReady();
            case RESTORE_GRASS -> world.grassReady();
        };
        if (!supplyReady)return "Selected terrain replacement tool or material changed";
        return null;
    }
}
