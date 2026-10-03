package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class PlanterClickGuiPolicyTest {
    @Test void clickGuiNeverReadsOrWritesIgnoredLegacyFlagsEvenInCallbacks()throws Exception {
        // Old persisted true/false values cannot re-enable a control or be changed by a callback.
        var pages=code("ClickGuiPages");
        for(var method:pages.methods)for(var i:method.instructions)if(i instanceof FieldInsnNode field)
            assertFalse(Set.of("planterTill","planterStack").contains(field.name),method.name+" -> "+field.name);
        var planter=method(pages,"planter");var strings=strings(planter);
        assertFalse(strings.contains("没有耕地时先锄"));assertFalse(strings.contains("甘蔗仙人掌往上叠"));
        assertEquals(3,Collections.frequency(calls(planter),"bool"));
        assertEquals(2,Collections.frequency(calls(planter),"note"));
        assertTrue(strings.contains("日常种田不翻耕草地或泥土；新开田必须通过独立入口明确确认范围。"));
        assertTrue(strings.contains("甘蔗、竹子等普通地面种植不属于日常耕地维护，需独立确认种植范围。"));
    }
    @Test void nativePlanterSaveAlsoPreservesLegacyFlagsAndKeepsWorkingOptions()throws Exception {
        var save=method(code("planter/PlanterScreen"),"saveFields");var fields=new HashSet<String>();
        for(var i:save.instructions)if(i instanceof FieldInsnNode field)fields.add(field.name);
        assertFalse(fields.contains("planterTill"));assertFalse(fields.contains("planterStack"));
        assertTrue(fields.containsAll(Set.of("planterWalk","planterHarvest","planterPickup","planterRange")));
        assertTrue(calls(save).contains("save"));
    }
    private static ClassNode code(String name)throws Exception {
        var result=new ClassNode();try(var in=PlanterClickGuiPolicyTest.class.getResourceAsStream("/dev/twob2tkit/"+name+".class")) {
            assertNotNull(in);new ClassReader(in).accept(result,0);
        }return result;
    }
    private static MethodNode method(ClassNode node,String name) {
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private static List<String> calls(MethodNode method) {
        var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode call)result.add(call.name);return result;
    }
    private static Set<String> strings(MethodNode method) {
        var result=new HashSet<String>();for(var i:method.instructions)if(i instanceof LdcInsnNode literal && literal.cst instanceof String text)result.add(text);return result;
    }
}
