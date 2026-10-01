package dev.twob2tkit;

import dev.twob2tkit.planter.PlanterApproachTracker;
import dev.twob2tkit.planter.PlanterLoot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class PlanterMovementLootTest {
    @BeforeAll static void bootstrap() {
        net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();
    }
    @Test void wheatAndBeetrootActualProduceAndSeedsAreCollected() {
        assertSame(Items.WHEAT_SEEDS,Blocks.WHEAT.asItem());
        assertSame(Items.BEETROOT_SEEDS,Blocks.BEETROOTS.asItem());
        assertTrue(PlanterLoot.isFarmLoot(Items.WHEAT,Items.WHEAT_SEEDS,Blocks.WHEAT));
        assertTrue(PlanterLoot.isFarmLoot(Items.WHEAT_SEEDS,Items.WHEAT_SEEDS,Blocks.WHEAT));
        assertTrue(PlanterLoot.isFarmLoot(Items.BEETROOT,Items.BEETROOT_SEEDS,Blocks.BEETROOTS));
        assertTrue(PlanterLoot.isFarmLoot(Items.BEETROOT_SEEDS,Items.BEETROOT_SEEDS,Blocks.BEETROOTS));
    }
    @Test void collectionStillRejectsOtherCropsAndUnrelatedValuables() {
        assertFalse(PlanterLoot.isFarmLoot(Items.WHEAT,Items.CARROT,Blocks.CARROTS));
        assertFalse(PlanterLoot.isFarmLoot(Items.BEETROOT,Items.WHEAT_SEEDS,Blocks.WHEAT));
        assertFalse(PlanterLoot.isFarmLoot(Items.DIAMOND,Items.WHEAT_SEEDS,Blocks.WHEAT));
        assertFalse(PlanterLoot.isFarmLoot(ItemStack.EMPTY,Items.WHEAT_SEEDS,Blocks.WHEAT));
        assertTrue(PlanterLoot.isFarmLoot(Items.CARROT,Items.CARROT,Blocks.CARROTS));
        assertTrue(PlanterLoot.isFarmLoot(Items.POTATO,Items.POTATO,Blocks.POTATOES));
    }
    @Test void farmingWalkNeverJumpsAndDoesNotAdvanceForNearOrInvalidDistance() {
        for(double distance:new double[]{0,.2,.21,1,24,Double.NaN,Double.POSITIVE_INFINITY}) {
            var input=PlanterApproachTracker.inputs(distance);
            assertFalse(input.jump());
            assertEquals(Double.isFinite(distance)&&distance>.2,input.forward());
        }
    }
    @Test void actualApproachAndPickupCallTheNoJumpMovementAndActualLootFilter()throws Exception {
        assertTrue(calls("planter/AutoPlanter","approach").contains("dev/twob2tkit/planter/PlanterApproachTracker.walkToward"));
        assertFalse(calls("planter/AutoPlanter","approach").contains("dev/twob2tkit/ApproachTracker.walkToward"));
        assertTrue(calls("planter/PlanterLoot","tick").contains("dev/twob2tkit/planter/PlanterApproachTracker.walkToward"));
        for(String method:List.of("beginNear","findOrLock","findNearest"))
            assertTrue(calls("planter/PlanterLoot",method).contains("dev/twob2tkit/planter/PlanterLoot.isFarmLoot"),method);
        assertTrue(calls("planter/PlanterLoot","isFarmLoot").contains("net/minecraft/world/item/ItemStack.getItem"));
        assertTrue(calls("planter/PlanterApproachTracker","walkToward").contains("dev/twob2tkit/planter/PlanterApproachTracker.inputs"));
        assertTrue(calls("planter/PlanterApproachTracker","walkToward").contains("dev/twob2tkit/planter/PlanterApproachTracker$WalkInputs.jump"));
    }
    private static List<String> calls(String type,String method)throws Exception {
        List<String> result=new ArrayList<>();
        try(InputStream input=PlanterMovementLootTest.class.getResourceAsStream("/dev/twob2tkit/"+type+".class")) {
            assertNotNull(input,type);
            new ClassReader(input).accept(new ClassVisitor(Opcodes.ASM9) {
                @Override public MethodVisitor visitMethod(int access,String name,String desc,String signature,String[] exceptions) {
                    if(!name.equals(method))return null;
                    return new MethodVisitor(Opcodes.ASM9) {
                        @Override public void visitMethodInsn(int opcode,String owner,String name,String descriptor,boolean itf) {result.add(owner+"."+name);}
                    };
                }
            },0);
        }return result;
    }
}
