package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class BucketWaterWiringTest {
    private static String src(String path)throws Exception{return Files.readString(Path.of("src/client/java/dev/twob2tkit/"+path+".java"));}
    @Test void onlyOneNormalUseWithoutMutatingWorldOrInventory()throws Exception {
        var s=src("automation/BucketWaterAction");assertEquals(1,s.split("gameMode\\.useItem\\(",-1).length-1);
        assertFalse(s.contains("gameMode.useItemOn("));assertFalse(s.contains(".setBlock("));assertFalse(s.contains(".setItem("));
        assertFalse(s.contains(".teleport"));assertFalse(s.contains("keyUse.setDown"));assertTrue(s.contains("if(receipt.sent())throw"));
    }
    @Test void durableClaimPrecedesSingleSend()throws Exception {
        var s=src("automation/BucketWaterAction");assertTrue(s.indexOf("BucketUseStore.claim(claimPath,claim)")<s.indexOf("gameMode.useItem("));
        assertTrue(s.contains("BucketUseStore.requireAvailable(claimPath)"));assertTrue(s.contains("terminal(String outcome)"));
    }
    @Test void sourceAndPlacementUseTheirRealVanillaRayModes()throws Exception {
        var s=src("automation/BucketWaterAction");assertTrue(s.contains("ClipContext.Fluid.SOURCE_ONLY:ClipContext.Fluid.NONE"));
        assertTrue(s.contains("calculateViewVector(c.player.getXRot(),c.player.getYRot())"));assertTrue(s.contains("hit.getBlockPos().relative(hit.getDirection()).equals(target)"));
        assertTrue(s.contains("state.is(Blocks.WATER)"));assertTrue(s.contains("LiquidBlock.LEVEL"));assertTrue(s.contains("LiquidBlockContainer"));
        assertTrue(s.contains("EnvironmentAttributes.WATER_EVAPORATES"));
    }
    @Test void loadedChunkReachAndEntityChecksAreFresh()throws Exception {
        var s=src("automation/BucketWaterAction");assertTrue(s.contains("LoadedServerChunkEvidence.isServerChunk"));
        assertTrue(s.contains("validateBeforeSend(c,true)"));assertTrue(s.contains("blockInteractionRange()"));assertTrue(s.contains("box.clip(eye,point)"));
        assertTrue(s.contains("new AABB(target)"));assertTrue(s.contains("mayUseItemAt"));
    }
    @Test void allBasinWallsRejectWaterloggableBlocksRatherThanRelyingOnCollisionShape()throws Exception {
        var s=src("automation/BucketWaterAction");
        int start=s.indexOf("private boolean dryFullBlock(");int end=s.indexOf("private boolean boundedHole(",start);
        var wall=s.substring(start,end);assertTrue(wall.contains("instanceof LiquidBlockContainer"));
        assertTrue(wall.contains("isCollisionShapeFullBlock"));assertTrue(wall.contains("getFluidState(pos).isEmpty()"));
    }
    @Test void rawServerCorrectionsAndPredictionSettlementAreRequired()throws Exception {
        var s=src("automation/BucketWaterAction");assertTrue(s.contains("receipt.block(sameContext(c),pos.equals(target),true"));
        assertTrue(s.contains("!predictions.pending(c.level,target)"));assertTrue(s.contains("inventoryUnchanged(c,true)"));
        assertTrue(s.contains("BucketWaterPolicy.exactDelta"));assertTrue(s.contains("sender==connection"));
    }
    @Test void inventoryCallbacksAreCurrentConnectionTailOnly()throws Exception {
        var s=src("mixin/BucketInventoryUpdatesMixin");assertEquals(3,s.split("@At\\(\"TAIL\"\\)",-1).length-1);
        assertTrue(s.contains("handleSetPlayerInventory"));assertTrue(s.contains("handleContainerSetSlot"));assertTrue(s.contains("handleContainerContent"));
        assertTrue(s.contains("packet.containerId()!=0"));assertTrue(s.contains("this==Minecraft.getInstance().getConnection()"));
        var config=Files.readString(Path.of("src/client/resources/twob2tkit.client.mixins.json"));assertTrue(config.contains("BucketInventoryUpdatesMixin"));
    }
    @Test void existingNativeMaterialSubmitAdmitsOnlyTheTwoNarrowBucketCommands()throws Exception {
        var s=src("automation/AutomationBridge");int start=s.indexOf("static String nativeMaterialSubmit(");
        int end=s.indexOf("private static void nativeMaterialRunQueued(",start);var submit=s.substring(start,end);
        assertTrue(submit.contains("\"bucket_fill\",\"bucket_place\""));assertFalse(submit.contains("\"use_item\""));
        assertFalse(submit.contains("gameMode.useItem("));assertTrue(submit.contains("nativeMaterialCheck(owner,c)"));
    }
    @Test void bridgeRequiresMaterialOwnershipAndKeepsFoodSemantics()throws Exception {
        var s=src("automation/AutomationBridge");assertTrue(s.contains("bucketOwnerCurrent(c,r)"));assertTrue(s.contains("bucketWaterTask.poll(c,ticks,ticks>=deadline)"));
        assertTrue(s.contains("currentMaterialRequest(c,r)"));assertTrue(s.contains("loadedHostileNearby(c)"));assertTrue(s.contains("lastBucketWater"));
        assertTrue(s.contains("AutomationFoodPolicy.allow("));assertTrue(s.contains("Expected edible item in hotbar"));
        assertTrue(s.contains("j.addProperty(\"bucket_water_protocol\",1)"));
    }
}
