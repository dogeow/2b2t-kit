package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import java.util.HashSet;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.automation.ParkingLeasePolicy.Action.*;

final class ParkingLeasePolicyTest {
    @Test void verifiedParkingPersistsWithoutAControllerHeartbeat(){
        assertEquals(KEEP,ParkingLeasePolicy.decide("parking",true,true,false,true));
    }

    @Test void unsafeParkingLogsOutButChangedScopeOrManualInputOnlyRevokes(){
        assertEquals(LOGOUT,ParkingLeasePolicy.decide("parking",true,true,false,false));
        assertEquals(REVOKE,ParkingLeasePolicy.decide("materials",true,true,false,true));
        assertEquals(REVOKE,ParkingLeasePolicy.decide("parking",false,true,false,true));
        assertEquals(REVOKE,ParkingLeasePolicy.decide("parking",true,false,false,true));
        assertEquals(REVOKE,ParkingLeasePolicy.decide("parking",true,true,true,true));
    }

    @Test void remoteCombatFinishRemainsAClosingMaterialLeaseAcrossTicks(){
        assertEquals(ParkingLeasePolicy.QuietWait.START,
            ParkingLeasePolicy.quietWait(true,false,false,false));
        assertEquals(ParkingLeasePolicy.QuietWait.KEEP,
            ParkingLeasePolicy.quietWait(true,false,false,true));
        assertEquals(ParkingLeasePolicy.QuietWait.NONE,
            ParkingLeasePolicy.quietWait(true,false,true,true));
        assertEquals(ParkingLeasePolicy.QuietWait.NONE,
            ParkingLeasePolicy.quietWait(true,true,false,true));
        assertEquals(ParkingLeasePolicy.QuietWait.NONE,
            ParkingLeasePolicy.quietWait(false,false,false,false));
    }

    @Test void bothExternalAndNativeFinishPathsRetainTheParkingLease()throws Exception{
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        for(String methodName:new String[]{"tickSupervision","nativeMaterialFinish"}){
            var method=node.methods.stream().filter(m->m.name.equals(methodName)).findFirst().orElseThrow();
            var calls=new HashSet<String>();
            for(var instruction:method.instructions)
                if(instruction instanceof MethodInsnNode call)calls.add(call.owner+"."+call.name);
            assertTrue(calls.contains("dev/twob2tkit/automation/AutomationBridge.retainParkingLease"),methodName);
        }
    }

	@Test void verifiedCurrentHoverReplacesAStaleResidualDriftTarget(){
		assertFalse(GuardParkingPolicy.ready(109.0,95,200.5,100.5,95,200.5,
			65,20,true,true));
		var anchor=ParkingLeasePolicy.reanchor(109.0,95,200.5,65,20,true,true);
		assertNotNull(anchor);assertEquals(109.0,anchor.x());
		assertTrue(GuardParkingPolicy.ready(109.0,95,200.5,
			anchor.x(),anchor.y(),anchor.z(),65,20,true,true));
		assertNull(ParkingLeasePolicy.reanchor(109.0,75,200.5,65,20,true,true));
		assertEquals(100,ParkingLeasePolicy.reanchor(10,98,20,80,20,true,true).y());
		assertEquals(100,ParkingLeasePolicy.reanchor(10,99,20,80,20,true,true).y());
		assertEquals(100,ParkingLeasePolicy.reanchor(10,100,20,80,20,true,true).y());
		assertEquals(102,ParkingLeasePolicy.reanchor(10,102,20,80,20,true,true).y());
		assertNull(ParkingLeasePolicy.reanchor(10,97,20,80,20,true,true));
	}

	@Test void parkingGuardUsesOnlyTheVerifiedFixedParkingTarget(){
		assertTrue(ParkingLeasePolicy.guardRebase("parking",true,true,false,true,true,true));
		assertFalse(ParkingLeasePolicy.guardRebase("parking",true,true,true,true,true,true));
		assertFalse(ParkingLeasePolicy.guardRebase("parking",true,true,false,true,false,true));
		assertFalse(ParkingLeasePolicy.guardRebase("materials",true,true,false,true,true,true));
		assertFalse(ParkingLeasePolicy.guardRebase("parking",true,true,false,true,true,false));
	}
}
