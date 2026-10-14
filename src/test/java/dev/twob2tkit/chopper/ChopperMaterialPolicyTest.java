package dev.twob2tkit.chopper;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChopperMaterialPolicyTest {
    @Test void retainSaplingsAvoidsReplantingAndLeafHarvestWithoutChangingConfiguredDefaults(){
        assertFalse(ChopperMaterialPolicy.replant(true,true));
        assertFalse(ChopperMaterialPolicy.harvestLeaves(true,true));
        assertTrue(ChopperMaterialPolicy.replant(true,false));
        assertTrue(ChopperMaterialPolicy.harvestLeaves(true,false));
    }
    @Test void disabledUserSettingsStayDisabledOutsideTheMaterialGoal(){
        for(boolean retain:new boolean[]{false,true}){
            assertFalse(ChopperMaterialPolicy.replant(false,retain));
            assertFalse(ChopperMaterialPolicy.harvestLeaves(false,retain));
        }
    }
}
