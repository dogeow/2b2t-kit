package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class TrialCreeperMeleePolicyTest {
    private final UUID id=UUID.randomUUID();
    @Test void onlyExplicitTrialAuthorityAndOrdinaryCurrentVisibleCreepersQualify(){
        assertTrue(TrialCreeperMeleePolicy.eligible(true,true,true,true,false,false,false,8));
        assertFalse(TrialCreeperMeleePolicy.eligible(false,true,true,true,false,false,false,8));
        assertFalse(TrialCreeperMeleePolicy.eligible(true,false,true,true,false,false,false,8));
        assertFalse(TrialCreeperMeleePolicy.eligible(true,true,true,false,false,false,false,8));
        assertFalse(TrialCreeperMeleePolicy.eligible(true,true,true,true,true,false,false,8));
        assertFalse(TrialCreeperMeleePolicy.eligible(true,true,true,true,false,true,false,8));
        assertFalse(TrialCreeperMeleePolicy.eligible(true,true,true,true,false,false,true,8));
        assertFalse(TrialCreeperMeleePolicy.eligible(true,true,true,true,false,false,false,Double.NaN));
    }
    @Test void starterSwordNeedsForecastSwingsPlusTwoAndAtLeastFive(){
        assertEquals(8,TrialCreeperMeleePolicy.swordReserve(20,4));
        assertTrue(16>=TrialCreeperMeleePolicy.swordReserve(20,4));
        assertEquals(7,TrialCreeperMeleePolicy.swordReserve(20,5));
        assertEquals(5,TrialCreeperMeleePolicy.swordReserve(4,8));
        assertEquals(Integer.MAX_VALUE,TrialCreeperMeleePolicy.swordReserve(20,Double.NaN));
        assertEquals(32,GuardWeaponPolicy.SWORD_RESERVE,"Existing server reserve is untouched");
    }
    private TrialCreeperMeleePolicy.Step step(TrialCreeperMeleePolicy p,int tick,double distance,double health,
                                             boolean swelling,boolean reach,boolean cooled,boolean clear,boolean escape){
        return p.step(id,tick,0,0,distance,health,swelling,reach,cooled,clear,escape);
    }
    @Test void aSwingImmediatelyRetreatsAndOnlyQuietDistanceBeyondSevenResetsTheFuse(){
        var p=new TrialCreeperMeleePolicy();
        assertEquals(TrialCreeperMeleePolicy.Decision.APPROACH,step(p,0,8,20,false,false,true,true,true).decision());
        assertEquals(TrialCreeperMeleePolicy.Decision.ATTACK,step(p,50,3.2,20,false,true,true,true,true).decision());
        p.attacked();
        assertEquals(TrialCreeperMeleePolicy.Decision.RETREAT,step(p,51,3.8,20,false,false,true,true,true).decision());
        assertEquals(TrialCreeperMeleePolicy.Decision.RETREAT,step(p,90,7.6,16,true,false,true,true,true).decision());
        assertEquals(TrialCreeperMeleePolicy.Decision.APPROACH,step(p,92,7.6,16,false,false,true,true,true).decision());
    }
    @Test void cooldownAndEscapeAreRequiredAndBlockedPathsCannotRestartEveryTick(){
        var p=new TrialCreeperMeleePolicy();
        assertEquals(TrialCreeperMeleePolicy.Decision.WAIT,step(p,0,3.2,20,false,true,false,true,true).decision());
        assertEquals("no_safe_escape",step(p,1,3.2,20,false,true,true,true,false).reason());
        assertEquals(TrialCreeperMeleePolicy.Decision.UNAVAILABLE,step(p,10,3.2,20,false,true,true,true,true).decision());
    }
    @Test void swingingWithoutObservedDamageCannotRenewTheBoundedCycle(){
        var p=new TrialCreeperMeleePolicy();step(p,0,8,20,false,false,true,true,true);
        p.attacked();
        assertEquals("no_confirmed_damage",step(p,160,8,20,false,false,true,true,true).reason());
        assertEquals(TrialCreeperMeleePolicy.Decision.UNAVAILABLE,step(p,161,3.2,20,false,true,true,true,true).decision());
    }
}
