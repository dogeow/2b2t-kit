package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class BorerCombatSeparationTest {
    private final BorerCombatSeparation gate=new BorerCombatSeparation();
    private final Object world=new Object();
    private BorerCombatSeparation.Threat hidden(){return new BorerCombatSeparation.Threat(true,true,false,false,8.5,6.8);}
    private boolean safe(BorerCombatSeparation.Threat threat){return BorerCombatSeparation.safe(true,true,true,false,false,List.of(threat));}
    @Test void liveCaveCaseY38AboveOrdinaryCreeperY30RequiresContinuousQuietAndKeepsUuid(){
        var session=new BorerCombatSession<String>();UUID uuid=UUID.randomUUID();
        session.beginTick(0);session.observe(uuid,"17hp creeper",true,false,false,17);
        for(int tick=0;tick<20;tick++){assertFalse(gate.observe(world,tick,safe(hidden())));assertTrue(gate.verifying());}
        assertTrue(gate.observe(world,20,safe(hidden())));assertTrue(gate.retain(world));
        session.pause(20);assertTrue(session.pending());assertTrue(session.contains(uuid));
        assertFalse(session.canAttack(uuid));assertEquals(1,session.targets().size());
    }
    @Test void descentOrSightRecoveryImmediatelyRevokesYieldButRetainsUnresolvedIdentity(){
        gate.observe(world,0,true);assertTrue(gate.observe(world,20,true));
        for(var threat:List.of(new BorerCombatSeparation.Threat(true,true,false,false,7.9,6),
                new BorerCombatSeparation.Threat(true,true,false,false,9,3.9),
                new BorerCombatSeparation.Threat(true,true,true,false,8.5,6.8))){
            assertFalse(gate.observe(world,21,safe(threat)));assertFalse(gate.yielding());assertTrue(gate.retain(world));
        }
        assertFalse(gate.observe(world,22,true),"A fresh stable safety window is needed after re-entry");
    }
    @Test void chargedIgnitedMissingRangedOrUnknownThreatsAreNeverGeneralizedToSafeCreepers(){
        for(var threat:List.of(new BorerCombatSeparation.Threat(false,true,false,false,50,30),
                new BorerCombatSeparation.Threat(true,false,false,false,9,6),
                new BorerCombatSeparation.Threat(true,true,false,true,9,6),
                new BorerCombatSeparation.Threat(true,true,false,false,Double.NaN,6))){assertFalse(safe(threat));}
        assertFalse(BorerCombatSeparation.safe(true,true,true,true,false,List.of(hidden())));
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,true,List.of(hidden())));
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,false,List.of()));
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,false,List.of(hidden(),new BorerCombatSeparation.Threat(true,false,false,false,20,10))));
    }
    @Test void unsafeFlightHealthOrScopeCannotReleaseDefense(){
        assertFalse(BorerCombatSeparation.safe(false,true,true,false,false,List.of(hidden())));
        assertFalse(BorerCombatSeparation.safe(true,false,true,false,false,List.of(hidden())));
        assertFalse(BorerCombatSeparation.safe(true,true,false,false,false,List.of(hidden())));
    }
    @Test void ordinarySameWorldHandoffRetainsButWorldChangeAndExplicitStopClearDeferral(){
        gate.observe(world,0,true);gate.observe(world,20,true);assertTrue(gate.retain(world));
        Object other=new Object();assertFalse(gate.retain(other));assertFalse(gate.observe(other,21,true));assertFalse(gate.retain(world));
        gate.observe(other,41,true);assertTrue(gate.retain(other));gate.clear();assertFalse(gate.retain(other));assertFalse(gate.yielding());
        assertFalse(gate.observe(other,42,true));assertFalse(gate.observe(null,100,true));
    }
    @Test void newThreatOrOneUnsafeTickRestartsTheSafetyWindow(){
        gate.observe(world,0,true);gate.observe(world,19,true);gate.observe(world,20,false);
        assertFalse(gate.observe(world,21,true));assertFalse(gate.observe(world,40,true));assertTrue(gate.observe(world,41,true));
    }
    private UUID verifiedCreeper(){
        UUID id=UUID.randomUUID();gate.seen(world,id,760957.64,26,797904.79,27.7,true,false);
        gate.observe(world,0,true);gate.observe(world,20,true);gate.verifyDeferred(world,List.of(id));return id;
    }
    @Test void verifiedCreeperUnloadsDuringVerticalExitWithoutHoldingY95NavigationForever(){
        UUID id=verifiedCreeper();var session=new BorerCombatSession<String>();session.beginTick(0);session.observe(id,"17hp creeper",true,false,false,17);
        var threat=gate.unloaded(world,id,760957.37,95,797899.53);
        assertTrue(threat.previouslyVerifiedSafe());assertFalse(threat.observed());assertTrue(safe(threat));
        assertTrue(gate.observe(world,200,safe(threat)));session.pause(200);
        assertTrue(session.pending());assertTrue(session.contains(id));assertEquals(1,session.targets().size());
    }
    @Test void unloadedExceptionUsesExactUuidAndVerifiedSafetyRatherThanAnyRememberedEntity(){
        UUID id=verifiedCreeper(),newId=UUID.randomUUID();
        gate.seen(world,newId,760957,26,797904,27.7,true,false);
        assertFalse(safe(gate.unloaded(world,newId,760957,95,797904)));
        assertFalse(safe(gate.unloaded(world,UUID.randomUUID(),760957,95,797904)));
        assertFalse(safe(gate.unloaded(new Object(),id,760957,95,797904)));
        var restored=new BorerCombatSeparation();assertFalse(safe(restored.unloaded(world,id,760957,95,797904)),"An unknown hot-reload UUID has no verified separation proof");
        assertFalse(BorerCombatSeparation.safe(true,true,true,true,false,List.of(gate.unloaded(world,id,760957,95,797904))));
    }
    @Test void unloadRequiresBothLargerDistanceAndLargerHeightAndIncludesDownwardPrediction(){
        UUID id=verifiedCreeper();
        assertFalse(safe(gate.unloaded(world,id,760957.64,49.9,797904.79)),"3D distance must be at least 24");
        assertFalse(safe(gate.unloaded(world,id,761000,43.69,797904.79)),"Clearance above the last observed body must be at least 16");
        assertTrue(safe(gate.unloaded(world,id,760957.64,50,797904.79)));
        double feet=50.2,vy=-.05;assertFalse(safe(gate.unloaded(world,id,760957.64,feet+Math.min(0,vy)*10,797904.79)));
    }
    @Test void newerLoadedPositionAndPoweredOrSwellingStateOverrideOldSafeEvidence(){
        UUID id=verifiedCreeper();
        gate.seen(world,id,760957.64,85,797904.79,86.7,true,false);
        assertFalse(safe(gate.unloaded(world,id,760957.64,95,797904.79)),"Use the latest real position, never the original low one");
        gate.seen(world,id,760957.64,26,797904.79,27.7,false,false);
        assertFalse(safe(gate.unloaded(world,id,760957.64,95,797904.79)),"A now-charged or non-creeper entity is unsafe");
        gate.seen(world,id,760957.64,26,797904.79,27.7,true,true);
        assertFalse(safe(gate.unloaded(world,id,760957.64,95,797904.79)),"Last observed fuse state cannot be discarded");
    }
    @Test void reloadNearOrVisibleMustReenterDefenseAndOtherThreatsOrDamageBlockDeparture(){
        UUID id=verifiedCreeper();assertTrue(safe(gate.unloaded(world,id,760957.64,95,797904.79)));
        var near=new BorerCombatSeparation.Threat(true,true,false,false,6,4,true);
        var visible=new BorerCombatSeparation.Threat(true,true,true,false,24,22,true);
        assertFalse(gate.observe(world,21,safe(near)));assertFalse(safe(visible));
        var departed=gate.unloaded(world,id,760957.64,95,797904.79);
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,true,List.of(departed)));
        assertFalse(BorerCombatSeparation.safe(true,true,false,false,false,List.of(departed)));
        gate.clear();assertNull(gate.lastVerified(world,id));assertFalse(safe(gate.unloaded(world,id,760957.64,95,797904.79)));
    }

    @Test void aNewLoadedUuidCannotInheritAnotherCreepersCompletedQuietWindow(){
        verifiedCreeper();UUID newcomer=UUID.randomUUID();
        gate.seen(world,newcomer,0,26,0,27.7,true,false);gate.verifyDeferred(world,List.of(newcomer));
        assertNull(gate.lastVerified(world,newcomer));assertFalse(gate.observe(world,21,true));
        assertTrue(gate.observe(world,41,true));gate.verifyDeferred(world,List.of(newcomer));
        assertNotNull(gate.lastVerified(world,newcomer));
    }

}
