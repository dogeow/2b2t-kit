package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
class BuildSupplyPlanTest {
    @Test void onlyActualDeficitsAndCraftableInputsAreOffered(){
        var r=BuildSupplyPlan.targets(Map.of("minecraft:oak_planks",5,"minecraft:glass",2),Map.of("minecraft:oak_planks",1,"minecraft:glass",2));
        assertEquals(Map.of("minecraft:oak_planks",5,"minecraft:oak_log",1),r);
        assertFalse(BuildSupplyPlan.targets(Map.of("minecraft:warped_planks",4),Map.of()).containsKey("minecraft:warped_log"));
    }
    @Test void carriedLogsAndCompletePlanksDoNotTriggerMoreSupply(){
        assertEquals(Map.of("minecraft:oak_planks",5),BuildSupplyPlan.targets(Map.of("minecraft:oak_planks",5),Map.of("minecraft:oak_log",2)));
        assertTrue(BuildSupplyPlan.targets(Map.of("minecraft:oak_planks",5),Map.of("minecraft:oak_planks",5)).isEmpty());
    }
    @Test void bothInventoryAndContainerMustAcknowledgeTheSameTransfer(){
        assertTrue(BuildSupplyPlan.confirmed(1,17,32,16,16));
        assertFalse(BuildSupplyPlan.confirmed(1,17,32,32,16));
        assertFalse(BuildSupplyPlan.confirmed(1,1,32,16,16));
        assertFalse(BuildSupplyPlan.confirmed(1,33,32,0,16));
    }
}
