package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerNoSupportPolicyTest {
    @Test void onlyVerifiedDryGroundedDropsAreAttempted() {
        assertTrue(BorerNoSupportPolicy.walkSafeDrop(true,false,false,false,2));
        assertFalse(BorerNoSupportPolicy.walkSafeDrop(false,false,false,false,2));
        assertFalse(BorerNoSupportPolicy.walkSafeDrop(true,true,false,false,2));
        assertFalse(BorerNoSupportPolicy.walkSafeDrop(true,false,true,false,2));
        assertFalse(BorerNoSupportPolicy.walkSafeDrop(true,false,false,true,2));
        assertFalse(BorerNoSupportPolicy.walkSafeDrop(true,false,false,false,-1));
        assertFalse(BorerNoSupportPolicy.walkSafeDrop(true,false,false,false,0));
    }
    @Test void blockedOreEventuallyReplansButActiveLootIsNotCountedAsCollected() {
        assertFalse(BorerNoSupportPolicy.replanOre(true,false,79));
        assertTrue(BorerNoSupportPolicy.replanOre(true,false,80));
        assertFalse(BorerNoSupportPolicy.replanOre(true,true,1000));
        assertFalse(BorerNoSupportPolicy.stopUnroutable(false,false,true,1000));
        assertTrue(BorerNoSupportPolicy.stopUnroutable(false,false,false,200));
        assertTrue(BorerNoSupportPolicy.stopUnroutable(true,false,false,200));
        assertFalse(BorerNoSupportPolicy.stopUnroutable(true,true,false,200));
    }
}
