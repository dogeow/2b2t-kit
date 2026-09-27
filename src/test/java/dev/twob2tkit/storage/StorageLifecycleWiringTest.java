package dev.twob2tkit.storage;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class StorageLifecycleWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(String cls,String name)throws Exception{var result=new ArrayList<String>();for(var i:method(cls,name).instructions){if(i instanceof MethodInsnNode c)result.add(c.name);if(i instanceof InvokeDynamicInsnNode d)for(var arg:d.bsmArgs)if(arg instanceof Handle h&&h.getOwner().equals("dev/twob2tkit/"+cls)&&h.getName().startsWith("lambda$"))result.addAll(calls(cls,h.getName()));}return result;}
    @Test void removalPacketsScheduleRecheckAndClosedMenusStillPollTheLifecycle()throws Exception{
        assertTrue(calls("mixin/ConcreteBlockUpdatesMixin","kit$concreteBlockUpdate").contains("blockUpdated"));
        assertTrue(calls("mixin/ConcreteBlockUpdatesMixin","kit$concreteSectionUpdate").contains("blockUpdated"));
        var instructions=method("storage/ContainerAssistant","tick").instructions;
        var first=java.util.stream.StreamSupport.stream(instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->(MethodInsnNode)i).findFirst().orElseThrow();
        assertEquals("dev/twob2tkit/storage/StorageLifecycle",first.owner);assertEquals("tick",first.name);
        assertTrue(calls("storage/ContainerAssistant","recordSnapshot").contains("capture"));
    }
    @Test void supplyPermissionCandidateAndExplicitCollectionAllCheckVerifiedScope()throws Exception{
        for(String name:List.of("sourceEnabled","toggleSource","sources","approvedSource"))assertTrue(calls("automation/BuildSupplyTask",name).contains("usable"),name);
        assertTrue(calls("storage/StorageLifecycle","usable").containsAll(List.of("sameScope","observe")));
    }
    @Test void legacyPruneNoLongerDeletesAndRecordReplacementKeepsHistory()throws Exception{
        assertFalse(calls("KitConfig","pruneMissingStorage").contains("removeIf"));assertTrue(calls("KitConfig","pruneMissingStorage").contains("refresh"));
        assertTrue(calls("KitConfig","upsertStorageSnapshot").containsAll(List.of("scopedKey","inherit")));
        assertTrue(calls("KitConfig","patchStorageLabels").contains("scopedKey"));
    }
}
