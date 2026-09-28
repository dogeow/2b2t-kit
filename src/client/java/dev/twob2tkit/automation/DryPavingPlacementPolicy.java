package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** Opt-in, last-moment guard for one dry Y63 paving placement. */
final class DryPavingPlacementPolicy {
    private DryPavingPlacementPolicy() {}

    interface World {
        boolean loaded(BlockPos pos);
        boolean air(BlockPos pos);
        boolean fluid(BlockPos pos);
        boolean blockEntity(BlockPos pos);
        boolean solid(BlockPos pos);
        boolean ordinaryLeaves(BlockPos pos);
        boolean naturalSupport(BlockPos pos);
        Iterable<Vec3> nearbyEntities(BlockPos destination);
        AABB playerBody();
    }

    static String rejection(World world, BlockPos support, Direction face) {
        if (face != Direction.UP || support.getY() != 62)
            return "Dry paving requires the upper face of a Y62 support";
        BlockPos destination = support.above();
        if (!world.loaded(destination) || !world.air(destination))
            return "Dry paving destination changed or unloaded";
        return surroundingsRejection(world, destination);
    }

    static String surroundingsRejection(World world, BlockPos destination) {
        for (int x = destination.getX() - 1; x <= destination.getX() + 1; x++)
            for (int z = destination.getZ() - 1; z <= destination.getZ() + 1; z++)
                for (int y = 62; y <= 66; y++) {
                    BlockPos pos = new BlockPos(x, y, z);
                    if (!world.loaded(pos) || world.fluid(pos) || world.blockEntity(pos))
                        return "Dry paving neighbor became unloaded, wet, or a block entity";
                    // A low canopy can safely remain above the empty two-block
                    // work column, but it must still be a dry ordinary leaf at
                    // the last possible moment before placing. This method is
                    // called both before and after interaction rotation.
                    if (y == 66 && x == destination.getX() && z == destination.getZ()
                            && !world.air(pos) && !world.ordinaryLeaves(pos))
                        return "Dry paving overhead canopy changed from dry leaves";
                }
        if (!world.naturalSupport(destination.below())
                || !world.air(destination.above()) || !world.air(destination.above(2)))
            return "Dry paving support or destination changed";
        for (Direction side : Direction.Plane.HORIZONTAL)
            for (int y = 63; y <= 64; y++) {
                BlockPos neighbor = new BlockPos(destination.getX() + side.getStepX(), y,
                        destination.getZ() + side.getStepZ());
                if (!world.air(neighbor) && !world.solid(neighbor))
                    return "A nearby non-solid feature may depend on the paving surface";
            }
        if (world.playerBody().intersects(new AABB(destination)))
            return "Player body overlaps the paving destination";
        Vec3 center = Vec3.atCenterOf(destination);
        for (Vec3 entity : world.nearbyEntities(destination))
            if (entity.distanceToSqr(center) <= 16)
                return "An entity approached the paving cell";
        return null;
    }
}
