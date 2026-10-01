package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

/** The local UI adapter must keep ownership through each existing native child. */
class NativeMaterialSessionWiringTest {
    private MethodNode method(String owner,String name)throws Exception{
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+owner+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method){
        var result=new ArrayList<String>();
        for(var instruction:method.instructions)
            if(instruction instanceof MethodInsnNode invoke)result.add(invoke.name);
        return result;
    }
    @Test void submitQueuesAndOnlyBridgeTickDispatches(){
        try{
            assertFalse(calls(method("automation/AutomationBridge","nativeMaterialSubmit")).contains("dispatch"));
            assertTrue(calls(method("automation/AutomationBridge","nativeMaterialRunQueued")).contains("dispatch"));
            assertTrue(calls(method("automation/AutomationBridge","tick")).contains("nativeMaterialRunQueued"));
        }catch(Exception e){throw new AssertionError(e);}
    }
	@Test void internalCruiseKeepsLeaseAndSynchronizesRevisionBeforeStartExact()throws Exception{
		var handoff=calls(method("automation/AutomationBridge","userTaskStarting"));
		assertTrue(handoff.contains("internalDispatch"));
		var internal=method("automation/AutomationBridge","internalDispatch");
		var readFlags=new java.util.HashSet<String>();
		for(var instruction:internal.instructions)
			if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
					&&field.getOpcode()==org.objectweb.asm.Opcodes.GETSTATIC)readFlags.add(field.name);
		assertTrue(readFlags.containsAll(List.of("nativeMaterialDispatch","materialHandoffDispatch")));
		var dispatch=calls(method("automation/AutomationBridge","dispatch"));
		int handoffCall=dispatch.indexOf("stopWorkForScript");
		assertTrue(handoffCall>=0);
		assertTrue(dispatch.subList(handoffCall+1,dispatch.size()).contains("startExact"));
		var stop=method("automation/AutomationBridge","stopWorkForScript");
		var stopCalls=calls(stop);
		assertTrue(stopCalls.indexOf("stopWork")<stopCalls.indexOf("syncMaterialRevision"));
		assertFalse(stop.tryCatchBlocks.isEmpty(),"revision sync must run from finally after a stop failure");
		var syncMethod=method("automation/AutomationBridge","syncMaterialRevision");
		boolean ownerRevision=false,leaseRevision=false;
		for(var instruction:syncMethod.instructions){
			if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
					&&field.name.equals("revision")&&field.getOpcode()==org.objectweb.asm.Opcodes.PUTFIELD)
				ownerRevision=true;
			if(instruction instanceof MethodInsnNode call&&call.name.equals("addProperty"))leaseRevision=true;
		}
		assertTrue(ownerRevision&&leaseRevision);
		var tick=calls(method("automation/AutomationBridge","tick"));
		assertTrue(tick.indexOf("nativeMaterialRunQueued")>=0);
		assertTrue(tick.indexOf("nativeMaterialRunQueued")<tick.indexOf("nativeMaterialTickCheck"));
		assertTrue(tick.contains("currentMaterialRequest"),
			"external file dispatch must derive handoff from the exact live material lease");
		var monitor=calls(method("automation/AutomationBridge","nativeMaterialTickCheck"));
		assertTrue(monitor.containsAll(List.of("nativeMaterialCheck","stop","releaseWalk",
			"stopWork","nativeMaterialReceipt")));
		var monitorMethod=method("automation/AutomationBridge","nativeMaterialTickCheck");
		int stopIndex=-1,activeClear=-1,index=0;
		for(var instruction:monitorMethod.instructions){
			if(instruction instanceof MethodInsnNode call&&call.name.equals("stopWork"))stopIndex=index;
			if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
					&&field.name.equals("active")&&field.getOpcode()==org.objectweb.asm.Opcodes.PUTSTATIC)
				activeClear=index;
			index++;
		}
		assertTrue(stopIndex>=0&&activeClear>stopIndex,
			"standard cancelWork must observe exact active/op before it is cleared");
	}
	@Test void malformedExternalScopeCannotLeakDispatchFlags()throws Exception{
		var tick=method("automation/AutomationBridge","tick");
		MethodInsnNode scope=null;
		for(var instruction:tick.instructions)
			if(instruction instanceof MethodInsnNode call&&call.name.equals("currentMaterialRequest")){scope=call;break;}
		assertNotNull(scope);int scopeIndex=tick.instructions.indexOf(scope);
		assertTrue(tick.tryCatchBlocks.stream().anyMatch(block->{
			int start=tick.instructions.indexOf(block.start),end=tick.instructions.indexOf(block.end);
			return start<=scopeIndex&&scopeIndex<end;
		}),"task_session parsing and context setup must be inside the restoring finally");
		int dispatchWrites=0,handoffWrites=0;
		for(var instruction:tick.instructions)
			if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
					&&field.getOpcode()==org.objectweb.asm.Opcodes.PUTSTATIC){
				if(field.name.equals("dispatching"))dispatchWrites++;
				if(field.name.equals("materialHandoffDispatch"))handoffWrites++;
			}
		assertTrue(dispatchWrites>=2&&handoffWrites>=2);
		assertTrue(calls(tick).containsAll(List.of("snapshot","save")),
			"malformed schema must still reach the exact error reply path");
	}
    @Test void ownedInterruptRetainsLeaseAndSafeLogoutDisablesReconnectFirst()throws Exception{
        var interrupt=calls(method("automation/AutomationBridge","nativeMaterialInterrupt"));
        assertTrue(interrupt.containsAll(List.of("nativeMaterialCheck","stopWork","nativeMaterialReceipt")));
        var logout=calls(method("automation/AutomationBridge","nativeMaterialSafeLogout"));
        assertTrue(logout.indexOf("nativeMaterialCheck")<logout.indexOf("suspendAutoReconnect"));
        assertTrue(logout.indexOf("suspendAutoReconnect")<logout.indexOf("safeLogout"));
        var finish=method("automation/AutomationBridge","nativeMaterialFinish");
        var finishCalls=calls(finish);
        assertTrue(finishCalls.contains("highGuardPark"));
        assertTrue(finishCalls.contains("retainParkingLease"));
        var parkingCalls=calls(method("automation/AutomationBridge","retainParkingLease"));
        assertTrue(parkingCalls.indexOf("stopWork")<parkingCalls.indexOf("armPveGuard"));
        var writes=new ArrayList<String>();
        for(var instruction:finish.instructions)
            if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
                    &&field.getOpcode()==org.objectweb.asm.Opcodes.PUTSTATIC)writes.add(field.name);
        assertTrue(writes.contains("nativeMaterialDispatch"),"Finish must not re-enter the collector stop hook");
    }
    @Test void publicAdapterExposesOwnedLifecycle()throws Exception{
        var methods=NativeMaterialSession.class.getMethods();
        var names=new java.util.HashSet<String>();for(var method:methods)names.add(method.getName());
        assertTrue(names.containsAll(List.of("open","submit","poll","snapshot","busy",
            "interrupt","finish","cancel","safeLogout")));
        assertTrue(calls(method("automation/AutomationBridge","nativeMaterialCheck"))
            .containsAll(List.of("session","manualMovementDown","guardArmed")));
    }

    @Test void materialSessionFreezesAHostOwnedReturnTarget()throws Exception{
        var dispatch=calls(method("automation/AutomationBridge","dispatch"));
        assertTrue(dispatch.contains("homeTarget"),
            "The native host must read the one configured Home itself");
        assertTrue(dispatch.contains("materialReturnTarget"),
            "The immutable return target must be written while the lease is created");
    }

    @Test void waterPreflightAcceptsFlowingWaterAndChecksFlowingLava()throws Exception{
        var fields=new ArrayList<String>();
        for(var instruction:method("automation/AutomationBridge","dispatch").instructions)
            if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
                    &&field.owner.equals("net/minecraft/tags/FluidTags"))fields.add(field.name);
        assertTrue(fields.contains("WATER"));
        assertTrue(fields.contains("LAVA"));
    }
    @Test void gravelLocalApiUsesCollectorAndChecksWorldScope()throws Exception{
        var dispatch=calls(method("automation/AutomationBridge","dispatch"));
        assertTrue(dispatch.containsAll(List.of("gravelScope","configureGravel","start","stop")));
        assertTrue(calls(method("automation/AutomationBridge","gravelScope")).contains("session"));
        var start=calls(method("automation/GravelCollector","start"));
        assertTrue(start.contains("open"),"Gravel must acquire the native material session directly");
        assertFalse(start.contains("stopWork"),
            "Stopping work first invalidates a retained parking revision before it can be replaced");
    }
}
