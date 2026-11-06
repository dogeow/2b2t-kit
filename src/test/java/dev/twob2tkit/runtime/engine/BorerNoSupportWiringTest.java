package dev.twob2tkit.runtime.engine;

import java.io.InputStream;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import static org.junit.jupiter.api.Assertions.*;

class BorerNoSupportWiringTest {
    private MethodNode method(String resource,String name) throws Exception {
        try (InputStream in=getClass().getClassLoader().getResourceAsStream(resource)) {
            assertNotNull(in);ClassNode node=new ClassNode();new ClassReader(in).accept(node,0);
            return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
        }
    }
    @Test void noSupportBranchInvokesRecoveryInsteadOfResettingForever() throws Exception {
        boolean callsRecovery=false;
        for(var i:method("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.class","tick").instructions) {
            if(i instanceof LdcInsnNode l && "前方没有立足点，已停步，不往下掉".equals(l.cst))fail("Unbounded wait remains");
            if(i instanceof MethodInsnNode c && c.owner.equals("dev/twob2tkit/runtime/engine/BorerNoSupportRecovery") && c.name.equals("handle"))callsRecovery=true;
        }
        assertTrue(callsRecovery);
    }
    @Test void recoveryChecksHazardsAndUsesExistingVerifiedActions() throws Exception {
        Set<String> calls=new HashSet<>();
        for(var i:method("dev/twob2tkit/runtime/engine/BorerNoSupportRecovery.class","handle").instructions)
            if(i instanceof MethodInsnNode c)calls.add(c.name);
        assertTrue(calls.containsAll(Set.of("safeDropAhead","playerOnMagma","walkSafeDrop",
            "placeStalledDescentSupport","nudgeToColumnCenter","replanOre","skipActive","stopUnroutable")));
    }
}
