package dev.twob2tkit.combat;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import static org.junit.jupiter.api.Assertions.*;

class MeteorPveSettingsWiringTest {
    @Test void genericGuardUsesPreservingTargetsAndNeverWritesPassiveFilter() throws Exception {
        var node = new ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/MeteorModules.class")) {
            assertNotNull(in);
            new ClassReader(in).accept(node, 0);
        }
        var method = node.methods.stream().filter(m -> m.name.equals("enablePveAura")).findFirst().orElseThrow();
        boolean preservingTargets = false;
        for (var instruction : method.instructions) {
            if (instruction instanceof LdcInsnNode value)
                assertNotEquals("ignorePassive", value.cst, "Generic guard must not force the user's passive filter");
            if (instruction instanceof MethodInsnNode call && call.owner.equals("dev/twob2tkit/combat/PveAuraPolicy") && call.name.equals("targets"))
                preservingTargets = true;
        }
        assertTrue(preservingTargets);
    }
}
