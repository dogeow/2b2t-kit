package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class DryPavingMiningPolicyTest {
    private static final BlockPos TARGET = new BlockPos(10, 63, 10);
    private static final String SOURCE = "Block{minecraft:grass_block}[snowy=false]";

    private static final class World implements DryPavingMiningPolicy.World {
        final Set<BlockPos> unloaded = new HashSet<>();
        final Set<BlockPos> occupied = new HashSet<>();
        final Set<BlockPos> wet = new HashSet<>();
        final Set<BlockPos> blockEntities = new HashSet<>();
        final Set<BlockPos> nonSolid = new HashSet<>();
        final ArrayList<Vec3> entities = new ArrayList<>();
        String targetState = SOURCE;
        boolean natural = true;
        boolean naturalSupport = true;
        boolean standing = false;
        AABB playerBody = new AABB(12.2, 63, 10.2, 12.8, 64.8, 10.8);

        public boolean loaded(BlockPos pos) { return !unloaded.contains(pos); }
        public boolean air(BlockPos pos) {
            return !pos.equals(TARGET) && !pos.equals(TARGET.below()) && !occupied.contains(pos);
        }
        public boolean fluid(BlockPos pos) { return wet.contains(pos); }
        public boolean blockEntity(BlockPos pos) { return blockEntities.contains(pos); }
        public boolean solid(BlockPos pos) { return !nonSolid.contains(pos); }
        public boolean naturalSupport(BlockPos pos) { return naturalSupport && pos.equals(TARGET.below()); }
        public Iterable<Vec3> nearbyEntities(BlockPos destination) { return entities; }
        public AABB playerBody() { return playerBody; }
        public String state(BlockPos pos) { return targetState; }
        public boolean naturalSurface(BlockPos pos) { return natural && pos.equals(TARGET); }
        public boolean playerStandingOn(BlockPos pos) { return standing; }
    }

    @Test void exactNaturalSourceAndStableDryWorksitePass() {
        World world = new World();
        assertNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET.above(), SOURCE));
        world.targetState = "Block{minecraft:dirt}";
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
        world.targetState = SOURCE;
        world.natural = false;
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
    }

    @Test void fluidEntityStandingOrChangedSupportStopsContinuedMining() {
        World world = new World();
        BlockPos neighbor = TARGET.east().above();
        world.wet.add(neighbor);
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
        world.wet.clear();
        world.blockEntities.add(neighbor);
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
        world.blockEntities.clear();
        world.entities.add(Vec3.atCenterOf(TARGET));
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
        world.entities.clear();
        world.standing = true;
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
        world.standing = false;
        world.naturalSupport = false;
        assertNotNull(DryPavingMiningPolicy.rejection(world, TARGET, SOURCE));
    }

    @Test void nativeMineChecksBeforeStartAndEveryDestroyTick() throws Exception {
        ClassNode node = new ClassNode();
        try (var source = getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")) {
            assertNotNull(source);
            new ClassReader(source).accept(node, 0);
        }
        MethodNode dispatch = node.methods.stream().filter(method -> method.name.equals("dispatch"))
                .findFirst().orElseThrow();
        assertTrue(calls(dispatch).contains("dryPavingMiningGuard"));
        MethodNode input = node.methods.stream().filter(method -> method.name.equals("beforeInput"))
                .findFirst().orElseThrow();
        List<String> inputCalls = calls(input);
        assertTrue(inputCalls.indexOf("dryPavingMiningGuard") >= 0);
        assertTrue(inputCalls.indexOf("dryPavingMiningGuard") < inputCalls.indexOf("startDestroyBlock"));
        assertTrue(inputCalls.indexOf("dryPavingMiningGuard") < inputCalls.indexOf("continueDestroyBlock"));
        MethodNode release = node.methods.stream().filter(method -> method.name.equals("releaseWalk"))
                .findFirst().orElseThrow();
        assertTrue(calls(release).contains("stopDestroyBlock"));
    }

    private static List<String> calls(MethodNode method) {
        List<String> names = new ArrayList<>();
        for (var instruction : method.instructions)
            if (instruction instanceof MethodInsnNode call) names.add(call.name);
        return names;
    }
}
