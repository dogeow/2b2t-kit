package dev.twob2tkit.runtime.engine;

import static org.junit.jupiter.api.Assertions.*;
import dev.twob2tkit.runtime.api.MapTaskView.Area;
import org.junit.jupiter.api.Test;

class SceneryMapTilesTest {
    @Test void coverageKeepsUnconfirmedChunksAndHidesOutOfBounds() {
        var plan = new SceneryCoverage(0, 0, 64);
        plan.clipTo(new SceneryCoverage.ChunkBounds(0, 3, 0, 3));
        plan.reuse(new SceneryCoverage.Chunk(0,0));
        plan.accepted(1,0);
        var view = new Area(-32,-32,32,32);
        var missing = SceneryMapTiles.missing(plan,view).areas();
        assertFalse(missing.contains(new Area(0,0,16,16)));
        assertTrue(missing.contains(new Area(16,0,32,16)));
        assertTrue(missing.stream().allMatch(cell -> cell.minX() >= 0 && cell.minZ() >= 0));
        plan.commitBatch();
        assertFalse(SceneryMapTiles.missing(plan,view).areas().contains(new Area(16,0,32,16)));
    }

    @Test void overviewSamplesWithoutPaintingEntireRegionAsMissing() {
        var plan = new SceneryCoverage(0,0,32768);
        var tiles = SceneryMapTiles.missing(plan,new Area(-50000,-50000,50000,50000));
        assertTrue(tiles.step()>1);
        assertFalse(tiles.areas().isEmpty());
        assertTrue(tiles.areas().size()<=1024);
        assertTrue(tiles.areas().stream().allMatch(cell -> cell.maxX()-cell.minX()==16));
    }
}
