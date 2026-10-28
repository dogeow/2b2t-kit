package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.automation.ProjectedWetTerrainPolicy.*;

class ProjectedWetTerrainPolicyTest {
    @Test void naturalEarthCanBeReplacedByTheLockedBuildingMaterial(){
        assertTrue(obstruction("minecraft:dirt","minecraft:cobblestone_slab"));
        assertTrue(obstruction("minecraft:stone","minecraft:packed_ice"));
        assertTrue(obstruction("minecraft:clay","minecraft:air"));
        assertFalse(obstruction("minecraft:diamond_ore","minecraft:air"));
        assertFalse(obstruction("minecraft:chest","minecraft:cobblestone"));
        assertFalse(obstruction("minecraft:cobblestone","minecraft:air"));
        assertFalse(obstruction("minecraft:water","minecraft:hopper"));
        assertFalse(obstruction("minecraft:stone","minecraft:diamond_block"));
    }
    @Test void oneRemovalMayFloodAirButNeverWaivesOriginalSourcesOrWaterloggedStates(){
        String source="Block{minecraft:water}[level=0]",flow="Block{minecraft:water}[level=8]";
        assertTrue(neighborPreserved(source,source,false));
        assertFalse(neighborPreserved(source,flow,true));
        assertFalse(neighborPreserved(source,"Block{minecraft:air}",true));
        assertFalse(neighborPreserved("Block{minecraft:air}",flow,false));
        assertTrue(neighborPreserved("Block{minecraft:air}",flow,true));
        assertTrue(neighborPreserved(flow,"Block{minecraft:water}[level=3]",true));
        assertFalse(neighborPreserved(flow,"Block{minecraft:lava}[level=0]",true));
        assertFalse(neighborPreserved("Block{minecraft:water}[level=99]",flow,true));
        assertFalse(neighborPreserved("Block{minecraft:cobblestone_slab}[type=top,waterlogged=true]",flow,true));
        assertFalse(neighborPreserved(null,source,true));
    }
    @Test void ownershipHealthScopeToolFootingAndLocalContainersCannotBeWaived(){
        assertNull(rejection(true,true,true,true,true,false,true,false));
        for(int i=0;i<8;i++){
            boolean[] v={true,true,true,true,true,false,true,false};v[i]=!v[i];
            assertNotNull(rejection(v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7]));
        }
    }
}
