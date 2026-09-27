package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.Collections;
import static org.junit.jupiter.api.Assertions.*;

class NativeMaterialSlotTest {
    @Test void exactSilkTouchSlotWinsOverEarlierFortuneShovel() {
        var items=new ArrayList<>(Collections.nCopies(36,"minecraft:air"));
        items.set(2,"minecraft:diamond_shovel");items.set(17,"minecraft:diamond_shovel");
        assertEquals(2,AutomationBridge.matchingInventorySlot(items,"minecraft:diamond_shovel",null));
        assertEquals(17,AutomationBridge.matchingInventorySlot(items,"minecraft:diamond_shovel",17));
        assertThrows(IllegalStateException.class,()->AutomationBridge.matchingInventorySlot(items,"minecraft:diamond_shovel",18));
        assertThrows(IllegalStateException.class,()->AutomationBridge.matchingInventorySlot(items,"minecraft:diamond_shovel",36));
    }
}
