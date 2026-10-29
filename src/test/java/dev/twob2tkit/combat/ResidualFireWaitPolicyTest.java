package dev.twob2tkit.combat;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ResidualFireWaitPolicyTest {
    @Test void escapedVanillaArcherIsDifferentFromIncomingArrowsOrOtherRangedMobs(){
        assertEquals(16,ResidualFireWaitPolicy.rangedRadius("minecraft:skeleton"));
        assertEquals(16,ResidualFireWaitPolicy.rangedRadius("minecraft:bogged"));
        assertEquals(64,ResidualFireWaitPolicy.rangedRadius("minecraft:blaze"));
        assertEquals(40,ResidualFireWaitPolicy.rangedRadius(null));
    }
    private ResidualFireWaitPolicy.Sample sample(double health,boolean fire){
        return new ResidualFireWaitPolicy.Sample(true,true,true,fire,true,true,true,health,20,20);
    }
    @Test void escapedHighHealthBurnWaitsDespiteRegenerationAndRepeatedFireTicks(){
        var w=new ResidualFireWaitPolicy.Window();
        assertTrue(w.observe(1000,sample(19.64,true)));
        assertTrue(w.observe(1500,sample(20,true)));
        assertTrue(w.observe(2000,sample(19.64,true)));
        assertTrue(w.observe(3000,sample(19.64,true)));
        assertEquals(1000,w.started());
    }
    @Test void extinguishedPlayerWaitsForRecoveryThenResumes(){
        var w=new ResidualFireWaitPolicy.Window();w.observe(1000,sample(19.64,true));
        assertTrue(w.observe(6000,sample(19.64,false)));
        assertFalse(w.observe(6500,sample(20,false)));assertFalse(w.active());
    }
    @Test void unknownIgnitionDirectFireAndOtherHazardsKeepOriginalProtection(){
        for(int field=0;field<5;field++){
            var w=new ResidualFireWaitPolicy.Window();
            var s=new ResidualFireWaitPolicy.Sample(field!=0,field!=1,field!=2,true,field!=3,field!=4,true,19.64,20,20);
            assertFalse(w.observe(1000,s));
        }
    }
    @Test void realThreatOrLossOfOwnershipStopsAnExistingWait(){
        for(int field=0;field<3;field++){
            var w=new ResidualFireWaitPolicy.Window();w.observe(1000,sample(19.64,true));
            assertFalse(w.observe(2000,new ResidualFireWaitPolicy.Sample(field!=0,field!=1,field!=2,true,true,true,true,19.64,20,20)));
            assertFalse(w.active());
        }
    }
    @Test void lowOrInvalidHealthAndFoodCannotUseTheWaitException(){
        for(double hp:new double[]{17.99,Double.NaN,Double.POSITIVE_INFINITY,0,21})
            assertFalse(new ResidualFireWaitPolicy.Window().observe(1000,sample(hp,true)));
        assertFalse(new ResidualFireWaitPolicy.Window().observe(1000,
            new ResidualFireWaitPolicy.Sample(true,true,true,true,true,true,true,19,40,20)));
        assertFalse(new ResidualFireWaitPolicy.Window().observe(1000,
            new ResidualFireWaitPolicy.Sample(true,true,true,true,true,true,true,19,20,17)));
    }
    @Test void oneBurnCannotRestartAnExpiredOrUnsafeWait(){
        var w=new ResidualFireWaitPolicy.Window();assertTrue(w.observe(1000,sample(20,true)));
        assertFalse(w.observe(21001,sample(20,true)));
        assertFalse(w.observe(21002,sample(20,true)));
        assertFalse(w.observe(22000,sample(20,false)));
        assertTrue(w.observe(23000,sample(20,true)));
    }
    @Test void clockRollbackCancelsAndContextResetDoesNotCarryTheOldPause(){
        var w=new ResidualFireWaitPolicy.Window();w.observe(1000,sample(20,true));
        assertFalse(w.observe(999,sample(20,true)));w.reset();
        assertFalse(w.active());assertTrue(w.observe(5000,sample(20,true)));
    }
    @Test void alreadyEatingDoesNotGetInterruptedToStartAWait(){
        var w=new ResidualFireWaitPolicy.Window();
        assertFalse(w.observe(1000,new ResidualFireWaitPolicy.Sample(true,true,true,true,true,true,false,19,20,20)));
    }
}
