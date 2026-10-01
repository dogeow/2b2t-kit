package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class MapAutomationWiringTest {
    private static String source(String name)throws Exception {
        return Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/"+name+".java"));
    }
    @Test void createHasExactlyOneNormalUseAndNoServerMapCreationOrInventoryFabrication()throws Exception {
        var helper=source("MapAutomation");
        assertEquals(1,helper.split("gameMode\\.useItem\\(",-1).length-1);
        assertTrue(helper.contains("if(useSent)throw"));
        assertFalse(helper.contains("MapItem.create("));
        assertFalse(helper.contains("createFresh("));
        assertFalse(helper.contains("setItem("));
        assertFalse(helper.contains("createForClient("));
        var bridge=source("AutomationBridge");
        assertTrue(bridge.contains("currentMaterialRequest(c,r)"));
        assertTrue(bridge.contains("mapCreationTask.poll(c,ticks>=deadline)"));
        assertTrue(bridge.contains("loadedHostileNearby(c)"));
    }
    @Test void auditExposesOnlyExistingClientDataAndDoesNotClaimGeographicOrFreshnessProof()throws Exception {
        var helper=source("MapAutomation");
        assertTrue(helper.contains("c.level.getMapData(id)"));
        assertTrue(helper.contains("geographic_center_verified\",false"));
        assertTrue(helper.contains("geographic_dimension_verified\",false"));
        assertTrue(helper.contains("Map data is not loaded"));
        assertFalse(helper.contains("overrideMapData("));
    }
    @Test void anvilReadsOfferedMenuCostAndActualResultPickupRatherThanInferringFromXp()throws Exception {
        var bridge=source("AutomationBridge");
        assertTrue(bridge.contains("m.addProperty(\"anvil_cost\",anvil.getCost())"));
        assertTrue(bridge.contains(".RESULT_SLOT).mayPickup(c.player)"));
        assertTrue(bridge.contains("anvil_too_expensive"));
    }
}
