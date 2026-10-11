package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import java.util.List;
import java.util.function.Function;

/** An isolated stem with all six skin faces needs no orientation or world-state rewriting. */
final class MushroomStemPlacementPolicy {
    static boolean allFaces(BlockState state) {
        var faces=List.of(BlockStateProperties.DOWN,BlockStateProperties.EAST,BlockStateProperties.NORTH,
            BlockStateProperties.SOUTH,BlockStateProperties.UP,BlockStateProperties.WEST);
        return state.is(Blocks.MUSHROOM_STEM)&&state.getProperties().size()==6
            &&faces.stream().allMatch(p->state.hasProperty(p)&&state.getValue(p));
    }
    static boolean isolated(BlockState state,BlockPos target,Function<BlockPos,BlockState> read) {
        return allFaces(state)&&java.util.Arrays.stream(Direction.values())
            .noneMatch(d->read.apply(target.relative(d)).is(state.getBlock()));
    }
}
