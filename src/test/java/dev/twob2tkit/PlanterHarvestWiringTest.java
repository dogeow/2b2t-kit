package dev.twob2tkit;

import dev.twob2tkit.planter.AutoPlanter;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class PlanterHarvestWiringTest {
    @BeforeAll static void bootstrap() {
        net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();
    }
    @Test void actualRuntimeMaturityRejectsYoungCropsAndPreservesExactMaximumAges()throws Exception {
        Method mature=AutoPlanter.class.getDeclaredMethod("isMatureCrop",BlockState.class);mature.setAccessible(true);
        for(Block block:List.of(Blocks.WHEAT,Blocks.CARROTS,Blocks.POTATOES,Blocks.BEETROOTS)) {
            CropBlock crop=(CropBlock)block;
            assertFalse((boolean)mature.invoke(null,crop.getStateForAge(0)));
            assertFalse((boolean)mature.invoke(null,crop.getStateForAge(crop.getMaxAge()-1)));
            assertTrue((boolean)mature.invoke(null,crop.getStateForAge(crop.getMaxAge())));
        }
        assertFalse((boolean)mature.invoke(null,Blocks.NETHER_WART.defaultBlockState().setValue(NetherWartBlock.AGE,2)));
        assertTrue((boolean)mature.invoke(null,Blocks.NETHER_WART.defaultBlockState().setValue(NetherWartBlock.AGE,3)));
        assertFalse((boolean)mature.invoke(null,Blocks.FARMLAND.defaultBlockState()));
    }
    @Test void entityBeforeCropBlocksHarvestWhileBehindOrOffRayDoesNot() {
        Vec3 eye=new Vec3(0,1,0),cropHit=new Vec3(0,1,4);
        assertTrue(AutoPlanter.harvestRayBlocked(eye,cropHit,new AABB(-.25,.5,1,.25,1.5,2)));
        assertTrue(AutoPlanter.harvestRayBlocked(eye,cropHit,new AABB(-.25,.5,-.25,.25,1.5,.25)));
        assertFalse(AutoPlanter.harvestRayBlocked(eye,cropHit,new AABB(-1,.5,5,1,1.5,6)));
        assertFalse(AutoPlanter.harvestRayBlocked(eye,cropHit,new AABB(1,.5,1,2,1.5,2)));
    }
    @Test void liveHarvestUsesVerifiedBlockDestructionWithoutAttackClicksOrCrosshairReplacement()throws Exception {
        Trace trace=trace("planter/AutoPlanter","harvest");
        assertTrue(trace.calls.contains("dev/twob2tkit/planter/AutoPlanter.stillHarvestTarget"));
        assertTrue(trace.calls.contains("dev/twob2tkit/runtime/engine/BorerAim.verifiedHit"));
        assertTrue(trace.calls.contains("dev/twob2tkit/planter/PlanterPolicy.skipHarvestWhenEntityInWay"));
        assertTrue(trace.calls.contains("dev/twob2tkit/planter/AutoPlanter.entityInHarvestRay"));
        assertTrue(trace.calls.contains("net/minecraft/client/multiplayer/MultiPlayerGameMode.startDestroyBlock"));
        assertTrue(trace.calls.contains("net/minecraft/client/multiplayer/MultiPlayerGameMode.continueDestroyBlock"));
        assertFalse(trace.calls.contains("net/minecraft/client/KeyMapping.click"));
        assertFalse(trace.calls.contains("net/minecraft/client/multiplayer/MultiPlayerGameMode.attack"));
        assertFalse(trace.writes.contains("hitResult"));assertFalse(trace.writes.contains("crosshairPickEntity"));
        assertEquals(List.of(0),trace.attackKeyValues);
        assertFalse(trace.calls.stream().anyMatch(c->c.endsWith(".setBlock")));
    }
    @Test void dailyScanAndInteractionUseExistingFarmlandBoundaryAndNeverSelectTillWork()throws Exception {
        assertTrue(trace("planter/AutoPlanter","start").calls.contains("dev/twob2tkit/planter/AutoPlanter.captureField"));
        assertTrue(trace("planter/AutoPlanter","captureField").calls.contains("dev/twob2tkit/planter/PlanterFieldBoundary.capture"));
        assertTrue(trace("planter/AutoPlanter","plantSpot").calls.contains("dev/twob2tkit/planter/PlanterFieldBoundary.canPlant"));
        assertTrue(trace("planter/AutoPlanter","act").calls.contains("dev/twob2tkit/planter/PlanterFieldBoundary.plantIfCurrent"));
        assertTrue(trace("planter/AutoPlanter","stillHarvestTarget").calls.contains("dev/twob2tkit/planter/PlanterFieldBoundary.canHarvest"));
        assertFalse(trace("planter/AutoPlanter","collect").calls.contains("dev/twob2tkit/planter/AutoPlanter.tillSpot"));
        assertFalse(trace("planter/AutoPlanter","tick").calls.contains("dev/twob2tkit/planter/AutoPlanter.selectHoe"));
        assertFalse(trace("planter/AutoPlanter","act").calls.contains("dev/twob2tkit/planter/AutoPlanter.selectHoe"));
        Trace harvest=trace("planter/AutoPlanter","harvest");
        String verify="dev/twob2tkit/planter/AutoPlanter.stillHarvestTarget";
        assertTrue(Collections.frequency(harvest.orderedCalls,verify)>=2);
        assertTrue(harvest.orderedCalls.lastIndexOf(verify)<harvest.orderedCalls.indexOf("net/minecraft/client/multiplayer/MultiPlayerGameMode.startDestroyBlock"));
    }
    @Test void defaultAttackSuppressionIsWiredOnlyThroughStrictOwnedPlanterPredicate()throws Exception {
        assertTrue(trace("mixin/MinecraftTickMixin","kit$ownedMining").calls.contains("dev/twob2tkit/planter/AutoPlanter.ownsMining"));
        Trace owned=trace("planter/AutoPlanter","ownsMining");
        assertTrue(owned.fields.containsAll(List.of("active","harvestStarted","target","sessionLevel","sessionPlayer")));
        assertTrue(owned.calls.containsAll(List.of("dev/twob2tkit/KitKeys.manualMovementDown",
            "dev/twob2tkit/KitKeys.isPhysicallyDown","dev/twob2tkit/planter/AutoPlanter.stillHarvestTarget",
            "net/minecraft/client/multiplayer/MultiPlayerGameMode.isDestroying",
            "dev/twob2tkit/runtime/engine/BorerAim.clipView","dev/twob2tkit/runtime/engine/BorerAim.hitInReach",
            "dev/twob2tkit/planter/AutoPlanter.entityInHarvestRay")));
        assertTrue(trace("planter/AutoPlanter","tick").fields.containsAll(List.of("sessionLevel","sessionPlayer","screen")));
    }
    private static class Trace {
        final Set<String> calls=new HashSet<>(),fields=new HashSet<>(),writes=new HashSet<>();
        final List<Integer> attackKeyValues=new ArrayList<>();
        final List<String> orderedCalls=new ArrayList<>();
    }
    private static Trace trace(String type,String method)throws Exception {
        Trace result=new Trace();
        try(InputStream input=PlanterHarvestWiringTest.class.getResourceAsStream("/dev/twob2tkit/"+type+".class")) {
            assertNotNull(input,type);
            new ClassReader(input).accept(new ClassVisitor(Opcodes.ASM9) {
                @Override public MethodVisitor visitMethod(int access,String name,String desc,String signature,String[] exceptions) {
                    if(!name.equals(method))return null;
                    return new MethodVisitor(Opcodes.ASM9) {
                        String lastField="";Integer constant=null;
                        @Override public void visitFieldInsn(int opcode,String owner,String name,String descriptor) {
                            result.fields.add(name);lastField=name;
                            if(opcode==Opcodes.PUTFIELD)result.writes.add(name);
                        }
                        @Override public void visitInsn(int opcode) {
                            if(opcode==Opcodes.ICONST_0)constant=0;
                            if(opcode==Opcodes.ICONST_1)constant=1;
                        }
                        @Override public void visitMethodInsn(int opcode,String owner,String name,String descriptor,boolean itf) {
                            result.calls.add(owner+"."+name);result.orderedCalls.add(owner+"."+name);
                            if(owner.equals("net/minecraft/client/KeyMapping")&&name.equals("setDown")&&lastField.equals("keyAttack"))result.attackKeyValues.add(constant);
                            lastField="";constant=null;
                        }
                    };
                }
            },0);
        }return result;
    }
}
