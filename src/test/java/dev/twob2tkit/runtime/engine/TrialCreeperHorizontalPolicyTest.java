package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class TrialCreeperHorizontalPolicyTest {
    private TrialCreeperHorizontalPolicy.Threat ordinary(double feet,double body){
        return new TrialCreeperHorizontalPolicy.Threat(true,true,true,false,false,false,true,feet,body);
    }
    private boolean safe(TrialCreeperHorizontalPolicy.Threat t){
        return TrialCreeperHorizontalPolicy.safe(true,true,false,true,false,List.of(t));
    }
    @Test void actualLoadedTwentyEightBlockCaseMayPrepareSwordWithoutCallingItAKill(){
        var target=ordinary(28,26.8);assertTrue(safe(target));
        UUID id=UUID.randomUUID();var session=new BorerCombatSession<String>();
        session.beginTick(0);session.observe(id,"actual alive creeper",true,false,true,20);
        session.beginTick(600);session.observe(id,"still alive at 28",false,false,true,20);assertFalse(session.canAttack(id));
        session.pause(600);assertTrue(session.contains(id));assertTrue(session.pending());
        session.beginTick(601);session.observe(id,"approached again",true,false,true,20);
        assertFalse(safe(ordinary(15.99,14.7)));assertTrue(session.contains(id));
        assertTrue(session.retryTrialMelee(id,true));assertTrue(session.canAttack(id));
        session.observe(id,"confirmed death",false,true,false,0);assertFalse(session.pending());
    }
    @Test void currentUnknownChargedIgnitedOrSwellingTargetsNeverDefer(){
        assertFalse(safe(new TrialCreeperHorizontalPolicy.Threat(false,true,true,false,false,false,true,28,27)));
        assertFalse(safe(new TrialCreeperHorizontalPolicy.Threat(true,false,true,false,false,false,true,28,27)));
        assertFalse(safe(new TrialCreeperHorizontalPolicy.Threat(true,true,false,false,false,false,true,28,27)));
        assertFalse(safe(new TrialCreeperHorizontalPolicy.Threat(true,true,true,true,false,false,true,28,27)));
        assertFalse(safe(new TrialCreeperHorizontalPolicy.Threat(true,true,true,false,true,false,true,28,27)));
        assertFalse(safe(new TrialCreeperHorizontalPolicy.Threat(true,true,true,false,false,true,true,28,27)));
        assertFalse(safe(new TrialCreeperHorizontalPolicy.Threat(true,true,true,false,false,false,false,28,27)));
    }
    @Test void actualBodyDistanceThresholdFiniteEvidenceAndEveryPendingTargetAreRequired(){
        assertTrue(safe(ordinary(17.2,16)));
        assertFalse(safe(ordinary(17.2,15.999)));
        assertFalse(safe(ordinary(Double.NaN,17)));assertFalse(safe(ordinary(28,Double.POSITIVE_INFINITY)));
        assertFalse(TrialCreeperHorizontalPolicy.safe(true,true,false,true,false,List.of(ordinary(28,27),ordinary(14,13))));
        assertFalse(TrialCreeperHorizontalPolicy.safe(true,true,false,true,false,List.of()));
    }
    @Test void serverScopesOtherHostilesMissingContinuationAndAirbornePlayerKeepDefense(){
        var targets=List.of(ordinary(28,27));
        assertFalse(TrialCreeperHorizontalPolicy.safe(false,true,false,true,false,targets));
        assertFalse(TrialCreeperHorizontalPolicy.safe(true,false,false,true,false,targets));
        assertFalse(TrialCreeperHorizontalPolicy.safe(true,true,true,true,false,targets));
        assertFalse(TrialCreeperHorizontalPolicy.safe(true,true,false,true,true,targets));
        assertFalse(TrialCreeperHorizontalPolicy.safe(true,true,false,false,false,targets));
    }
}
