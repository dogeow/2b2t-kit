package dev.twob2tkit.chopper;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ChopperCombatWiringTest {
    private MethodNode method(String name) throws Exception {
        var node = new ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/chopper/AutoChopper.class")) {
            assertNotNull(in);
            new ClassReader(in).accept(node, 0);
        }
        return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(String name) throws Exception {
        var names = new ArrayList<String>();
        for (var instruction : method(name).instructions)
            if (instruction instanceof MethodInsnNode call) names.add(call.name);
        return names;
    }
    @Test void actualScanUsesObservedTargetsAndTimeBoundedAttackerEvidence() throws Exception {
        assertTrue(calls("nearbyHostile").containsAll(List.of("activeAuraTarget", "getTarget", "getLastHurtByMob",
            "getLastHurtByMobTimestamp", "recentAttacker", "isThreat")));
        assertTrue(calls("updateCombatPause").containsAll(List.of("nearbyHostile", "shouldPause", "holdStill", "selectWeapon")));
    }
    @Test void auraIntegrationReadsActivityAndCurrentTargetWithoutChangingSettings() throws Exception {
        var lookups = new ArrayList<String>();
        for (var instruction : method("activeAuraTarget").instructions)
            if (instruction instanceof LdcInsnNode constant && constant.cst instanceof String name) lookups.add(name);
        assertTrue(lookups.indexOf("isActive") >= 0 && lookups.indexOf("getTarget") > lookups.indexOf("isActive"));
        for (String mutator : List.of("enable", "disable", "toggle", "set")) assertFalse(lookups.contains(mutator));
        // An inactive module must return before the getTarget reflection lookup.
        int returns = 0;
        for (var instruction : method("activeAuraTarget").instructions) {
            if (instruction instanceof LdcInsnNode c && "getTarget".equals(c.cst)) break;
            if (instruction.getOpcode() == org.objectweb.asm.Opcodes.ARETURN) returns++;
        }
        assertTrue(returns > 0);
    }
}
