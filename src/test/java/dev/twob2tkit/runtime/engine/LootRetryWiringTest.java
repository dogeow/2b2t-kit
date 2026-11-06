package dev.twob2tkit.runtime.engine;

import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import static org.junit.jupiter.api.Assertions.*;

class LootRetryWiringTest {
    private MethodNode method(String name) throws Exception {
        try (InputStream in=getClass().getClassLoader().getResourceAsStream("dev/twob2tkit/runtime/engine/BorerLoot.class")) {
            assertNotNull(in); ClassNode node=new ClassNode();new ClassReader(in).accept(node,0);
            return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
        }
    }
    private boolean calls(MethodNode m,String owner,String name) {
        for(var i:m.instructions)if(i instanceof MethodInsnNode c && c.owner.equals(owner) && c.name.equals(name))return true;
        return false;
    }
    @Test void deferralUsesStableItemIdentityAndBackoff() throws Exception {
        MethodNode m=method("abandon");
        assertTrue(calls(m,"net/minecraft/world/entity/item/ItemEntity","getUUID"));
        assertTrue(calls(m,"dev/twob2tkit/runtime/engine/LootRetryBackoff","nextDelay"));
    }
    @Test void OrdinaryBatchClearDoesNotEraseBackoffButSessionResetDoes() throws Exception {
        String owner="dev/twob2tkit/runtime/engine/LootRetryBackoff";
        assertFalse(calls(method("clear"),owner,"clear"));
        assertTrue(calls(method("clearIgnored"),owner,"clear"));
    }
}
