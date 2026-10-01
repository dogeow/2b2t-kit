package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** The native material lease owns one immutable same-dimension return target. */
class MaterialReturnTargetTest {
    @Test void sameDimensionUniqueHomeWinsAndUsesSafeCruiseHeight() {
        var home = new MaterialReturnTargetPolicy.Home(761020.5, 797850.5, 129,
            "minecraft:overworld");
        var target = MaterialReturnTargetPolicy.choose(home,
            "minecraft:overworld", 10, 70, 20);

        assertEquals("saved_home", target.source());
        assertEquals("minecraft:overworld", target.dimension());
        assertEquals(761020.5, target.x());
        assertEquals(797850.5, target.z());
        assertEquals(160, target.cruiseY());
    }

    @Test void otherDimensionHomeCannotReplaceTheSessionOrigin() {
        var home = new MaterialReturnTargetPolicy.Home(100, 200, 180,
            "minecraft:the_nether");
        var target = MaterialReturnTargetPolicy.choose(home,
            "minecraft:overworld", 30, 205, 40);

        assertEquals("search_origin", target.source());
        assertEquals(30, target.x());
        assertEquals(40, target.z());
        assertEquals(205, target.cruiseY());
    }

    @Test void invalidHomeFallsBackWithoutSerializingItsCoordinates() {
        var home = new MaterialReturnTargetPolicy.Home(Double.POSITIVE_INFINITY, 200, 180,
            "minecraft:overworld");
        var target = MaterialReturnTargetPolicy.choose(home,
            "minecraft:overworld", 50, 70, 60);

        assertEquals("search_origin", target.source());
        assertEquals(50, target.x());
        assertEquals(60, target.z());
        assertEquals(160, target.cruiseY());
    }
}
