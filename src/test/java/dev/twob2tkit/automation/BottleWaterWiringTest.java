package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class BottleWaterWiringTest {
    @Test void normalBottleUseNeedsExactWaterAndServerInventoryWithoutWorldMutation()throws Exception {
        var s=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/BottleWaterAction.java"));
        assertEquals(1,s.split("gameMode\\.useItem\\(",-1).length-1);
        assertTrue(s.indexOf("BucketUseStore.claim(claimPath,claim)")<s.indexOf("gameMode.useItem("));
        assertTrue(s.contains("PotionContents.createItemStack(Items.POTION,Potions.WATER)"));
        assertTrue(s.contains("AreaEffectCloud.class"));assertTrue(s.contains("ClipContext.Fluid.SOURCE_ONLY"));
        assertTrue(s.contains("sender==connection"));assertTrue(s.contains("inventory(c,true)"));
        assertFalse(s.contains(".setBlock("));assertFalse(s.contains(".setItem("));assertFalse(s.contains("gameMode.useItemOn("));
        var bridge=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/AutomationBridge.java"));
        assertTrue(bridge.contains("id.equals(str(lastBottleWater,\"request_id\"))"));
        assertTrue(bridge.contains("result.add(\"bottle_water\",lastBottleWater.deepCopy())"));
    }
}
