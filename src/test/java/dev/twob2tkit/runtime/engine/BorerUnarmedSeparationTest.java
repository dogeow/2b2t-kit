package dev.twob2tkit.runtime.engine;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerUnarmedSeparationTest {
    private final Object world=new Object();
    private boolean safe(BorerCombatSeparation.Threat threat){
        return BorerCombatSeparation.safe(true,true,true,false,false,List.of(threat));
    }
    private BorerCombatSeparation.Threat unarmed(boolean visible,double distance,double clearance){
        return new BorerCombatSeparation.Threat(true,false,visible,false,distance,clearance,false,true);
    }
    @Test void actualDrownedAfterFixedRiseCanWatchVisibleOrHiddenWithoutAnyKillCredit(){
        var gate=new BorerCombatSeparation();var session=new BorerCombatSession<String>();
        var id=UUID.fromString("285bd39c-e09d-4ae2-ac7b-7f1392624c30");
        double clearance=79.55760029413983-.0784*10-55.771777391433716;
        for(int tick=0;tick<=20;tick++){
            session.beginTick(tick);session.observe(id,"alive5.7319994 unarmed drowned",true,false,false,5.7319994f);
            boolean yielded=gate.observe(world,tick,safe(unarmed(tick%2==0,25.8831,clearance)));
            assertEquals(tick==20,yielded);assertTrue(session.contains(id));assertEquals(1,session.targets().size());
            if(yielded)session.pause(tick);
        }
        assertTrue(gate.yielding());assertTrue(session.pending());assertFalse(session.canAttack(id));
    }
    @Test void approachOrDescentReacquiresSameUuidImmediatelyWithoutExtendingAttackPermission(){
        var gate=new BorerCombatSeparation();var session=new BorerCombatSession<String>();var id=UUID.randomUUID();
        session.beginTick(0);session.observe(id,"same alive drowned",true,false,false,5.7f);
        gate.observe(world,0,safe(unarmed(true,25,20)));assertTrue(gate.observe(world,20,safe(unarmed(true,25,20))));session.pause(20);
        assertFalse(gate.observe(world,21,safe(unarmed(true,8,2))));assertFalse(gate.yielding());assertTrue(session.contains(id));
        session.beginTick(21);session.observe(id,"same alive current target",true,false,true,5.7f);
        assertTrue(session.canAttack(id));assertTrue(session.pending());
        assertFalse(gate.observe(world,22,safe(unarmed(true,25,20))),"Returning to safety requires another full quiet window");
    }
    @Test void boundariesUnknownArmedRangedDamageOrAnotherThreatCannotRelease(){
        for(var threat:List.of(unarmed(true,11.999,20),unarmed(false,25,5.999),
                unarmed(true,Double.NaN,20),unarmed(true,25,Double.POSITIVE_INFINITY),
                new BorerCombatSeparation.Threat(true,false,true,false,25,20,false,false),
                new BorerCombatSeparation.Threat(false,false,false,false,25,20,false,true),
                new BorerCombatSeparation.Threat(true,false,true,true,25,20,false,true))){assertFalse(safe(threat));}
        assertTrue(safe(unarmed(true,12,6)));
        assertFalse(BorerCombatSeparation.safe(true,true,false,false,false,List.of(unarmed(true,25,20))));
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,true,List.of(unarmed(true,25,20))));
        assertFalse(BorerCombatSeparation.safe(true,true,true,true,false,List.of(unarmed(true,25,20))));
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,false,List.of(unarmed(true,25,20),
            new BorerCombatSeparation.Threat(true,false,false,false,25,20))));
    }
    @Test void onlyPreviouslyVerifiedCurrentUnarmedUuidMayUseStrongerUnloadedExitMargin(){
        var gate=new BorerCombatSeparation();var id=UUID.randomUUID();
        assertFalse(safe(gate.unloaded(world,id,0,90,0)));
        gate.seen(world,id,0,52,0,54,false,false,true);
        assertFalse(safe(gate.unloaded(world,id,0,90,0)),"A remembered position alone is not verified safety");
        gate.observe(world,0,true);gate.observe(world,20,true);gate.verifyDeferred(world,List.of(id));
        assertTrue(safe(gate.unloaded(world,id,0,90,0)));
        assertFalse(safe(gate.unloaded(world,id,0,75.99,0)),"Need24 distance despite16 height clearance");
        assertFalse(safe(gate.unloaded(world,id,50,69.99,0)),"Need16 projected clearance despite large distance");
        assertFalse(safe(gate.unloaded(new Object(),id,0,90,0)));
        assertFalse(safe(new BorerCombatSeparation().unloaded(world,id,0,90,0)),"Reload cannot invent a verified watch");
    }
    @Test void newCurrentWeaponDamageOrMalformedBodyRevokesOlderVerifiedEvidence(){
        var gate=new BorerCombatSeparation();var id=UUID.randomUUID();
        gate.seen(world,id,0,52,0,54,false,false,true);gate.observe(world,0,true);gate.observe(world,20,true);gate.verifyDeferred(world,List.of(id));
        gate.seen(world,id,0,52,0,54,false,false,false);
        assertFalse(safe(gate.unloaded(world,id,0,90,0)),"Current armed/ranged/hit evidence overrides previous unarmed classification");
        gate.seen(world,id,Double.NaN,Double.NaN,Double.NaN,Double.NaN,false,false,false);
        assertNull(gate.lastVerified(world,id));
    }
    @Test void armedThenEmptyThenUnloadCannotReviveThePreviousUnarmedProof(){
        var gate=new BorerCombatSeparation();var id=UUID.randomUUID();
        gate.seen(world,id,0,52,0,54,false,false,true);gate.observe(world,0,true);gate.observe(world,20,true);gate.verifyDeferred(world,List.of(id));
        assertTrue(safe(gate.unloaded(world,id,0,90,0)));
        gate.seen(world,id,0,52,0,54,false,false,false);gate.observe(world,21,false);
        gate.seen(world,id,0,52,0,54,false,false,true);
        assertFalse(safe(gate.unloaded(world,id,0,90,0)),"A single empty-hand observation cannot restore the old proof");
        assertFalse(gate.observe(world,22,true));assertFalse(gate.observe(world,41,true));
        assertTrue(gate.observe(world,42,true));gate.verifyDeferred(world,List.of(id));
        assertTrue(safe(gate.unloaded(world,id,0,90,0)));
    }
    @Test void nearThenFarThenUnloadNeedsAnotherFullCurrentQuietWindow(){
        var gate=new BorerCombatSeparation();var id=UUID.randomUUID();
        gate.seen(world,id,0,52,0,54,false,false,true);gate.observe(world,0,true);gate.observe(world,20,true);gate.verifyDeferred(world,List.of(id));
        gate.seen(world,id,0,88,0,90,false,false,true);gate.revokeUnarmed(world,id);assertFalse(gate.observe(world,21,safe(unarmed(true,2,0))));
        gate.seen(world,id,0,52,0,54,false,false,true);
        assertFalse(safe(gate.unloaded(world,id,0,90,0)),"Moving far again does not resurrect a revoked proof");
        assertFalse(gate.observe(world,22,true));assertFalse(gate.observe(world,41,true));
        assertTrue(gate.observe(world,42,true));gate.verifyDeferred(world,List.of(id));
        assertTrue(safe(gate.unloaded(world,id,0,90,0)));
    }
    @Test void legacyCreeperConditionsAndManualFlightWorldLifecycleArePreserved(){
        assertTrue(safe(new BorerCombatSeparation.Threat(true,true,false,false,8.5,6.8)));
        assertFalse(safe(new BorerCombatSeparation.Threat(true,true,true,false,25,20)));
        for(boolean standalone:List.of(false))assertFalse(BorerCombatSeparation.safe(standalone,true,true,false,false,List.of(unarmed(true,25,20))));
        assertFalse(BorerCombatSeparation.safe(true,false,true,false,false,List.of(unarmed(true,25,20))));
        var gate=new BorerCombatSeparation();gate.observe(world,0,true);assertTrue(gate.observe(world,20,true));
        assertFalse(gate.observe(new Object(),21,true));assertFalse(gate.retain(world));
    }
    @Test void unrelatedThreatHealthOrFlightFailurePreservesPerUuidProofButRestartsQuietWindow(){
        var gate=new BorerCombatSeparation();var safeId=UUID.randomUUID();var unsafeId=UUID.randomUUID();
        for(var id:List.of(safeId,unsafeId))gate.seen(world,id,0,52,0,54,false,false,true);
        gate.observe(world,0,true);gate.observe(world,20,true);gate.verifyDeferred(world,List.of(safeId,unsafeId));
        gate.revokeUnarmed(world,unsafeId);gate.observe(world,21,false);
        assertNull(gate.lastVerified(world,unsafeId));assertNotNull(gate.lastVerified(world,safeId));
        assertTrue(safe(gate.unloaded(world,safeId,0,90,0)));
        assertFalse(gate.observe(world,22,true));assertFalse(gate.observe(world,41,true));
        assertTrue(gate.observe(world,42,true));
    }
    @Test void unavailableChunkKeepsLastReliablePositionWhileUnsafeClassificationRevokesOnlyThatId(){
        var gate=new BorerCombatSeparation();var id=UUID.randomUUID();
        gate.seen(world,id,0,52,0,54,false,false,true);gate.observe(world,0,true);
        gate.observe(world,20,true);gate.verifyDeferred(world,List.of(id));
        var reliable=gate.lastVerified(world,id);
        gate.observe(world,21,false);
        assertEquals(reliable,gate.lastVerified(world,id));
        assertTrue(safe(gate.unloaded(world,id,0,90,0)));
        gate.revokeUnarmed(new Object(),id);assertEquals(reliable,gate.lastVerified(world,id));
        gate.revokeUnarmed(world,id);assertNull(gate.lastVerified(world,id));
    }

}
