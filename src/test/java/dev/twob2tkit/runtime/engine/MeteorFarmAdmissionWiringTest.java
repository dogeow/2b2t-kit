package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

import java.util.ArrayList;

import static org.junit.jupiter.api.Assertions.*;

class MeteorFarmAdmissionWiringTest {
    @Test void checksScopeBeforeEntityQueriesAndAcquiresOnlyOnce() throws Exception {
        var node = new ClassNode();
        try (var in = MeteorFarmAssist.class.getResourceAsStream("MeteorFarmAssist.class")) {
            assertNotNull(in);
            new ClassReader(in).accept(node, 0);
        }
        var tick = node.methods.stream().filter(m -> m.name.equals("tick")).findFirst().orElseThrow();
        var calls = new ArrayList<String>();
        for (var instruction : tick.instructions) {
            if (instruction instanceof MethodInsnNode call) calls.add(call.name);
            if (instruction instanceof LdcInsnNode constant) assertNotEquals("request.json", constant.cst);
        }
        assertTrue(calls.containsAll(java.util.List.of("supplyAsync", "scope", "getEntitiesOfClass")));
        assertTrue(calls.indexOf("scope") < calls.indexOf("getEntitiesOfClass"));
        assertFalse(calls.contains("entitiesForRendering"));
        assertTrue(calls.indexOf("scope") < calls.indexOf("readString"),
            "The receipt ledger is read only after scope admission");
        assertEquals(1, calls.stream().filter("prepareMeleeTarget"::equals).count());
    }
}
