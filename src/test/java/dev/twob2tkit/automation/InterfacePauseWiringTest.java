package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Inspect the real compiled input/operation paths without opening a game. */
class InterfacePauseWiringTest {
    private ClassNode clazz(String name)throws Exception{
        var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+name+".class")){
            assertNotNull(in);new ClassReader(in).accept(n,0);
        }return n;
    }
    private MethodNode method(String cls,String name)throws Exception{return clazz(cls).methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private MethodNode bridge(String name)throws Exception{return method("automation/AutomationBridge",name);}
    private List<String> calls(MethodNode method){var out=new ArrayList<String>();for(var n:method.instructions)if(n instanceof MethodInsnNode m)out.add(m.name);return out;}
    private Set<String> written(MethodNode method){var out=new HashSet<String>();for(var n:method.instructions)if(n instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTSTATIC)out.add(f.name);return out;}
    @Test void screenPauseRunsBeforeEveryTaskInputAndCanNeverCancelTheLease()throws Exception{
        var c=calls(bridge("beforeInput"));
        assertTrue(c.indexOf("interfacePaused")<c.indexOf("emergencyStop"));
        assertTrue(c.indexOf("pauseInterfaceInput")<c.indexOf("input"));
        var pause=calls(bridge("pauseInterfaceInput"));
        assertTrue(pause.containsAll(List.of("pause","movementKeys","setDown","stopDestroyBlock")));
        assertFalse(pause.contains("stop")||pause.contains("close")||pause.contains("cancelWork")||pause.contains("disarmGuard")||pause.contains("releaseUsingItem"));
        assertFalse(written(bridge("pauseInterfaceInput")).contains("active"));
        assertFalse(written(bridge("pauseInterfaceInput")).contains("supervisionLease"));
        for(var n:bridge("pauseInterfaceInput").instructions)if(n instanceof FieldInsnNode f)assertNotEquals("keyUse",f.name,"Meteor AutoEat owns its survival use input");
    }
    @Test void pausedTickFreezesOperationTimeBeforeObservationAndStillRunsTheSafetySupervisor()throws Exception{
        var tick=calls(bridge("tick"));
        assertTrue(tick.indexOf("tickInterfacePause")<tick.indexOf("tickRockQuarry"));
        var c=calls(bridge("tickInterfacePause"));
        assertTrue(c.containsAll(List.of("pauseInterfaceInput","tickSupervision","writeStatus")));
        assertFalse(c.contains("finish")||c.contains("cancelWork")||c.contains("dispatch")||c.contains("tick"));
        assertTrue(written(bridge("tickInterfacePause")).containsAll(Set.of("deadline","concretePickupDeadline","dryPavingConfirmedTick","dryPavingClientAirTick")));
        assertFalse(written(bridge("tickInterfacePause")).contains("active"));
        assertFalse(written(bridge("tickInterfacePause")).contains("phase"));
    }
    @Test void projectionConcreteAndEndTickActionsRespectThePauseButSafetyRunsFirst()throws Exception{
        var c=calls(method("KitClient","tickNavigation"));
        assertTrue(c.indexOf("handleHeldKeys")<c.indexOf("beforeInput"));
        assertTrue(c.indexOf("yieldGuardToManualInput")<c.indexOf("beforeInput"));
        boolean inputSeen=false;int taskTicks=0;
        for(var n:method("KitClient","tickNavigation").instructions)if(n instanceof MethodInsnNode m){
            if(m.name.equals("beforeInput"))inputSeen=true;
            if(m.name.equals("tick")&&(m.owner.endsWith("/ProjectionBuildJob")||m.owner.endsWith("/ConcreteMaker")||m.owner.endsWith("/TunnelBorer")||m.owner.endsWith("/CruiseController"))){
                assertTrue(inputSeen,m.owner+" task must follow common input gate");taskTicks++;
            }
        }
        assertTrue(taskTicks>=3);
        c=calls(method("KitClient","onEndTick"));
        int paused=c.indexOf("interfacePaused");assertTrue(paused>c.indexOf("handleHeldKeys"));
        int machine=-1,index=0;
        for(var n:method("KitClient","onEndTick").instructions)if(n instanceof MethodInsnNode m){
            if(m.owner.endsWith("/MachineBuilder")&&m.name.equals("tick"))machine=index;
            index++;
        }
        assertTrue(machine>paused);
    }
    @Test void queuedWriteCannotDispatchFromAnOpenPassiveScreenAndSnapshotExposesThePause()throws Exception{
        var c=calls(bridge("nativeMaterialRunQueued"));
        assertTrue(c.indexOf("interfacePaused")<c.indexOf("dispatch"));
        c=calls(bridge("tick"));assertTrue(c.containsAll(List.of("deferInterfaceRequest","resumeInterfaceRequest","interfaceReadOrStop")));
        assertTrue(calls(bridge("snapshot")).contains("interfacePaused"));
        var pause=bridge("interfacePaused");
        assertTrue(Arrays.stream(pause.instructions.toArray()).anyMatch(n->n instanceof TypeInsnNode t&&t.getOpcode()==Opcodes.INSTANCEOF&&t.desc.endsWith("/AbstractContainerScreen")));
    }
}
