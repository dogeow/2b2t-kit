package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class TerrainReplacePolicyTest {
    private static final BlockPos TARGET = new BlockPos(760994, 62, 797865);
    private static final String KEY = "locked courtyard projection";
    private static final String STONE = "Block{minecraft:stone}";
    private static final String DIRT = "Block{minecraft:dirt}";
    private static final String GRASS = "Block{minecraft:grass_block}[snowy=false]";
    private static final String AIR = "Block{minecraft:air}";

    private static final class World implements TerrainReplacePolicy.World {
        final Map<BlockPos,String> states = new HashMap<>();
        final Set<BlockPos> unloaded = new HashSet<>(), wet = new HashSet<>(), blockEntities = new HashSet<>();
        final Set<BlockPos> nonSolid = new HashSet<>();
        final List<AABB> entities = new ArrayList<>();
        AABB body = new AABB(TARGET.getX()+.2, 64.2, TARGET.getZ()+.2,
            TARGET.getX()+.8, 66.0, TARGET.getZ()+.8);
        Vec3 player = new Vec3(TARGET.getX()+.5, 64.2, TARGET.getZ()+.5);
        double eye = 65.82;
        boolean selected = true, standing = true, guarded = true;
        boolean shovel = true, pick = true, dirt = true, grass = true;

        World() {
            states.put(TARGET, STONE);
            states.put(TARGET.above(), GRASS);
            states.put(TARGET.below(), STONE);
        }
        public boolean loaded(BlockPos pos) { return !unloaded.contains(pos); }
        public boolean air(BlockPos pos) { return AIR.equals(state(pos)); }
        public boolean solid(BlockPos pos) { return !air(pos) && !nonSolid.contains(pos); }
        public boolean fluid(BlockPos pos) { return wet.contains(pos); }
        public boolean blockEntity(BlockPos pos) { return blockEntities.contains(pos); }
        public String state(BlockPos pos) { return states.getOrDefault(pos,AIR); }
        public boolean selectedDirtAndGrassColumn(BlockPos pos,String key) {
            return selected && pos.equals(TARGET) && KEY.equals(key);
        }
        public Iterable<AABB> nearbyEntityBoxes(BlockPos pos) { return entities; }
        public AABB playerBody() { return body; }
        public Vec3 playerPosition() { return player; }
        public double playerEyeY() { return eye; }
        public boolean standingPose() { return standing; }
        public boolean guardedFlight() { return guarded; }
        public boolean silkShovelReady() { return shovel; }
        public boolean pickReady() { return pick; }
        public boolean dirtReady() { return dirt; }
        public boolean grassReady() { return grass; }
    }

    private static String check(World world,TerrainReplacePolicy.Stage stage) {
        String expected=switch(stage){
            case LIFT_GRASS->GRASS;
            case MINE_STONE->STONE;
            case PLACE_DIRT->STONE;
            case RESTORE_GRASS->world.state(TARGET);
        };
        return TerrainReplacePolicy.rejection(world,TARGET,stage,KEY,GRASS,STONE,expected);
    }

    @Test void requestScopeCannotSurviveWorldOrManualRevisionChange() {
        long now = 100000L;
        assertTrue(TerrainReplacePolicy.scopeValid("world-a","world-a",4,4,false,now+5000,now));
        assertTrue(TerrainReplacePolicy.scopeValid("world-a","world-a",4,5,true,now-1000,now));
        assertFalse(TerrainReplacePolicy.scopeValid("world-a","world-b",4,5,true,now+5000,now));
        assertFalse(TerrainReplacePolicy.scopeValid("world-a","world-a",4,5,false,now+5000,now));
        assertFalse(TerrainReplacePolicy.scopeValid("world-a","world-a",4,6,true,now+5000,now));
        assertFalse(TerrainReplacePolicy.scopeValid("world-a","world-a",4,4,false,now-1,now));
        assertFalse(TerrainReplacePolicy.scopeValid("world-a","world-a",4,4,false,now+15001,now));
    }

    @Test void fourStagesRequireExactConfirmedColumnStates() {
        World world = new World();
        assertNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        assertNotNull(check(world,TerrainReplacePolicy.Stage.MINE_STONE));
        world.states.put(TARGET.above(),AIR);
        assertNull(check(world,TerrainReplacePolicy.Stage.MINE_STONE));
        world.states.put(TARGET,AIR);
        assertNull(check(world,TerrainReplacePolicy.Stage.PLACE_DIRT));
        world.states.put(TARGET,DIRT);
        assertNull(check(world,TerrainReplacePolicy.Stage.RESTORE_GRASS));
        world.states.put(TARGET.above(),GRASS);
        assertNotNull(check(world,TerrainReplacePolicy.Stage.RESTORE_GRASS));
    }

    @Test void restoreAcceptsOnlyExactCurrentDirtOrNaturallySpreadGrassFoundation() {
        World world = new World();world.states.put(TARGET.above(),AIR);world.states.put(TARGET,DIRT);
        assertNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.RESTORE_GRASS,
            KEY,GRASS,STONE,DIRT));
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.RESTORE_GRASS,
            KEY,GRASS,STONE,GRASS));
        world.states.put(TARGET,GRASS);
        assertNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.RESTORE_GRASS,
            KEY,GRASS,STONE,GRASS));
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.RESTORE_GRASS,
            KEY,GRASS,STONE,DIRT));
        for(String arbitrary:List.of(STONE,"Block{minecraft:coarse_dirt}","Block{minecraft:sand}")){
            world.states.put(TARGET,arbitrary);
            assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.RESTORE_GRASS,
                KEY,GRASS,STONE,arbitrary));
        }
        world.states.put(TARGET,GRASS);world.states.put(TARGET.above(),GRASS);
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.RESTORE_GRASS,
            KEY,GRASS,STONE,GRASS));
    }

    @Test void otherThreeStagesKeepTheirExactActionStateContracts() {
        World world = new World();
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.LIFT_GRASS,
            KEY,GRASS,STONE,STONE));
        world.states.put(TARGET.above(),AIR);
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.MINE_STONE,
            KEY,GRASS,STONE,DIRT));
        world.states.put(TARGET,AIR);
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,TerrainReplacePolicy.Stage.PLACE_DIRT,
            KEY,GRASS,STONE,DIRT));
    }

    @Test void selectedColumnAndUnchangedFoundationMustBePresent() {
        World world = new World();
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET.above(),
            TerrainReplacePolicy.Stage.LIFT_GRASS,KEY,GRASS,STONE,GRASS));
        assertNotNull(TerrainReplacePolicy.rejection(world,new BlockPos(760992,62,797865),
            TerrainReplacePolicy.Stage.LIFT_GRASS,KEY,GRASS,STONE,GRASS));
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET.north(),
            TerrainReplacePolicy.Stage.LIFT_GRASS,KEY,GRASS,STONE,GRASS));
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,
            TerrainReplacePolicy.Stage.LIFT_GRASS,"",GRASS,STONE,GRASS));
        world.selected = false;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.selected = true;
        world.states.put(TARGET.below(),AIR);
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.states.put(TARGET.below(),STONE);
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,
            TerrainReplacePolicy.Stage.LIFT_GRASS,KEY,GRASS,DIRT,GRASS));
        world.states.put(TARGET.below(),DIRT);
        assertNotNull(TerrainReplacePolicy.rejection(world,TARGET,
            TerrainReplacePolicy.Stage.LIFT_GRASS,KEY,GRASS,DIRT,GRASS));
        world.states.put(TARGET.below(),STONE);
        world.unloaded.add(TARGET.above());
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
    }

    @Test void waterBlockEntityOrObstructedFlightColumnStopsEveryStage() {
        World world = new World();
        BlockPos neighbor = TARGET.east().above(2);
        world.wet.add(neighbor);
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.wet.clear();
        world.blockEntities.add(neighbor);
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.blockEntities.clear();
        world.states.put(TARGET.above(2),STONE);
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.states.put(TARGET.above(2),AIR);
        BlockPos attachment = TARGET.north();
        world.states.put(attachment,"Block{minecraft:wall_torch}[facing=south]");
        world.nonSolid.add(attachment);
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
    }

    @Test void poseFlightActorsAndPerStageSupplyAreRequired() {
        World world = new World();
        world.guarded = false;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.guarded = true;
        world.standing = false;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.standing = true;
        world.player = new Vec3(TARGET.getX()+.8,64.2,TARGET.getZ()+.5);
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.player = new Vec3(TARGET.getX()+.5,64.2,TARGET.getZ()+.5);
        world.eye = 66.5;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.eye = 65.82;
        world.entities.add(new AABB(TARGET.getX()+2,63,TARGET.getZ()+1,
            TARGET.getX()+3,64,TARGET.getZ()+2));
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.entities.clear();
        world.body = new AABB(TARGET.above());
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.body = new AABB(TARGET.getX()+.2,64.2,TARGET.getZ()+.2,
            TARGET.getX()+.8,66.0,TARGET.getZ()+.8);
        world.shovel = false;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.LIFT_GRASS));
        world.shovel = true;
        world.states.put(TARGET.above(),AIR);
        world.pick = false;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.MINE_STONE));
        world.pick = true;
        world.states.put(TARGET,AIR);
        world.dirt = false;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.PLACE_DIRT));
        world.dirt = true;
        world.states.put(TARGET,DIRT);
        world.grass = false;
        assertNotNull(check(world,TerrainReplacePolicy.Stage.RESTORE_GRASS));
    }

    @Test void hostChecksAtDispatchEveryMiningTickAndBeforePlacementClick() throws Exception {
        ClassNode node = bridge();
        MethodNode dispatch = method(node,"dispatch");
        MethodNode input = method(node,"beforeInput");
        assertTrue(calls(dispatch).contains("terrainReplacementGuard"));
        assertTrue(calls(input).indexOf("terrainReplacementGuard") >= 0);
        assertTrue(calls(input).indexOf("terrainReplacementGuard") < calls(input).indexOf("startDestroyBlock"));
        assertTrue(calls(input).indexOf("terrainReplacementGuard") < calls(input).indexOf("continueDestroyBlock"));
        assertTrue(node.methods.stream().filter(m -> m.name.startsWith("lambda$dispatch$"))
            .map(TerrainReplacePolicyTest::calls)
            .anyMatch(names -> names.contains("terrainReplacementGuard")
                && names.indexOf("terrainReplacementGuard") < names.indexOf("useItemOn")));
    }

    @Test void nativeStatusAdvertisesTerrainReplacementProtocol() throws Exception {
        MethodNode snapshot = method(bridge(),"snapshot");
        boolean advertised = false;
        for (var instruction : snapshot.instructions)
            if (instruction instanceof LdcInsnNode key && "terrain_replace_protocol".equals(key.cst)) {
                var value = instruction.getNext();
                while (value != null && value.getOpcode() < 0) value = value.getNext();
                advertised = value != null && value.getOpcode() == Opcodes.ICONST_1;
                break;
            }
        assertTrue(advertised);
    }

    private static ClassNode bridge() throws Exception {
        ClassNode node = new ClassNode();
        try (var source = TerrainReplacePolicyTest.class.getResourceAsStream(
                "/dev/twob2tkit/automation/AutomationBridge.class")) {
            assertNotNull(source);
            new ClassReader(source).accept(node,0);
        }
        return node;
    }
    private static MethodNode method(ClassNode node,String name) {
        return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private static List<String> calls(MethodNode method) {
        List<String> names = new ArrayList<>();
        for (var instruction : method.instructions)
            if (instruction instanceof MethodInsnNode call) names.add(call.name);
        return names;
    }
}
