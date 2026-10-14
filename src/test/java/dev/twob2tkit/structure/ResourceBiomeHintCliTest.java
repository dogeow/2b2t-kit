package dev.twob2tkit.structure;

import org.junit.jupiter.api.Test;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class ResourceBiomeHintCliTest {
    @Test void unverifiedSavedSeedsDoNotEmitTravelCandidates(){
        var saved=new com.google.gson.JsonObject();
        assertFalse(ResourceBiomeHintCli.seedHashMatches(saved,0));
        saved.addProperty("hasHashedSeed",true);
        saved.addProperty("hashedSeed",net.minecraft.world.level.biome.BiomeManager.obfuscateSeed(0));
        assertTrue(ResourceBiomeHintCli.seedHashMatches(saved,0));
        assertFalse(ResourceBiomeHintCli.seedHashMatches(saved,1));
        saved.addProperty("hasHashedSeed",false);
        assertFalse(ResourceBiomeHintCli.seedHashMatches(saved,0));
    }
    @Test void mismatchedOrOceanOnlySamplesCannotAuthorizeAnotherLongSeedTrip(){
        assertFalse(ResourceBiomeHintCli.calibrationAllowsHints(false,5,0,2));
        assertFalse(ResourceBiomeHintCli.calibrationAllowsHints(true,5,4,2));
        assertFalse(ResourceBiomeHintCli.calibrationAllowsHints(false,5,5,0));
        assertFalse(ResourceBiomeHintCli.calibrationAllowsHints(true,4,4,2));
        assertTrue(ResourceBiomeHintCli.calibrationAllowsHints(false,5,5,2));
        assertTrue(ResourceBiomeHintCli.calibrationAllowsHints(true,5,5,0));
    }
    @Test void candidatesOutsideTheUsersBorderNeverBecomeTravelHints(){
        assertTrue(ResourceBiomeHintCli.insideBoundary(761021,797829,800000));
        assertFalse(ResourceBiomeHintCli.insideBoundary(761021,801157,800000));
        assertFalse(ResourceBiomeHintCli.insideBoundary(799968,0,800000));
        assertFalse(ResourceBiomeHintCli.insideBoundary(-800000,0,800000));
        assertFalse(ResourceBiomeHintCli.insideBoundary(Integer.MIN_VALUE,0,800000));
    }
    @Test void oldSavannaDefaultAndExplicitDesertFilterAreIndependent(){
        assertTrue(ResourceBiomeHintCli.parseBiomes("").contains("minecraft:savanna"));
        assertEquals(Set.of("minecraft:desert","minecraft:badlands"),
            ResourceBiomeHintCli.parseBiomes("minecraft:desert,minecraft:badlands,minecraft:desert"));
        assertFalse(ResourceBiomeHintCli.parseBiomes("").contains("minecraft:desert"));
    }
    @Test void malformedOrExcessiveFiltersNeverStartSampling(){
        for(String value:new String[]{"desert","minecraft:desert,","minecraft:desert;give","minecraft:DESERT"})
            assertThrows(IllegalArgumentException.class,()->ResourceBiomeHintCli.parseBiomes(value));
        String many=String.join(",",java.util.stream.IntStream.range(0,33)
            .mapToObj(i->"minecraft:biome"+(char)('a'+i/26)+(char)('a'+i%26)).toList());
        assertThrows(IllegalArgumentException.class,()->ResourceBiomeHintCli.parseBiomes(many));
    }
}
