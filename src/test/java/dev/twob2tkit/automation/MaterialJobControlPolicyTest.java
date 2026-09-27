package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class MaterialJobControlPolicyTest {
    @Test void pauseOnlyAppliesToTheCurrentExternalOwner(){
        assertTrue(MaterialJobControlPolicy.owned("task","task","world","world",4,4,4,5000,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("","task","world","world",4,4,4,5000,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("old","task","world","world",4,4,4,5000,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","old","world",4,4,4,5000,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","world","world",3,4,4,5000,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","world","world",4,4,3,5000,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","world","world",4,4,4,-1,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","world","world",4,4,4,15001,false,true,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","world","world",4,4,4,5000,true,true,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","world","world",4,4,4,5000,false,false,false));
        assertFalse(MaterialJobControlPolicy.owned("task","task","world","world",4,4,4,5000,false,true,true));
    }
    @Test void localParkHasARealClearColumnAndDoesNotPretendThePlayerHasArrived(){
        assertTrue(MaterialJobControlPolicy.localPark(1,64,1,1,100,1,70,20,true,true,true));
        assertFalse(MaterialJobControlPolicy.localPark(1,64,1,4,100,1,70,20,true,true,true));
        assertFalse(MaterialJobControlPolicy.localPark(1,100,1,1,99,1,70,20,true,true,true));
        assertFalse(MaterialJobControlPolicy.localPark(1,64,1,1,320,1,70,20,true,true,true));
        assertFalse(MaterialJobControlPolicy.localPark(1,64,1,1,89,1,70,20,true,true,true));
        assertFalse(MaterialJobControlPolicy.localPark(1,64,1,1,100,1,70,20,true,true,false));
        assertFalse(MaterialJobControlPolicy.localPark(1,64,1,1,100,1,70,17,true,true,true));
        assertFalse(MaterialJobControlPolicy.localPark(1,64,1,1,100,1,70,20,false,true,true));
        assertFalse(MaterialJobControlPolicy.localPark(1,64,1,Double.NaN,100,1,70,20,true,true,true));
    }
    @Test void preciseArrivalIsOnlyGrantedToAnOwnedMaterialLease(){
        assertEquals(.25,MaterialJobControlPolicy.arrival(.25,true));
        assertEquals(.2,MaterialJobControlPolicy.arrival(.01,true));
        assertEquals(1,MaterialJobControlPolicy.arrival(.25,false));
        assertThrows(IllegalArgumentException.class,()->MaterialJobControlPolicy.arrival(Double.NaN,true));
    }
    @Test void onlyCurrentVerifiedQuietParkingCanBecomeANativeMaterialSession(){
        assertTrue(MaterialJobControlPolicy.resumableParking("parking","world","world",4,4,true,true,false));
        assertFalse(MaterialJobControlPolicy.resumableParking("materials","world","world",4,4,true,true,false));
        assertFalse(MaterialJobControlPolicy.resumableParking("parking","old","world",4,4,true,true,false));
        assertFalse(MaterialJobControlPolicy.resumableParking("parking","world","world",3,4,true,true,false));
        assertFalse(MaterialJobControlPolicy.resumableParking("parking","world","world",4,4,false,true,false));
        assertFalse(MaterialJobControlPolicy.resumableParking("parking","world","world",4,4,true,false,false));
        assertFalse(MaterialJobControlPolicy.resumableParking("parking","world","world",4,4,true,true,true));
        try{
            var calls=new HashSet<String>();for(var instruction:method("nativeMaterialOpen").instructions)
                if(instruction instanceof MethodInsnNode call)calls.add(call.name);
            assertTrue(calls.containsAll(Set.of("resumableParking","highGuardPark","held")));
        }catch(Exception failure){throw new AssertionError(failure);}
    }
    private MethodNode method(String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            new ClassReader(in).accept(node,0);}
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    @Test void parkOnlyChangesLeaseMetadataAndPauseDoesNotRestartOrMove()throws Exception{
        var calls=new HashSet<String>();for(var instruction:method("updateMaterialPark").instructions)
            if(instruction instanceof MethodInsnNode call)calls.add(call.name);
        assertTrue(calls.containsAll(Set.of("localPark","noCollision","hasChunkAt","getFluidState","add")));
        assertFalse(calls.contains("startExact"));assertFalse(calls.contains("start"));
        var constants=new HashSet<String>();for(var instruction:method("dispatch").instructions)
            if(instruction instanceof LdcInsnNode value&&value.cst instanceof String text)constants.add(text);
        assertTrue(constants.containsAll(Set.of("material_job_pause","material_job_park","release")));
        var scopeCalls=new HashSet<String>();for(var instruction:method("externalMaterialScope").instructions)
            if(instruction instanceof MethodInsnNode call)scopeCalls.add(call.name);
        assertTrue(scopeCalls.containsAll(Set.of("owned","session","sameServer","manualMovementDown")));
    }
    @Test void ownedKitPageRemainsPausableWithoutRemovingManualTakeoverProtection()throws Exception{
        var menuText=new HashSet<String>();var menuCalls=new HashSet<String>();
        for(var instruction:method("nativeKitMenu").instructions){
            if(instruction instanceof LdcInsnNode value&&value.cst instanceof String text)menuText.add(text);
            if(instruction instanceof MethodInsnNode call)menuCalls.add(call.name);
        }
        assertTrue(menuText.containsAll(Set.of("materials","world_session","revision","task_session","job_session")));
        assertTrue(menuCalls.contains("session"));
        var inputCalls=new HashSet<String>();for(var instruction:method("beforeInput").instructions)
            if(instruction instanceof MethodInsnNode call)inputCalls.add(call.name);
        assertTrue(inputCalls.containsAll(Set.of("nativeKitMenu","manualMovementDown","emergencyStop","stopDestroyBlock")));
    }
    @Test void airOnlyNavigationChecksLoadedDryCollisionAndRestoresItsTemporaryPreference()throws Exception{
        var pathCalls=new HashSet<String>();for(var instruction:method("airNavigationClear").instructions)
            if(instruction instanceof MethodInsnNode call)pathCalls.add(call.name);
        assertTrue(pathCalls.containsAll(Set.of("noCollision","hasChunkAt","getFluidState")));
        var restorationFields=new HashSet<String>();for(var instruction:method("restoreArrival").instructions)
            if(instruction instanceof FieldInsnNode field)restorationFields.add(field.name);
        assertTrue(restorationFields.containsAll(Set.of("savedClearCeiling","clearCeiling","savedArrival")));
        var inputCalls=new HashSet<String>();for(var instruction:method("beforeInput").instructions)
            if(instruction instanceof MethodInsnNode call)inputCalls.add(call.name);
        assertTrue(inputCalls.contains("airNavigationClear"));
    }
}
