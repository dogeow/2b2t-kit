package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;

/** The same bounded observation must remain true throughout an opt-in paving excavation. */
final class DryPavingMiningPolicy {
    private DryPavingMiningPolicy() {}

    interface World extends DryPavingPlacementPolicy.World {
        String state(BlockPos pos);
        boolean naturalSurface(BlockPos pos);
        boolean playerStandingOn(BlockPos pos);
    }

    static String rejection(World world, BlockPos target, String expectedState) {
        if (target.getY() != 63 || !world.loaded(target)
                || !expectedState.equals(world.state(target))
                || !world.naturalSurface(target) || !world.solid(target))
            return "Dry paving mining target is no longer the exact Y63 natural surface";
        if (world.playerStandingOn(target))
            return "Player is standing on the paving excavation";
        return DryPavingPlacementPolicy.surroundingsRejection(world, target);
    }
}
