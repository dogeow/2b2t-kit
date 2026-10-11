package dev.twob2tkit.planter;

import com.google.gson.JsonObject;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

/** A material visit is bounded to explicit mature crops, with one replant use per crop. */
public final class PlanterMaterialBatch {
    private final Set<BlockPos> crops;
    private final Set<BlockPos> harvestSent = new LinkedHashSet<>(), removed = new LinkedHashSet<>();
    private final Set<BlockPos> plantSent = new LinkedHashSet<>(), restored = new LinkedHashSet<>();
    private final int grainBefore;

    public PlanterMaterialBatch(Collection<BlockPos> soils, int grainBefore) {
        if (soils.isEmpty() || soils.size() > 16 || grainBefore < 0)
            throw new IllegalArgumentException("One to sixteen explicit mature wheat cells required");
        crops = new LinkedHashSet<>();
        for (BlockPos soil : soils) if (!crops.add(soil.above().immutable()))
            throw new IllegalArgumentException("Duplicate wheat cell");
        this.grainBefore = grainBefore;
    }

    public Set<BlockPos> crops() { return Set.copyOf(crops); }
    public boolean mayHarvest(BlockPos crop) { return crops.contains(crop) && !harvestSent.contains(crop); }
    public boolean mayPlant(BlockPos crop) { return removed.contains(crop) && !plantSent.contains(crop); }
    public void harvestSent(BlockPos crop) {
        if (!mayHarvest(crop)) throw new IllegalStateException("No repeated mature-crop break");
        harvestSent.add(crop.immutable());
    }
    public void plantSent(BlockPos crop) {
        if (!mayPlant(crop)) throw new IllegalStateException("No repeated seed use or planting before removal acknowledgement");
        plantSent.add(crop.immutable());
    }
    /** Only the current vanilla connection's applied block packets may acknowledge actions. */
    public void serverBlock(BlockPos crop, BlockState state, boolean applied) {
        if (!applied || !crops.contains(crop)) return;
        if (harvestSent.contains(crop) && !plantSent.contains(crop) && state.isAir()) removed.add(crop.immutable());
        if (plantSent.contains(crop) && state.is(Blocks.WHEAT)) restored.add(crop.immutable());
    }
    public boolean hasUnacknowledgedAction() {
        return !removed.containsAll(harvestSent) || !restored.containsAll(plantSent);
    }
    public boolean cellsConfirmed() { return restored.containsAll(crops); }
    public boolean done(int grain, int seeds) { return cellsConfirmed() && grain >= grainBefore + crops.size() && seeds >= 4; }
    public boolean currentCrops(Collection<BlockState> states) {
        return states.size() == crops.size() && states.stream().allMatch(s -> s.is(Blocks.WHEAT));
    }
    public JsonObject snapshot() {
        var result = new JsonObject(); result.addProperty("protocol", 1);
        result.addProperty("total", crops.size()); result.addProperty("grain_before", grainBefore);
        result.addProperty("harvest_sent", harvestSent.size()); result.addProperty("removed_confirmed", removed.size());
        result.addProperty("plant_sent", plantSent.size()); result.addProperty("replanted_confirmed", restored.size());
        result.addProperty("cells_server_confirmed", cellsConfirmed());
        var positions = new com.google.gson.JsonArray();
        crops.forEach(p -> { var row = new com.google.gson.JsonArray(); row.add(p.getX()); row.add(p.getY()); row.add(p.getZ()); positions.add(row); });
        result.add("crop_positions", positions);
        return result;
    }
}
