package dev.twob2tkit.concrete;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ConcreteConfirmationTest {
    @Test void rejectedPredictedPlacementNeverCounts(){
        var c=new ConcreteConfirmation();c.reset(false);c.beginMining();c.observe(false,true);
        assertFalse(c.canMine());assertFalse(c.removed());
    }
    @Test void requiresServerSolidThenMiningThenServerAir(){
        var c=new ConcreteConfirmation();c.reset(false);c.observe(true,false);assertTrue(c.canMine());
        c.observe(false,true);assertFalse(c.removed());c.beginMining();assertFalse(c.removed());
        c.observe(false,true);assertTrue(c.removed());assertFalse(c.canMine());
    }
    @Test void serverRollbackKeepsSameCycleWithoutDoubleCounting(){
        var c=new ConcreteConfirmation();c.reset(false);c.observe(true,false);c.beginMining();
        c.observe(false,true);assertTrue(c.removed());c.observe(true,false);assertFalse(c.removed());
        c.observe(false,true);assertTrue(c.removed());c.reset(false);assertFalse(c.removed());
    }
    @Test void freshCycleCannotReusePreviousServerConfirmation(){
        var c=new ConcreteConfirmation();c.reset(true);c.beginMining();c.observe(false,true);assertTrue(c.removed());
        c.reset(false);c.observe(false,true);assertFalse(c.canMine());assertFalse(c.removed());
    }
}
