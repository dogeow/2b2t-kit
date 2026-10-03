package dev.twob2tkit.automation;

import dev.twob2tkit.fisher.IdleFishingPolicy;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class IdleFishingPolicyTest {
    @Test void twoTickFullInventoryStopsBeforeEitherExistingOrNewChestCouldBeUsed(){
        assertEquals(IdleFishingPolicy.Decision.FISH,IdleFishingPolicy.decide(true,true,false,0,0));
        // A loot pickup fills the last slot before the next Python observation.
        // Chest presence/search is absent from the idle decision contract.
        assertEquals(IdleFishingPolicy.Decision.STOP_FULL,IdleFishingPolicy.decide(true,true,true,0,0));
        assertFalse(IdleFishingPolicy.mayDeposit(true,true));
    }
    @Test void dumpPhaseOrDisplacementCannotMakeIdleMoveOrDeposit(){
        assertEquals(IdleFishingPolicy.Decision.STOP_CHANGED,IdleFishingPolicy.decide(true,false,false,0,0));
        assertEquals(IdleFishingPolicy.Decision.STOP_CHANGED,IdleFishingPolicy.decide(true,true,false,.46,0));
        assertEquals(IdleFishingPolicy.Decision.STOP_CHANGED,IdleFishingPolicy.decide(true,true,false,0,.46));
        assertEquals(IdleFishingPolicy.Decision.STOP_CHANGED,IdleFishingPolicy.decide(true,true,false,Double.NaN,0));
    }
    @Test void ordinaryFisherAndInactiveStatusRetainTheirMeaning(){
        assertEquals(IdleFishingPolicy.Decision.NORMAL,IdleFishingPolicy.decide(false,false,true,10,10));
        assertTrue(IdleFishingPolicy.mayDeposit(true,false));
        assertFalse(IdleFishingPolicy.mayDeposit(false,false));
        assertFalse(IdleFishingPolicy.mayDeposit(false,true));
    }
    @Test void readonlyRangeMatchesTheExistingActualClampWithoutChangingPreference(){
        assertEquals(2,IdleFishingPolicy.chestRange(-20));assertEquals(2,IdleFishingPolicy.chestRange(1));
        assertEquals(7,IdleFishingPolicy.chestRange(7));assertEquals(8,IdleFishingPolicy.chestRange(999));
    }
}
