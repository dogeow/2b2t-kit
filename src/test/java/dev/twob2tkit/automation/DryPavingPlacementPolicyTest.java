package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class DryPavingPlacementPolicyTest {
    private static final BlockPos SUPPORT = new BlockPos(10, 62, 10);

    private static final class World implements DryPavingPlacementPolicy.World {
        final Set<BlockPos> unloaded = new HashSet<>();
        final Set<BlockPos> occupied = new HashSet<>();
        final Set<BlockPos> wet = new HashSet<>();
        final Set<BlockPos> blockEntities = new HashSet<>();
        final Set<BlockPos> nonSolid = new HashSet<>();
        final ArrayList<Vec3> entities = new ArrayList<>();
        boolean naturalSupport = true;
        AABB playerBody = new AABB(12.2, 63, 10.2, 12.8, 64.8, 10.8);

        public boolean loaded(BlockPos pos) { return !unloaded.contains(pos); }
        public boolean air(BlockPos pos) { return !pos.equals(SUPPORT) && !occupied.contains(pos); }
        public boolean fluid(BlockPos pos) { return wet.contains(pos); }
        public boolean blockEntity(BlockPos pos) { return blockEntities.contains(pos); }
        public boolean solid(BlockPos pos) { return !nonSolid.contains(pos); }
        public boolean naturalSupport(BlockPos pos) { return naturalSupport && pos.equals(SUPPORT); }
        public Iterable<Vec3> nearbyEntities(BlockPos destination) { return entities; }
        public AABB playerBody() { return playerBody; }
    }

    @Test void onlyDryY63EmptyDestinationWithNaturalSupportAndNoActorsPasses() {
        World world = new World();
        assertNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.NORTH));
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT.above(), Direction.UP));
        world.naturalSupport = false;
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
    }

    @Test void changedDestinationBodyOrNeighborBlocksClick() {
        World world = new World();
        world.occupied.add(SUPPORT.above());
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
        world.occupied.clear();
        world.occupied.add(SUPPORT.above(2));
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
        world.occupied.clear();
        BlockPos torch = SUPPORT.above().east();
        world.occupied.add(torch);
        world.nonSolid.add(torch);
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
    }

    @Test void wetUnloadedOrBlockEntityInNeighborVolumeBlocksClick() {
        World world = new World();
        BlockPos neighbor = SUPPORT.east().above(3);
        world.wet.add(neighbor);
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
        world.wet.clear();
        world.unloaded.add(neighbor);
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
        world.unloaded.clear();
        world.blockEntities.add(neighbor);
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
    }

    @Test void nearbyEntityOrPlayerBodyBlocksClick() {
        World world = new World();
        world.entities.add(Vec3.atCenterOf(SUPPORT.above()));
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
        world.entities.clear();
        world.playerBody = new AABB(SUPPORT.above());
        assertNotNull(DryPavingPlacementPolicy.rejection(world, SUPPORT, Direction.UP));
    }

    @Test void nativeInteractChecksAtDispatchAndImmediatelyBeforeTheClick() throws Exception {
        ClassNode node = new ClassNode();
        try (var source = getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")) {
            assertNotNull(source);
            new ClassReader(source).accept(node, 0);
        }
        MethodNode dispatch = node.methods.stream().filter(method -> method.name.equals("dispatch"))
                .findFirst().orElseThrow();
        assertTrue(calls(dispatch).contains("dryPavingPlacementGuard"));
        assertTrue(node.methods.stream().filter(method -> method.name.startsWith("lambda$dispatch$"))
                .map(DryPavingPlacementPolicyTest::calls)
                .anyMatch(methodCalls -> methodCalls.contains("dryPavingPlacementGuard")
                        && methodCalls.indexOf("dryPavingPlacementGuard") < methodCalls.indexOf("useItemOn")));
    }

    @Test void nativeStatusAdvertisesGuardedPavingProtocol() throws Exception {
        ClassNode node = new ClassNode();
        try (var source = getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")) {
            assertNotNull(source);
            new ClassReader(source).accept(node, 0);
        }
        MethodNode snapshot = node.methods.stream().filter(method -> method.name.equals("snapshot"))
                .findFirst().orElseThrow();
        boolean advertised = false;
        for (var instruction : snapshot.instructions) {
            if (instruction instanceof LdcInsnNode key && "dry_paving_protocol".equals(key.cst)) {
                var value = instruction.getNext();
                while (value != null && value.getOpcode() < 0) value = value.getNext();
                advertised = value != null && value.getOpcode() == Opcodes.ICONST_1;
                break;
            }
        }
        assertTrue(advertised);
    }

    private static List<String> calls(MethodNode method) {
        List<String> names = new ArrayList<>();
        for (var instruction : method.instructions)
            if (instruction instanceof MethodInsnNode call) names.add(call.name);
        return names;
    }
}
