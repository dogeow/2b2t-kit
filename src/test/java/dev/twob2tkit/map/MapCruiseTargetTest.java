package dev.twob2tkit.map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class MapCruiseTargetTest {
    @Test void requiresCurrentDimensionAndFiniteWorldCoordinates(){
        assertTrue(MapCruiseTarget.allowed("minecraft:overworld","minecraft:overworld",761088,797696));
        assertFalse(MapCruiseTarget.allowed("minecraft:overworld","minecraft:the_nether",761088,797696));
        assertFalse(MapCruiseTarget.allowed(null,"minecraft:overworld",0,0));
        assertFalse(MapCruiseTarget.allowed("minecraft:overworld","minecraft:overworld",Double.NaN,0));
        assertFalse(MapCruiseTarget.allowed("minecraft:overworld","minecraft:overworld",0,Double.POSITIVE_INFINITY));
        assertFalse(MapCruiseTarget.allowed("minecraft:overworld","minecraft:overworld",30_000_000,0));
    }
}
