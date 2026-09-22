package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BorerSurroundWaitTest {
    @Test void completedShelterContinuesNormally(){var p=new BorerSurroundWait();p.started(0,20);assertFalse(p.shouldAbort(true,5,20));assertFalse(p.shouldAbort(false,10,20));assertTrue(p.allowed());}
    @Test void unfinishedShelterCannotFreezeCombatIndefinitely(){var p=new BorerSurroundWait();p.started(10,20);assertFalse(p.shouldAbort(true,39,20));assertTrue(p.shouldAbort(true,40,20));assertFalse(p.allowed());}
    @Test void beingHitAbortsImmediatelyEvenBeforeTheTimeout(){var p=new BorerSurroundWait();p.started(10,20);assertTrue(p.shouldAbort(true,11,19.2F));assertFalse(p.allowed());}
    @Test void failedShelterIsNotImmediatelyStartedAgain(){var p=new BorerSurroundWait();p.started(0,20);p.shouldAbort(true,30,20);p.shouldAbort(false,31,20);assertFalse(p.allowed());p.reset();assertTrue(p.allowed());}
    @Test void unrelatedManualShelterIsNotOwnedByThisPolicy(){var p=new BorerSurroundWait();assertFalse(p.shouldAbort(true,100,1));}
}
