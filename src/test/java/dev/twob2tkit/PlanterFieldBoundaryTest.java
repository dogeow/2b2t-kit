package dev.twob2tkit;

import dev.twob2tkit.planter.PlanterFieldBoundary;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.CropBlock;
import net.minecraft.world.level.block.state.BlockState;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class PlanterFieldBoundaryTest {
    @BeforeAll static void bootstrap() {
        net.minecraft.SharedConstants.tryDetectVersion();
        net.minecraft.server.Bootstrap.bootStrap();
    }

    static final class Field {
        final Map<BlockPos, BlockState> world = new HashMap<>();
        final List<BlockPos> observed = new ArrayList<>();
        final List<BlockPos> planted = new ArrayList<>();
        BlockState read(BlockPos pos) { return world.getOrDefault(pos, Blocks.AIR.defaultBlockState()); }
        void soil(BlockPos pos, Block block) { world.put(pos, block.defaultBlockState()); observed.add(pos); }
        boolean plant(BlockPos crop) { planted.add(crop); world.put(crop, Blocks.WHEAT.defaultBlockState()); return true; }
    }

    @Test void existingFiveByFiveFieldDoesNotTillOrPlantSurroundingGrassDirtAndDecorativeBlocks() {
        Field field = new Field();
        for (int x = -3; x <= 3; x++) for (int z = -3; z <= 3; z++) {
            Block soil = Math.abs(x) <= 2 && Math.abs(z) <= 2 ? Blocks.FARMLAND
                : (x + z) % 2 == 0 ? Blocks.GRASS_BLOCK : Blocks.DIRT;
            if (x == 0 && z == 0) soil = Blocks.WATER;
            field.soil(new BlockPos(x, 64, z), soil);
        }
        field.world.put(new BlockPos(3, 64, 1), Blocks.POLISHED_ANDESITE.defaultBlockState());
        Map<BlockPos, BlockState> before = new HashMap<>(field.world);
        PlanterFieldBoundary boundary = PlanterFieldBoundary.capture(field.observed, field::read);
        assertEquals(24, boundary.size());
        for (BlockPos soil : field.observed) {
            BlockPos crop = soil.above();
            boundary.plantIfCurrent(crop, Blocks.WHEAT, field::read, () -> true, () -> field.plant(crop));
        }
        assertEquals(24, field.planted.size());
        assertTrue(field.planted.stream().allMatch(p -> Math.abs(p.getX()) <= 2 && Math.abs(p.getZ()) <= 2));
        for (var entry : before.entrySet()) assertEquals(entry.getValue(), field.read(entry.getKey()), "Soil must never be hoed");
        for (BlockPos soil : field.observed) if (!before.get(soil).is(Blocks.FARMLAND)) assertTrue(field.read(soil.above()).isAir());
    }

    @Test void newlyTilledOrPreviouslyUnobservedFarmlandCannotExpandTheSessionBoundary() {
        Field field = new Field();
        BlockPos original = new BlockPos(0, 64, 0), ordinary = new BlockPos(1, 64, 0), outside = new BlockPos(3, 64, 0);
        field.soil(original, Blocks.FARMLAND);field.soil(ordinary, Blocks.GRASS_BLOCK);
        field.world.put(outside, Blocks.FARMLAND.defaultBlockState());
        PlanterFieldBoundary boundary = PlanterFieldBoundary.capture(field.observed, field::read);
        field.world.put(ordinary, Blocks.FARMLAND.defaultBlockState());
        assertTrue(boundary.canPlant(original.above(), Blocks.WHEAT, field::read));
        assertFalse(boundary.plantIfCurrent(ordinary.above(), Blocks.WHEAT, field::read, () -> true, () -> field.plant(ordinary.above())));
        assertFalse(boundary.plantIfCurrent(outside.above(), Blocks.WHEAT, field::read, () -> true, () -> field.plant(outside.above())));
        assertTrue(field.planted.isEmpty());
    }

    @Test void soilChangedBetweenScanAndInteractionCancelsTheRealPlantCallback() {
        for (Block changed : List.of(Blocks.GRASS_BLOCK, Blocks.DIRT, Blocks.DIRT_PATH, Blocks.STONE, Blocks.WATER)) {
            Field field = new Field();BlockPos soil = new BlockPos(0, 64, 0), crop = soil.above();
            field.soil(soil, Blocks.FARMLAND);
            PlanterFieldBoundary boundary = PlanterFieldBoundary.capture(field.observed, field::read);
            assertTrue(boundary.canPlant(crop, Blocks.WHEAT, field::read));
            AtomicInteger clicks = new AtomicInteger();
            boolean acted = boundary.plantIfCurrent(crop, Blocks.WHEAT, field::read,
                () -> { field.world.put(soil, changed.defaultBlockState()); return true; },
                () -> { clicks.incrementAndGet(); return field.plant(crop); });
            assertFalse(acted);assertEquals(0, clicks.get());assertTrue(field.read(crop).isAir());
            assertTrue(field.read(soil).is(changed));
        }
    }

    @Test void matureCropOrDecorationAppearingAfterSelectionIsPreserved() {
        CropBlock wheat = (CropBlock)Blocks.WHEAT;
        for (BlockState occupied : List.of(wheat.getStateForAge(wheat.getMaxAge()),
                Blocks.POPPY.defaultBlockState(), Blocks.SHORT_GRASS.defaultBlockState(), Blocks.CHEST.defaultBlockState())) {
            Field field = new Field();BlockPos soil = new BlockPos(0, 64, 0), crop = soil.above();
            field.soil(soil, Blocks.FARMLAND);
            PlanterFieldBoundary boundary = PlanterFieldBoundary.capture(field.observed, field::read);
            assertFalse(boundary.plantIfCurrent(crop, Blocks.WHEAT, field::read,
                () -> { field.world.put(crop, occupied); return true; }, () -> field.plant(crop)));
            assertEquals(occupied, field.read(crop));assertTrue(field.planted.isEmpty());
        }
    }

    @Test void matureBoundaryCropOnGrassOrOutsideObservedFieldIsNeverHarvestable() {
        Field field = new Field();BlockPos owned = new BlockPos(0, 64, 0), grass = new BlockPos(1, 64, 0), outside = new BlockPos(3, 64, 0);
        field.soil(owned, Blocks.FARMLAND);field.soil(grass, Blocks.GRASS_BLOCK);
        field.world.put(outside, Blocks.FARMLAND.defaultBlockState());
        CropBlock wheat = (CropBlock)Blocks.WHEAT;
        for (BlockPos soil : List.of(owned, grass, outside)) field.world.put(soil.above(), wheat.getStateForAge(wheat.getMaxAge()));
        PlanterFieldBoundary boundary = PlanterFieldBoundary.capture(field.observed, field::read);
        assertTrue(boundary.canHarvest(owned.above(), Blocks.WHEAT, field::read));
        assertFalse(boundary.canHarvest(grass.above(), Blocks.WHEAT, field::read));
        assertFalse(boundary.canHarvest(outside.above(), Blocks.WHEAT, field::read));
        field.world.put(owned, Blocks.DIRT.defaultBlockState());
        assertFalse(boundary.canHarvest(owned.above(), Blocks.WHEAT, field::read));
        assertTrue(wheat.isMaxAge(field.read(owned.above())));
    }

    @Test void cropCompatibilityNeverAuthorizesOrdinaryGroundOrSpecialPlantExpansion() {
        Field field = new Field();BlockPos soil = new BlockPos(0, 64, 0);field.soil(soil, Blocks.FARMLAND);
        PlanterFieldBoundary boundary = PlanterFieldBoundary.capture(field.observed, field::read);
        for (Block crop : List.of(Blocks.BAMBOO, Blocks.SUGAR_CANE, Blocks.SWEET_BERRY_BUSH,
                Blocks.CACTUS, Blocks.KELP, Blocks.NETHER_WART, Blocks.COCOA)) {
            assertFalse(boundary.plantIfCurrent(soil.above(), crop, field::read, () -> true, () -> field.plant(soil.above())));
        }
        assertTrue(field.planted.isEmpty());
    }
}
