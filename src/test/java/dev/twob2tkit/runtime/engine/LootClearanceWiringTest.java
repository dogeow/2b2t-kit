package dev.twob2tkit.runtime.engine;

import java.io.InputStream;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import static org.junit.jupiter.api.Assertions.*;

class LootClearanceWiringTest {
    private MethodNode method(String name) throws Exception {
        try(InputStream in=getClass().getClassLoader().getResourceAsStream("dev/twob2tkit/runtime/engine/BorerLoot.class")) {
            assertNotNull(in);ClassNode c=new ClassNode();new ClassReader(in).accept(c,0);
            return c.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
        }
    }
    private Set<String> calls(String name)throws Exception {
        Set<String> result=new HashSet<>();for(var i:method(name).instructions)if(i instanceof MethodInsnNode c)result.add(c.name);return result;
    }
    @Test void continuingClearanceReleasesMovementWithoutCancellingMining()throws Exception {
        Set<String> hold=calls("holdMovementForClearance");
        assertTrue(hold.contains("setDown"));assertFalse(hold.contains("releaseMine"));assertFalse(hold.contains("stopDestroyBlock"));
        assertTrue(calls("prepareClearance").containsAll(Set.of("keepTarget","holdMovementForClearance","holdStill","setMiningTarget")));
    }
    @Test void pickupAndHopPathsUseTheClearancePolicy()throws Exception {
        assertTrue(calls("handle").containsAll(Set.of("clearBeforePickup","prepareClearance")));
        assertTrue(calls("walkToward").contains("prepareClearance"));
    }
}
