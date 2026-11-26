package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class PlanterClickGuiPolicyTest {
    @Test void clickGuiNeverReadsOrWritesIgnoredLegacyFlagsEvenInCallbacks()throws Exception {
        // Old persisted true/false values cannot re-enable a control or be changed by a callback.
        var pages=code("ProductionPages");
        for(var method:pages.methods)for(var i:method.instructions)if(i instanceof FieldInsnNode field)
            assertFalse(Set.of("planterTill","planterStack").contains(field.name),method.name+" -> "+field.name);
        var planter=method(pages,"planter");var strings=strings(planter);
        assertFalse(strings.contains("没有耕地时先锄"));assertFalse(strings.contains("甘蔗仙人掌往上叠"));
        assertEquals(3,Collections.frequency(calls(planter),"bool"));
        // The tilling and ground-crop boundaries stay visible on the page, not only in a tooltip.
        assertEquals(1,Collections.frequency(calls(planter),"note"));
        assertTrue(strings.contains("日常种田不翻耕草地或泥土，甘蔗、竹子等也不在维护范围；新开田或种这些需另外明确确认范围。"));
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
