package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class HorseNudgeWiringTest {
    private ClassNode clazz(String name)throws Exception{
        var node=new ClassNode();
        try(var input=getClass().getResourceAsStream("/dev/twob2tkit/automation/"+name+".class")){
            assertNotNull(input);new ClassReader(input).accept(node,0);
        }
        return node;
    }
    private MethodNode method(String owner,String name)throws Exception{
        return clazz(owner).methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<MethodInsnNode> calls(MethodNode method){
        var result=new ArrayList<MethodInsnNode>();
        for(var instruction:method.instructions)if(instruction instanceof MethodInsnNode call)result.add(call);
        return result;
    }
    private int index(List<MethodInsnNode> calls,String name){
        for(int i=0;i<calls.size();i++)if(calls.get(i).name.equals(name))return i;return -1;
    }

    @Test void packetHelperHasExactlyOneAttackCallAndRestoresTheSlot()throws Exception{
        var calls=calls(method("HorseNudgeAction","attackOnce"));
        assertEquals(1,calls.stream().filter(call->call.owner.equals("net/minecraft/client/multiplayer/MultiPlayerGameMode")
            &&call.name.equals("attack")).count());
        assertTrue(calls.stream().filter(call->call.name.equals("setSelectedSlot")).count()>=2);
        assertTrue(calls.stream().anyMatch(call->call.name.equals("twob2tkit$syncSelectedSlot")));
    }

    @Test void bridgeClaimsBeforeOneAttackAndTickOnlyObserves()throws Exception{
        var start=calls(method("AutomationBridge","startHorseNudge"));
        assertTrue(index(start,"canonicalKey")>=0&&index(start,"canonicalKey")<index(start,"claim"));
        assertTrue(index(start,"claim")>=0&&index(start,"claim")<index(start,"attackOnce"));
        var tick=calls(method("AutomationBridge","tickHorseNudge"));
        assertFalse(tick.stream().anyMatch(call->call.name.equals("attackOnce")||call.name.equals("attack")));
        assertTrue(tick.stream().anyMatch(call->call.name.equals("outcome")));
    }

    @Test void nativePathUsesExactHorsePolicyAndKeepsPveAura()throws Exception{
        var start=calls(method("AutomationBridge","startHorseNudge"));
        var names=start.stream().map(call->call.name).toList();
        assertTrue(names.containsAll(List.of("externalMaterialScope","scopeValid","horseNudgeTarget",
            "exactObservation","geometryRejection","escapeRejection","safeEmptyHandHit",
            "enablePveAura","attackOnce")));
        assertFalse(dev.twob2tkit.combat.PveAuraPolicy.allowed("minecraft:horse"));
    }

    @Test void nativeEscapeChecksLoadedCollisionSolidGroundFluidBorderAndPlayers()throws Exception{
        var calls=calls(method("HorseNudgeAction","escapeRejection")).stream().map(call->call.name).toList();
        assertTrue(calls.containsAll(List.of("isWithinBounds","getEntitiesOfClass","loaded","noCollision",
            "isCollisionShapeFullBlock","getFluidState")));
        var start=calls(method("AutomationBridge","startHorseNudge")).stream().map(call->call.name).toList();
        assertTrue(start.containsAll(List.of("isBaby","isVehicle","isPassenger","isLeashed",
            "onGround","hasLineOfSight")));
    }

    @Test void hostAdvertisesProtocolAndPersistsTerminalEvidence()throws Exception{
        MethodNode snapshot=method("AutomationBridge","snapshot");boolean advertised=false;
        for(var instruction:snapshot.instructions){
            if(instruction instanceof LdcInsnNode key&&"horse_nudge_protocol".equals(key.cst)){
                var value=instruction.getNext();while(value!=null&&value.getOpcode()<0)value=value.getNext();
                advertised=value!=null&&value.getOpcode()==Opcodes.ICONST_1;break;
            }
        }
        assertTrue(advertised);
        var finish=calls(method("AutomationBridge","finish")).stream().map(call->call.name).toList();
        assertTrue(finish.containsAll(List.of("path","update","save")));
    }
}
