package dev.twob2tkit.planter;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.CropBlock;
import net.minecraft.world.level.block.PitcherCropBlock;
import net.minecraft.world.level.block.TorchflowerCropBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.IntegerProperty;

import java.util.HashSet;
import java.util.Set;
import java.util.function.BooleanSupplier;
import java.util.function.Function;

/** A maintenance session owns only soil that was already farmland when it began. */
public final class PlanterFieldBoundary {
    private final Set<BlockPos> soils;

    private PlanterFieldBoundary(Set<BlockPos> soils) {
        this.soils = Set.copyOf(soils);
    }

    public static PlanterFieldBoundary empty() {
        return new PlanterFieldBoundary(Set.of());
    }

    public static PlanterFieldBoundary capture(Iterable<BlockPos> candidates,
                                               Function<BlockPos, BlockState> read) {
        Set<BlockPos> farmland = new HashSet<>();
        for (BlockPos soil : candidates) {
            BlockState state = read.apply(soil);
            if (state != null && state.is(Blocks.FARMLAND)) farmland.add(soil.immutable());
        }
        return new PlanterFieldBoundary(farmland);
    }

    public int size() {
        return soils.size();
    }

    public static boolean supports(Block plant) {
        return plant instanceof CropBlock || plant instanceof PitcherCropBlock
            || plant instanceof TorchflowerCropBlock;
    }

    private boolean existingSoil(BlockPos crop, Function<BlockPos, BlockState> read) {
        BlockPos soil = crop.below();
        if (!soils.contains(soil)) return false;
        BlockState current = read.apply(soil);
        return current != null && current.is(Blocks.FARMLAND) && current.getFluidState().isEmpty();
    }

    public boolean canPlant(BlockPos crop, Block plant, Function<BlockPos, BlockState> read) {
        if (!supports(plant) || !existingSoil(crop, read)) return false;
        BlockState space = read.apply(crop);
        return space != null && space.isAir();
    }

    public boolean canHarvest(BlockPos crop, Block plant, Function<BlockPos, BlockState> read) {
        if (!supports(plant) || !existingSoil(crop, read)) return false;
        BlockState current = read.apply(crop);
        if (current == null || !(current.is(plant)
                || plant instanceof TorchflowerCropBlock && current.is(Blocks.TORCHFLOWER))) return false;
        if (current.getBlock() instanceof CropBlock ordinary) return ordinary.isMaxAge(current);
        if (current.is(Blocks.TORCHFLOWER)) return true;
        if (current.getBlock() instanceof PitcherCropBlock) {
            for (var property : current.getProperties()) {
                if (property instanceof IntegerProperty age && property.getName().equals("age")) {
                    return current.getValue(age) >= 4;
                }
            }
        }
        return false;
    }

    /** Recheck after selection/aiming and immediately before the real interaction. */
    public boolean plantIfCurrent(BlockPos crop, Block plant, Function<BlockPos, BlockState> read,
                                  BooleanSupplier finalChecks, BooleanSupplier interact) {
        if (!canPlant(crop, plant, read) || !finalChecks.getAsBoolean()) return false;
        return canPlant(crop, plant, read) && interact.getAsBoolean();
    }
}
