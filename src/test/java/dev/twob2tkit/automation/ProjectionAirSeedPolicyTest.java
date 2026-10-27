package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeAll;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.RotatedPillarBlock;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionAirSeedPolicyTest {
    @Test void singleSlabsPredictTheRequestedHalfUsingOneFace(){
        var bottom=Blocks.COBBLESTONE_SLAB.defaultBlockState();
        var top=bottom.setValue(net.minecraft.world.level.block.SlabBlock.TYPE,net.minecraft.world.level.block.state.properties.SlabType.TOP);
        assertTrue(ProjectionAirSeed.singleSlab(bottom));assertTrue(ProjectionAirSeed.singleSlab(top));
        for(var motion:Direction.values()){
            assertEquals(Direction.UP,ProjectionAirSeed.placementFace(bottom,motion));
            assertEquals(Direction.DOWN,ProjectionAirSeed.placementFace(top,motion));
        }
    }
    @Test void doubleAndWaterloggedSlabsCannotBecomeAOneItemSeed(){
        var dry=Blocks.COBBLESTONE_SLAB.defaultBlockState();
        var doubled=dry.setValue(net.minecraft.world.level.block.SlabBlock.TYPE,net.minecraft.world.level.block.state.properties.SlabType.DOUBLE);
        var wet=dry.setValue(net.minecraft.world.level.block.SlabBlock.WATERLOGGED,true);
        for(var invalid:new net.minecraft.world.level.block.state.BlockState[]{doubled,wet}){
            assertFalse(ProjectionAirSeed.singleSlab(invalid));assertThrows(IllegalStateException.class,()->ProjectionAirSeed.placementFace(invalid,Direction.EAST));
        }
        assertFalse(ProjectionAirSeed.singleSlab(Blocks.COBBLESTONE.defaultBlockState()));
    }
    @Test void flowingWaterOptInProtectsSourcesLavaAndOtherBlocks(){
        var hopper=Blocks.HOPPER.defaultBlockState();
        for(int level=1;level<=15;level++){
            var water=Blocks.WATER.defaultBlockState().setValue(net.minecraft.world.level.block.LiquidBlock.LEVEL,level);
            assertTrue(ProjectionAirSeed.targetAllowed(water,hopper,true));
            assertFalse(ProjectionAirSeed.targetAllowed(water,hopper,false));
            assertFalse(ProjectionAirSeed.targetAllowed(water,Blocks.COBBLESTONE.defaultBlockState(),true));
        }
        for(var block:new net.minecraft.world.level.block.Block[]{Blocks.WATER,Blocks.LAVA,Blocks.CHEST,Blocks.AIR})
            assertFalse(ProjectionAirSeed.targetAllowed(block.defaultBlockState(),hopper,true));
        assertTrue(ProjectionAirSeed.targetAllowed(Blocks.AIR.defaultBlockState(),hopper,false));
    }
    @Test void waterFlagMustBeAnExplicitBoolean(){
        assertFalse(ProjectionAirSeed.flowingWaterRequested(new com.google.gson.JsonObject()));
        var r=new com.google.gson.JsonObject();r.addProperty("replace_flowing_water",true);assertTrue(ProjectionAirSeed.flowingWaterRequested(r));
        r.addProperty("replace_flowing_water","true");assertThrows(IllegalArgumentException.class,()->ProjectionAirSeed.flowingWaterRequested(r));
    }
    @Test void surfaceWorkNeverAllowsSubmergedEyesOrLowOxygen(){
        assertTrue(ProjectionAirSeed.surfacePlayerAllowed(true,true,false,225,300));
        assertFalse(ProjectionAirSeed.surfacePlayerAllowed(true,true,false,224,300));
        assertFalse(ProjectionAirSeed.surfacePlayerAllowed(true,false,false,224,300));
        assertFalse(ProjectionAirSeed.surfacePlayerAllowed(true,true,true,300,300));
        assertFalse(ProjectionAirSeed.surfacePlayerAllowed(false,true,false,300,300));
        assertTrue(ProjectionAirSeed.surfacePlayerAllowed(false,false,false,300,300));
    }
    @Test void hopperUsesClickedFaceOppositeItsOutputRatherThanPlayerMotion(){
        for(var facing:new Direction[]{Direction.DOWN,Direction.NORTH,Direction.SOUTH,Direction.EAST,Direction.WEST})
            for(var motion:Direction.values()){
                var expected=Blocks.HOPPER.defaultBlockState().setValue(net.minecraft.world.level.block.HopperBlock.FACING,facing);
                assertEquals(facing.getOpposite(),ProjectionAirSeed.placementFace(expected,motion));
            }
    }
    @Test void directedHopperMustPredictVanillaStateBeforeTheOnlySend()throws Exception {
        var source=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/ProjectionAirSeed.java"));
        assertTrue(source.contains("target.equals(context.getClickedPos())"));
        assertTrue(source.contains("expected.equals(expected.getBlock().getStateForPlacement(context))"));
        assertTrue(source.indexOf("getStateForPlacement(context)")<source.indexOf("void sendOnce"));
    }
    @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    @Test void airWoodPreservesEveryProjectedAxisForDirectAndUnstrippedItems(){
        for(var axis:Direction.Axis.values()){
            var wanted=Blocks.STRIPPED_CHERRY_WOOD.defaultBlockState().setValue(RotatedPillarBlock.AXIS,axis);
            assertEquals(wanted,ProjectionAirSeed.placementState(wanted,"minecraft:stripped_cherry_wood"));
            var raw=ProjectionAirSeed.placementState(wanted,"minecraft:cherry_wood");
            assertEquals(Blocks.CHERRY_WOOD,raw.getBlock());
            assertEquals(axis,raw.getValue(RotatedPillarBlock.AXIS));
        }
    }
    @Test void anotherMaterialOrNonWoodIntermediateIsNeverAdmitted(){
        var wanted=Blocks.STRIPPED_CHERRY_WOOD.defaultBlockState();
        for(String wrong:new String[]{"minecraft:oak_wood","minecraft:cherry_log","minecraft:air","other:cherry_wood"})
            assertThrows(IllegalStateException.class,()->ProjectionAirSeed.placementState(wanted,wrong));
        assertThrows(IllegalStateException.class,()->ProjectionAirSeed.placementState(Blocks.OAK_PLANKS.defaultBlockState(),"minecraft:oak_log"));
        assertEquals(Blocks.COBBLESTONE.defaultBlockState(),ProjectionAirSeed.placementState(Blocks.COBBLESTONE.defaultBlockState(),"minecraft:cobblestone"));
    }
    @Test void clientPredictionAndInventoryDecreaseWithoutServerPacketCannotFinish() {
        assertFalse(ProjectionAirSeedPolicy.confirmed(false,true,64,63,10,30));
        assertFalse(ProjectionAirSeedPolicy.confirmed(true,false,64,63,10,30));
        assertFalse(ProjectionAirSeedPolicy.confirmed(true,true,64,64,10,30));
        assertFalse(ProjectionAirSeedPolicy.confirmed(true,true,64,62,10,30));
    }
    @Test void exactlyOneMaterialAndEightStableTicksConfirmEvenTheLastItem() {
        assertFalse(ProjectionAirSeedPolicy.confirmed(true,true,1,0,10,17));
        assertTrue(ProjectionAirSeedPolicy.confirmed(true,true,1,0,10,18));
        assertTrue(ProjectionAirSeedPolicy.confirmed(true,true,64,63,10,18));
        assertFalse(ProjectionAirSeedPolicy.confirmed(true,true,1,0,-1,18));
    }
    @Test void serverCorrectionInvalidatesSeedAndAnUncertainCellCannotBeReopened() {
        var confirmation=new TerrainServerConfirmation();
        var target=new BlockPos(761024,64,797631);
        confirmation.begin("world","seed",ProjectionAirSeed.STAGE,target,"Block{minecraft:cobblestone}");
        assertFalse(confirmation.serverBlock("world","seed",ProjectionAirSeed.STAGE,target,"Block{minecraft:cobblestone}",true));
        confirmation.sent("world","seed",ProjectionAirSeed.STAGE,target);
        assertTrue(confirmation.serverBlock("world","seed",ProjectionAirSeed.STAGE,target,"Block{minecraft:cobblestone}",true));
        assertFalse(confirmation.serverBlock("world","seed",ProjectionAirSeed.STAGE,target,"Block{minecraft:air}",true));
        assertFalse(confirmation.confirmed("world","seed",ProjectionAirSeed.STAGE,target));
        confirmation.close("seed");
        assertThrows(IllegalStateException.class,()->confirmation.begin("world","retry",ProjectionAirSeed.STAGE,target,"Block{minecraft:cobblestone}"));
    }
    @Test void primitiveTargetsTheExactAirCellAndNeverWritesBlocksOrModuleSettings()throws Exception {
        var helper=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/ProjectionAirSeed.java"));
        assertTrue(helper.contains("new BlockHitResult(Vec3.atCenterOf(target),face,target,false)"));
        assertTrue(helper.contains("expected.getValue(RotatedPillarBlock.AXIS)"));
        assertTrue(helper.contains("!projected.equals(schematic.getBlockState(target))"));
        assertTrue(helper.contains("requires_stripping"));
        assertEquals(1,helper.split("interact\\.invoke\\(",-1).length-1);
        assertTrue(helper.contains("if(sent)throw"));
        assertTrue(helper.contains("LoadedServerChunkEvidence.isServerChunk"));
        assertTrue(helper.contains("targetAllowed(c.level.getBlockState(target),expected,flowingWaterHopper)"));
        assertTrue(helper.contains("confirmation.sent(world,requestId,STAGE,target);sent=true"));
        assertFalse(helper.contains("setBlock("));
        assertFalse(helper.contains("setItem("));
        assertFalse(helper.contains("MeteorModules.enable("));
        assertFalse(helper.contains("MeteorModules.disable("));
        assertFalse(helper.contains("MeteorModules.isActive(MeteorModules.AIR_PLACE)"));
    }
    @Test void printerAndSnapshotResolveInstalledPlayerAirPlaceAndServerHookWiresSeed()throws Exception {
        var printer=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/ProfessionalPrinter.java"));
        var modules=Files.readString(Path.of("src/client/java/dev/twob2tkit/MeteorModules.java"));
        var bridge=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/AutomationBridge.java"));
        assertTrue(printer.contains("AIR=MeteorModules.AIR_PLACE"));
        assertTrue(modules.contains("meteordevelopment.meteorclient.systems.modules.player.AirPlace"));
        assertFalse(printer.contains("systems.modules.world.AirPlace"));
        assertTrue(bridge.contains("airSeedTask.serverBlock(session(c),pos,packetState,applied,ticks)"));
        assertTrue(bridge.contains("projection_air_seed_protocol"));
        assertTrue(bridge.contains("lastAirSeed=completedAirSeed.snapshot(p.equals(\"done\"));completedAirSeed.close()"));
    }
}
