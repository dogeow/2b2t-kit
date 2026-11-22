package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.MapTaskView.Area;
import java.util.ArrayList;
import java.util.List;

final class SceneryMapTiles {
    record Tiles(List<Area> areas, int step) {}

    static Tiles missing(SceneryCoverage plan, Area view) {
        int minX = Math.floorDiv(Math.max(view.minX(), (int)Math.floor(plan.centreX - plan.radius) - 16), 16);
        int maxX = Math.floorDiv(Math.min(view.maxX(), (int)Math.ceil(plan.centreX + plan.radius)), 16);
        int minZ = Math.floorDiv(Math.max(view.minZ(), (int)Math.floor(plan.centreZ - plan.radius) - 16), 16);
        int maxZ = Math.floorDiv(Math.min(view.maxZ(), (int)Math.ceil(plan.centreZ + plan.radius)), 16);
        int step = 1;
        while ((long)Math.max(0, (maxX-minX+step)/step) * Math.max(0, (maxZ-minZ+step)/step) > 1024) step *= 2;
        var missing = new ArrayList<Area>();
        for (int z = minZ; z <= maxZ; z += step) {
            for (int x = minX; x <= maxX; x += step) {
                int endX = Math.min(x + step - 1, maxX);
                int endZ = Math.min(z + step - 1, maxZ);
                // At overview zoom, show sampled gaps as single chunks rather than implying the entire tile is missing.
                int sx = (x + endX) >> 1, sz = (z + endZ) >> 1;
                if (plan.missingForMap(sx, sz)) missing.add(new Area(sx*16, sz*16, sx*16+16, sz*16+16));
            }
        }
        return new Tiles(List.copyOf(missing), step);
    }

    private SceneryMapTiles() {}
}
