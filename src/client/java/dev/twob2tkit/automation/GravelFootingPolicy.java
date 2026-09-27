package dev.twob2tkit.automation;

import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.FallingBlock;

/** The only supported exception to the normal rule that protects the block under the player. */
final class GravelFootingPolicy {
    private GravelFootingPolicy() {}

    static boolean stableFloor(ClientLevel level, BlockPos gravel) {
        BlockPos below=gravel.below();
        if(!level.hasChunkAt(below))return false;
        var state=level.getBlockState(below);
        return state.getFluidState().isEmpty() && !(state.getBlock() instanceof FallingBlock)
            && state.isCollisionShapeFullBlock(level,below);
    }

    static boolean mayStand(boolean fullStableFloor, boolean clearWaterColumn,
                            double horizontal, double drop, int air, int pickupFloor) {
        return fullStableFloor && clearWaterColumn && horizontal <= 1.25
            && drop >= .5 && drop <= 5 && air >= pickupFloor;
    }

    static boolean mayMineUnderfoot(boolean ownedMaterialTask, boolean underwaterGravel,
                                     boolean fullStableFloor, boolean feetOnTarget,
                                     boolean underwater, float health, int air, int workFloor) {
        return ownedMaterialTask && underwaterGravel && fullStableFloor && feetOnTarget
            && underwater && health >= 19 && air >= workFloor;
    }
}
