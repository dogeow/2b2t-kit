package dev.twob2tkit.material;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class MaterialTaskWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}return node.methods.stream().filter(m->m.name.equals(name)&&(!name.equals("control")||m.desc.startsWith("(Lnet/minecraft/client/Minecraft;"))).findFirst().orElseThrow();}
    private List<String> calls(MethodNode method){var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode c)result.add(c.name);return result;}
    @Test void sidebandDispatchDelegatesToTheExistingLifecycleWithoutReplacingGameplayRequestState()throws Exception{
        var method=method("automation/AutomationBridge","materialTaskReply");var c=calls(method);
        assertTrue(c.containsAll(List.of("parse","requireScope","materialJobContext","lockedBuildSelection","startItem","startProjection","control","snapshot")));
        for(var instruction:method.instructions)if(instruction instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTSTATIC)
            assertFalse(Set.of("lastId","statusId","active","phase","op").contains(f.name));
        assertFalse(c.contains("dispatch"));assertFalse(c.contains("save"));
        assertTrue(calls(method("automation/AutomationBridge","tick")).contains("pollMaterialTasks"));
    }
    @Test void startAndResumeCheckSafetyBeforeClosingAnyScreenAndSpawning()throws Exception{
        var start=calls(method("material/MaterialJobs","start"));assertTrue(start.indexOf("occupied")<start.indexOf("start"));
        assertTrue(start.indexOf("materialJobContext")<start.indexOf("setScreen"));assertTrue(start.indexOf("materialJobContext")<start.indexOf("start"));
        var resume=calls(method("material/MaterialJobs","resume"));assertTrue(resume.indexOf("held")<resume.indexOf("setScreen"));assertTrue(resume.indexOf("materialJobContext")<resume.indexOf("setScreen"));
        var scope=calls(method("automation/AutomationBridge","materialJobContext"));assertTrue(scope.containsAll(List.of("held","manualMovementDown","getHealth","anyAfkAuto")));
    }
    @Test void itemAndProjectionValidationAreSharedWithUi()throws Exception{
        assertTrue(calls(method("material/MaterialJobs","startItem")).contains("validateItem"));assertTrue(calls(method("material/MaterialJobs","startProjection")).contains("lockedBuildSelection"));
        assertTrue(calls(method("material/MaterialJobs","resume")).contains("lockedBuildSelection"));
        var control=calls(method("material/MaterialJobs","control"));assertTrue(control.containsAll(List.of("requireJob","pause","resume","cancel")));assertTrue(control.indexOf("requireJob")<control.indexOf("pause"));
    }
    @Test void preciseWorkerSnapshotIsPureAndStopUsesOwnedHandle()throws Exception{
        var snapshot=method("material/MaterialJobs","snapshot");assertTrue(calls(snapshot).containsAll(List.of("alive","occupied")));
        assertFalse(calls(snapshot).contains("start"));assertFalse(calls(snapshot).contains("tick"));
        assertTrue(calls(method("material/MaterialJobs","stop")).contains("stop"));
        assertTrue(calls(method("KitClient","stopAll")).contains("stop"));
    }
}
