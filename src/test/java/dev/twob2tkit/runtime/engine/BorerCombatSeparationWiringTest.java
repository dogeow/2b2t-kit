package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class BorerCombatSeparationWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(String cls,String name)throws Exception{
        var result=new ArrayList<String>();
        for(var i:method(cls,name).instructions){
            if(i instanceof MethodInsnNode c)result.add(c.name);
            if(i instanceof InvokeDynamicInsnNode dynamic)for(var arg:dynamic.bsmArgs)
                if(arg instanceof Handle handle&&handle.getOwner().endsWith("/"+cls)&&handle.getName().startsWith("lambda$"))result.addAll(calls(cls,handle.getName()));
        }
        return result;
    }
    @Test void safeDecisionUsesLivePresenceFlightHealthLosBodyAndThreatChecks()throws Exception{
        var c=calls("BorerRangedCombat","safeVerticalSeparation");assertTrue(c.containsAll(List.of("getEntity","isAlive","isPowered","hasLineOfSight","swelling","eligible","creeperAlert","getHealth","isInWater","isInLava","isOnFire","safeAir","noCollision","meteorFlightActive","observe")));
        assertFalse(c.contains("clear"));assertFalse(c.contains("end"));
    }
    @Test void ordinaryTaskSwitchesPreserveOnlySameWorldDeferredSession()throws Exception{
        for(String method:List.of("start","stop","beginReturn","suspendStandaloneCombatForAirReturn")){
            assertTrue(calls("DefaultTunnelBorerEngine",method).contains("handoff"));assertFalse(calls("DefaultTunnelBorerEngine",method).contains("end"));
        }
        var c=calls("BorerRangedCombat","handoff");assertTrue(c.containsAll(List.of("pending","retain","releaseControls","pause","save","end")));
        assertTrue(c.indexOf("retain")<c.indexOf("releaseControls"));assertTrue(c.indexOf("save")<c.indexOf("end"));
    }
    @Test void explicitDisarmClearsBeforeTheActiveMinerEarlyReturn()throws Exception{
        var m=method("DefaultTunnelBorerEngine","tickStandaloneGuard");int index=0,end=-1,active=-1;
        for(var i:m.instructions){if(i instanceof MethodInsnNode c&&c.name.equals("end")&&end<0)end=index;
            if(i instanceof FieldInsnNode f&&f.name.equals("active")&&active<0)active=index;index++;}
        assertTrue(end>=0&&end<active,"Disarm cannot be skipped merely because native mining is still active");
        assertTrue(calls("BorerRangedCombat","end").stream().filter("clear"::equals).count()>=3);
    }
    @Test void worldChangeIsCheckedBeforeAnyRestoredOrRememberedObservation()throws Exception{
        var c=calls("BorerRangedCombat","tick");assertTrue(c.indexOf("end")<c.indexOf("restore"));
        boolean check=false;for(var i:method("BorerRangedCombat","tick").instructions)if(i instanceof FieldInsnNode f&&f.name.equals("combatWorld"))check=true;assertTrue(check);
    }
    @Test void unloadedTargetsUsePerUuidProofAndLoadedTargetsRefreshRealEvidence()throws Exception{
        var c=calls("BorerRangedCombat","safeVerticalSeparation");
        assertTrue(c.containsAll(List.of("getEntity","isAlive","currentServerChunk","getUUID","unloaded","seen","verifyDeferred")));
        assertTrue(c.indexOf("observe")<c.indexOf("verifyDeferred"),"Do not authorize an unknown UUID before the safety window has completed");
        assertFalse(c.contains("end"));assertFalse(c.contains("clear"));
        assertTrue(calls("BorerCombatSeparation","unloaded").contains("lastVerified"));
    }

    @Test void unarmedWatchRequiresExactCurrentWeaponsDamageAndFullActualBody()throws Exception{
        var c=calls("BorerRangedCombat","safeVerticalSeparation");
        assertTrue(c.containsAll(List.of("ordinaryZombie","getMainHandItem","getOffhandItem","isEmpty",
            "currentReceivedMobHit","recentlyHurt","shouldYieldToCombat","finiteVector","finiteBox",
            "clearSeparationBody","currentServerChunk")));
        assertTrue(calls("BorerRangedCombat","ordinaryZombie").contains("isRangedCombatThreat"));
        var body=calls("BorerRangedCombat","clearSeparationBody");
        assertTrue(body.containsAll(List.of("position","getDeltaMovement","getBoundingBox","finiteVector","finiteBox",
            "noCollision","betweenClosed","safeAir")));
        assertTrue(body.indexOf("finiteBox")<body.indexOf("betweenClosed"));
        assertTrue(calls("BorerRangedCombat","currentServerChunk").contains("isServerChunk"));
        assertFalse(body.contains("attack"));assertFalse(body.contains("setPos"));
        assertFalse(c.contains("clear"));assertFalse(c.contains("end"));
    }

}
