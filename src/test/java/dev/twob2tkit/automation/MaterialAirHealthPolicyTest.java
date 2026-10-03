package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import static org.junit.jupiter.api.Assertions.*;

final class MaterialAirHealthPolicyTest {
    @Test void firstMinorInjuryInterruptsRatherThanWaitingForTheNinetySecondDeadline(){
        assertTrue(MaterialAirHealthPolicy.interrupted(20,100,19.5f,101));
        assertTrue(MaterialAirHealthPolicy.interrupted(20,100,19.64f,100));
        assertTrue(MaterialAirHealthPolicy.interrupted(20,100,20,101));
    }
    @Test void underwaterEscapeContinuesUntilBreathingBeforeAnInjuryStop(){
        assertFalse(MaterialAirHealthPolicy.interruptible(true,52,65));
        assertTrue(MaterialAirHealthPolicy.interruptible(false,65,65));
        assertTrue(MaterialAirHealthPolicy.interruptible(true,65,52));
        assertTrue(MaterialAirHealthPolicy.interruptible(false,144,65.6));
    }
    @Test void healthyWaypointAndHealingDoNotInterrupt(){
        assertFalse(MaterialAirHealthPolicy.interrupted(20,100,20,100));
        assertFalse(MaterialAirHealthPolicy.interrupted(18,100,19,100));
    }
    @Test void invalidOrDeadHealthNeverProvesAHealthyWaypoint(){
        assertTrue(MaterialAirHealthPolicy.interrupted(20,100,Float.NaN,100));
        assertTrue(MaterialAirHealthPolicy.interrupted(Float.NaN,100,20,100));
        assertTrue(MaterialAirHealthPolicy.interrupted(20,100,0,100));
    }
    @Test void injuryCheckRunsBeforeInputAndDuringTickWithoutDisarmingDefense()throws Exception{
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        for(var name:new String[]{"beforeInput","tick"}){
            var m=node.methods.stream().filter(v->v.name.equals(name)).findFirst().orElseThrow();
            assertTrue(java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false)
                .anyMatch(i->i instanceof MethodInsnNode call&&call.name.equals("stopInjuredAirNavigation")),name);
        }
        var m=node.methods.stream().filter(v->v.name.equals("stopInjuredAirNavigation")).findFirst().orElseThrow();
        var calls=java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false)
            .filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
        assertTrue(calls.contains("injured"));assertTrue(calls.contains("finish"));
        assertFalse(calls.contains("emergencyStop"));assertFalse(calls.contains("disarmGuard"));
    }
    @org.junit.jupiter.api.Test void newInjuryDoesNotFreezeAnOwnedDefensiveAscentButStillStopsOtherAirWork(){
        org.junit.jupiter.api.Assertions.assertFalse(MaterialAirHealthPolicy.interruptible(false,74,106,true));
        org.junit.jupiter.api.Assertions.assertFalse(MaterialAirHealthPolicy.interruptible(false,106.1,106,true));
        org.junit.jupiter.api.Assertions.assertTrue(MaterialAirHealthPolicy.interruptible(false,74,106,false));
        org.junit.jupiter.api.Assertions.assertTrue(MaterialAirHealthPolicy.interruptible(false,110,106,true));
    }
}
