package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class GuardRangedSafetyWiringTest {
    private MethodNode method(String owner,String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/"+owner+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(String owner,String name)throws Exception{
        var result=new ArrayList<String>();
        for(var i:method(owner,name).instructions){
            if(i instanceof MethodInsnNode call)result.add(call.name);
            if(i instanceof InvokeDynamicInsnNode dynamic)for(var arg:dynamic.bsmArgs)
                if(arg instanceof Handle handle&&handle.getOwner().endsWith("/"+owner)&&handle.getName().startsWith("lambda$"))
                    result.addAll(calls(owner,handle.getName()));
        }return result;
    }
    private int directCallIndex(String owner,String name,String calledOwner,String calledName)throws Exception{
        var instructions=method(owner,name).instructions;
        for(int i=0;i<instructions.size();i++)if(instructions.get(i) instanceof MethodInsnNode call
            &&call.owner.endsWith("/"+calledOwner)&&call.name.equals(calledName))return i;
        fail("Missing call "+calledOwner+"."+calledName);return -1;
    }
    @Test void unavailableBranchConsidersSafetyBeforeHoldPeekAttackOrBow()throws Exception{
        var calls=calls("BorerRangedCombat","tick");
        assertTrue(calls.indexOf("safetyRise")<calls.indexOf("holdForMissingObservation"));
        assertTrue(calls.indexOf("safetyRise")<calls.indexOf("attack"));
        assertTrue(calls.indexOf("safetyRise")<calls.indexOf("selectBow"));
        assertTrue(calls.contains("currentReceivedMobHit"));
    }
    @Test void safetyUsesCurrentUnresolvedObservationsAndNormalFlightWithoutAttackingOrClearing()throws Exception{
        var c=calls("BorerRangedCombat","safetyRise");
        assertTrue(c.containsAll(List.of("targets","getEntity","level","isAlive","currentServerChunk",
            "contains","isRangedCombatThreat","canAttack","hasLineOfSight","safetyRiseNeeded","remaining",
            "physicalMovementHeld","cancel","attempted","clearWholeRise","pauseGuardMovement","acquire","speed","setDown")));
        assertTrue(c.indexOf("getEntity")<c.indexOf("remaining"));assertTrue(c.indexOf("clearWholeRise")<c.indexOf("acquire"));
        assertFalse(c.contains("attack"));assertFalse(c.contains("clear"));assertFalse(c.contains("setPos"));
        assertFalse(c.contains("setDeltaMovement"));assertFalse(c.contains("enablePveMelee"));
        assertTrue(directCallIndex("BorerRangedCombat","safetyRise","BorerCombatPeek","close")
            <directCallIndex("BorerRangedCombat","safetyRise","BorerAreaFlightSession","acquire"));
    }
    @Test void wholeRiseChecksEveryActualBodyCellAndCurrentDangerousEntitiesMovingAway()throws Exception{
        var c=calls("BorerRangedCombat","clearWholeRise");
        assertTrue(c.containsAll(List.of("noCollision","betweenClosed","safeAir","getEntities","getEntity",
            "level","isAlive","currentServerChunk","riseThreatClear","getBoundingBox","finiteVector","finiteBox","getDeltaMovement")));
        assertTrue(c.indexOf("finiteVector")<c.indexOf("betweenClosed"));
        assertTrue(c.indexOf("finiteBox")<c.indexOf("betweenClosed"));
        assertTrue(calls("GuardWeaponPolicy","riseThreatClear").containsAll(List.of("intersects","boxDistanceSquared","finiteBox")));
        assertTrue(calls("BorerRangedCombat","currentServerChunk").contains("isServerChunk"));
    }
    @Test void sharedClassifierCoversPriorityRiseFoodPauseOrdinaryAndEngagement()throws Exception{
        for(String name:List.of("rank","elevateBeforeCombat","hasImmediateHostileThreat","ordinaryZombie"))
            assertTrue(calls("BorerRangedCombat",name).contains("isRangedCombatThreat"),name);
        assertTrue(calls("BorerEngagement","shouldReact").contains("isRangedCombatThreat"));
    }
    @Test void disarmWorldAndUiStillPrecedeNewSafetyInputAndResetOnlyExplicitEnd()throws Exception{
        var tick=calls("BorerRangedCombat","tick");assertTrue(tick.indexOf("end")<tick.indexOf("restore"));
        int guardTick=directCallIndex("DefaultTunnelBorerEngine","tickStandaloneGuard","BorerRangedCombat","tick");
        assertTrue(directCallIndex("DefaultTunnelBorerEngine","tickStandaloneGuard","BorerRangedCombat","end")<guardTick);
        assertTrue(directCallIndex("DefaultTunnelBorerEngine","tickStandaloneGuard","BorerRangedCombat","pause")<guardTick);
        assertTrue(calls("BorerRangedCombat","end").contains("clear"));
        assertFalse(calls("BorerRangedCombat","safetyRise").contains("end"));
    }
    @Test void evidenceUsesRealCurrentPoseBboxEquipmentDamageAndThrottledTicks()throws Exception{
        var c=calls("BorerRangedCombat","logThreatEvidence");
        assertTrue(c.containsAll(List.of("getEntity","level","position","getBoundingBox","getMainHandItem",
            "getOffhandItem","getLastDamageSource","getDirectEntity","getEntity","getMsgId","isAlive","fileLog")));
        assertFalse(c.contains("attack"));assertFalse(c.contains("setPos"));
    }
    @Test void pauseAndSafeWatchCancelOnlyTheRisePlanAndCooldownsStayIndependent()throws Exception{
        for(String name:List.of("pause","pauseForEating","handoff","tick"))
            assertTrue(calls("BorerRangedCombat",name).contains("cancel"),name);
        for(String name:List.of("safetyRise","elevateBeforeCombat","safetyDefenseAfterRiseFailure","groundDefenseAfterRiseFailure")){
            var fields=new HashSet<String>();
            for(var i:method("BorerRangedCombat",name).instructions)
                if(i instanceof FieldInsnNode field&&field.name.endsWith("RetryAfter"))fields.add(field.name);
            assertEquals(Set.of(name.startsWith("safety")?"safetyRiseRetryAfter":"riseRetryAfter"),fields,name);
        }
        var c=calls("BorerRangedCombat","safetyRise");
        assertTrue(c.indexOf("setDown")<c.indexOf("attempted"));
        var whole=calls("BorerRangedCombat","clearWholeRise");
        assertTrue(whole.indexOf("boxDistanceSquared")<whole.indexOf("currentServerChunk"));
    }

}
