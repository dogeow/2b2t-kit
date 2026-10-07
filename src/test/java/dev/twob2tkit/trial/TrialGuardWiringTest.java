package dev.twob2tkit.trial;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Inspect the compiled host wiring without creating or launching Minecraft. */
class TrialGuardWiringTest {
    private ClassNode clazz(String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+name+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }return node;
    }
    private MethodNode method(String owner,String name)throws Exception{
        return clazz(owner).methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method){
        var result=new ArrayList<String>();for(var i:method.instructions)
            if(i instanceof MethodInsnNode call)result.add(call.name);return result;
    }
    @Test void actualDefenseIsComputedBeforeOnlyTheRecoveryWindowIsScoped()throws Exception{
        var calls=calls(method("automation/AutomationBridge","beforeGuard"));
        assertTrue(calls.indexOf("tickStandaloneGuard")<calls.indexOf("trialHealthRecoveryEnabled"));
        assertTrue(calls.indexOf("trialHealthRecoveryEnabled")<calls.lastIndexOf("hold"));
        var policy=calls(method("automation/AutomationBridge","trialHealthRecoveryEnabled"));
        assertTrue(policy.containsAll(List.of("trialFlag","trialOwner","trialScope","healthRecoveryEnabled")));
        assertFalse(policy.contains("acknowledge"));assertFalse(policy.contains("safeLogout"));
        assertFalse(policy.contains("disarmGuard"));assertFalse(policy.contains("setDown"));
    }
    @Test void currentOwnerComesFromActualRegisteredWorldAndAliveRun()throws Exception{
        var calls=calls(method("trial/SingleplayerTrialRuntime","currentOwner"));
        assertTrue(calls.containsAll(List.of("registeredHere","activeHere","isBoolean")));
        var world=calls(method("trial/SingleplayerTrialRuntime","registeredHere"));
        assertTrue(world.containsAll(List.of("getSingleplayerServer","getCurrentServer","isPublished","getPlayerMode","isHardcore","worldId","world")));
    }
    @Test void flightFilterConsultsExactNativeChopAndLeavesAllOtherDisabledModules()throws Exception{
        var runtime=clazz("trial/SingleplayerTrialRuntime");
        assertTrue(calls(method("trial/SingleplayerTrialRuntime","tick")).contains("ownedTrialChop"));
        var filter=runtime.methods.stream().filter(m->m.name.startsWith("lambda$tick$")
            &&calls(m).contains("disableModule")).findFirst().orElseThrow();
        assertTrue(calls(filter).contains("equals"));
        assertTrue(java.util.stream.StreamSupport.stream(filter.instructions.spliterator(),false).anyMatch(i->
            i instanceof LdcInsnNode c&&"meteordevelopment.meteorclient.systems.modules.movement.Flight".equals(c.cst)));
        var chop=calls(method("automation/AutomationBridge","ownedTrialChop"));
        assertTrue(chop.containsAll(List.of("trialOwner","trialScope","ownedChop","isActive")));
    }
    @Test void exactChopperStopsAndReleasesOwnedKeysBeforeItsBridgeReceiptFinishes()throws Exception{
        var stop=method("automation/AutomationBridge","stopTrialInputs");var calls=calls(stop);
        assertTrue(calls.indexOf("stopOwnedChop")<calls.indexOf("stop"));
        assertTrue(calls.indexOf("stop")<calls.indexOf("setDown"));
        assertTrue(calls.indexOf("setDown")<calls.indexOf("finish"));
        assertFalse(calls.contains("emergencyStop"));assertFalse(calls.contains("stopWork"));
        var keys=new HashSet<String>();for(var i:stop.instructions)if(i instanceof FieldInsnNode field&&field.name.startsWith("key"))keys.add(field.name);
        assertEquals(Set.of("keyUp","keyDown","keyLeft","keyRight","keyJump","keyShift","keySprint","keyAttack"),keys);
        assertFalse(keys.contains("keyUse"),"Guard/AutoEat use input is not the chopper's lease");
    }
}
