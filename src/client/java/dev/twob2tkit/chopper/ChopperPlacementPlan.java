package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import java.util.function.Function;

/** Resolve vanilla's actual destination before sending a single placement. */
final class ChopperPlacementPlan {
    static BlockHitResult choose(BlockPos target, Function<BlockHitResult, BlockPos> destination) {
        for (Direction side : Direction.values()) {
            var hit = new BlockHitResult(Vec3.atCenterOf(target).add(side.getStepX()*.5,
                side.getStepY()*.5, side.getStepZ()*.5), side.getOpposite(), target.relative(side), false);
            if (target.equals(destination.apply(hit))) return hit;
        }
        // The same ordinary Air Place interaction, aimed at the requested cell itself.
        var air = new BlockHitResult(Vec3.atCenterOf(target), Direction.DOWN, target, false);
        return target.equals(destination.apply(air)) ? air : null;
    }
}
