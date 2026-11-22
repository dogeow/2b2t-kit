package dev.twob2tkit.runtime.api;

import java.util.List;
import net.minecraft.core.BlockPos;

/** Read-only map data; no controller or cache operation may be started by these views. */
public final class MapTaskView {
    private MapTaskView() {}

    public record Route(List<List<BlockPos>> recorded, List<BlockPos> next) {}
    public record Area(int minX, int minZ, int maxX, int maxZ) {}
    public record Scenery(double x, double z, int radius, int covered, int total,
                          Area batch, BlockPos next, String reason, List<Area> missing, int sampleChunks) {}
}
