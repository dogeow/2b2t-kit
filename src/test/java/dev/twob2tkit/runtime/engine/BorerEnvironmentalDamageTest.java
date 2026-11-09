package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Terrain damage while mining (suffocation under gravel, crowding, dripstone) must count as
 * environmental so the repeated-environmental-damage exit fires and it is not reported as a
 * mob hit; mob-applied effects must stay non-environmental so combat pauses still hold.
 */
class BorerEnvironmentalDamageTest {
    private Set<String> damageTypesRead(String method) throws Exception {
        var node = new ClassNode();
        try (var input = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerThreats.class")) {
            assertNotNull(input); new ClassReader(input).accept(node, 0);
        }
        var m = node.methods.stream().filter(x -> x.name.equals(method)).findFirst().orElseThrow();
        var read = new HashSet<String>();
        for (var i : m.instructions)
            if (i instanceof FieldInsnNode f && f.owner.endsWith("/DamageTypes")) read.add(f.name);
        return read;
    }

    @Test void miningTerrainDamageIsEnvironmental() throws Exception {
        var read = damageTypesRead("isEnvironmental");
        for (var type : List.of("IN_WALL", "CRAMMING", "STALAGMITE", "FALLING_STALACTITE", "FALLING_BLOCK",
                "FALLING_ANVIL", "FLY_INTO_WALL", "LIGHTNING_BOLT", "OUTSIDE_BORDER",
                "HOT_FLOOR", "LAVA", "IN_FIRE", "ON_FIRE", "CAMPFIRE", "DROWN", "FALL", "CACTUS"))
            assertTrue(read.contains(type), type + " must be environmental");
    }

    @Test void mobAppliedDamageIsNeverEnvironmental() throws Exception {
        var read = damageTypesRead("isEnvironmental");
        for (var type : List.of("WITHER", "MAGIC", "INDIRECT_MAGIC", "MOB_ATTACK", "ARROW", "TRIDENT",
                "THORNS", "STING", "EXPLOSION", "PLAYER_EXPLOSION", "SONIC_BOOM"))
            assertFalse(read.contains(type), type + " must keep combat/mining pauses");
    }

    @Test void everyEnvironmentalTypeHasItsOwnLabel() throws Exception {
        var labelled = damageTypesRead("environmentalLabel");
        for (var type : damageTypesRead("isEnvironmental"))
            assertTrue(labelled.contains(type), type + " needs a chat label instead of a raw id");
    }
}
