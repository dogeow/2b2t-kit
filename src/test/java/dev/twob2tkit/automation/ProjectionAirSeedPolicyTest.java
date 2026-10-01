package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionAirSeedPolicyTest {
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
        assertTrue(helper.contains("new BlockHitResult(Vec3.atCenterOf(target),c.player.getMotionDirection().getOpposite(),target,false)"));
        assertEquals(1,helper.split("interact\\.invoke\\(",-1).length-1);
        assertTrue(helper.contains("if(sent)throw"));
        assertTrue(helper.contains("LoadedServerChunkEvidence.isServerChunk"));
        assertTrue(helper.contains("getBlockState(target).isAir()"));
        assertTrue(helper.contains("confirmation.sent(world,requestId,STAGE,target);sent=true"));
        assertFalse(helper.contains("setBlock("));
        assertFalse(helper.contains("setItem("));
        assertFalse(helper.contains("MeteorModules.enable("));
        assertFalse(helper.contains("MeteorModules.disable("));
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
