package dev.twob2tkit.chopper;

import dev.twob2tkit.runtime.engine.BorerFlyPath;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ChopperApproachWiringTest {
    private ClassNode read(String owner) throws Exception {
        var node = new ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/chopper/" + owner + ".class")) {
            assertNotNull(in);
            new ClassReader(in).accept(node, 0);
        }
        return node;
    }
    private List<MethodInsnNode> calls(String owner, String name) throws Exception {
        var method = read(owner).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
        var calls = new ArrayList<MethodInsnNode>();
        for (var instruction : method.instructions)
            if (instruction instanceof MethodInsnNode call) calls.add(call);
        return calls;
    }
    private List<String> names(String owner, String name) throws Exception {
        return calls(owner, name).stream().map(c -> c.name).toList();
    }
    @Test void actualApproachUsesManagedRoutesForTreeWorkAndReplanting() throws Exception {
        var approach = names("AutoChopper", "approach");
        assertTrue(approach.containsAll(List.of("moveToTree", "safeStandby", "returnToStandby", "stop")));
        assertFalse(approach.contains("setDown"));
        assertFalse(approach.contains("walkToward"));
        assertTrue(names("ChopperScaffold", "planWork").contains("choose"));
        assertTrue(names("ChopperScaffold", "travelTo").contains("findExact"));
        assertTrue(names("ChopperScaffold", "safeStandby").contains("above"));
    }
    @Test void everyTravelInputChecksTheSweptBodyBeforeMovement() throws Exception {
        var calls = calls("ChopperScaffold", "tick");
        int safeMove = -1, speed = -1;
        for (int i = 0; i < calls.size(); i++) {
            var call = calls.get(i);
            if (call.name.equals("safeMove")) safeMove = i;
            if (call.owner.endsWith("BorerAreaFlightSession") && call.name.equals("speed") && speed < 0) speed = i;
        }
        assertTrue(safeMove >= 0 && speed > safeMove);
        assertTrue(names("ChopperScaffold", "safeMove").containsAll(List.of("getBoundingBox", "expandTowards", "noCollision", "recoverCollision")));
        var recoveryChecks = read("ChopperScaffold").methods.stream()
            .filter(m -> m.name.startsWith("lambda$recoverCollision$")).toList();
        assertEquals(2, recoveryChecks.size());
        for (var method : recoveryChecks) {
            boolean checksBody = false;
            for (var instruction : method.instructions)
                if (instruction instanceof MethodInsnNode call && call.name.equals("safeBox")) checksBody = true;
            assertTrue(checksBody, method.name);
        }
    }
    @Test void aFeetOnlyOpeningCannotBecomeAWorkPositionOrFlightRoute() {
        ChopperPlatformPlan.World world = new ChopperPlatformPlan.World() {
            public boolean clear(BlockPos p) {
                return p.getZ() == 0 && (p.getY() == 0 && p.getX() >= 0 && p.getX() <= 4
                    || p.equals(new BlockPos(0, 1, 0)));
            }
            public boolean replaceable(BlockPos p) { return true; }
            public boolean floor(BlockPos p) { return true; }
        };
        assertTrue(BorerFlyPath.open(world, BlockPos.ZERO));
        assertFalse(BorerFlyPath.open(world, new BlockPos(1, 0, 0)));
        assertNull(ChopperPlatformPlan.choose(world, new Vec3(.5, 0, .5), List.of(new BlockPos(4, 0, 0)), 4.5));
        assertTrue(BorerFlyPath.findExact(world, BlockPos.ZERO, new BlockPos(4, 0, 0), 8, 100).nodes().isEmpty());
    }
}
