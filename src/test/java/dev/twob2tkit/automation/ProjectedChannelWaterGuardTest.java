package dev.twob2tkit.automation;

import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import net.minecraft.core.BlockPos;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class ProjectedChannelWaterGuardTest {
    @Test void ordinaryBucketModeIsUnchangedUnlessExplicitlyEnabled(){
        assertFalse(ProjectedChannelWaterGuard.requested(JsonParser.parseString("{}").getAsJsonObject()));
        assertFalse(ProjectedChannelWaterGuard.requested(JsonParser.parseString("{\"projected_water_channel\":false}").getAsJsonObject()));
        assertTrue(ProjectedChannelWaterGuard.requested(JsonParser.parseString("{\"projected_water_channel\":true}").getAsJsonObject()));
        for(String value:new String[]{"null","1","\"true\"","[]"})
            assertThrows(IllegalArgumentException.class,()->ProjectedChannelWaterGuard.requested(
                JsonParser.parseString("{\"projected_water_channel\":"+value+"}").getAsJsonObject()));
    }
    @Test void directionLengthAndLockedSelectionCannotBeInferred(){
        assertDoesNotThrow(()->new ProjectedChannelWaterGuard(JsonParser.parseString(
            "{\"placement_key\":\"p\",\"channel_direction\":\"west\",\"channel_length\":8}").getAsJsonObject(),BlockPos.ZERO));
        for(String value:new String[]{"{}","{\"placement_key\":\"p\"}",
            "{\"placement_key\":\"p\",\"channel_direction\":\"east\",\"channel_length\":8}",
            "{\"placement_key\":\"p\",\"channel_direction\":\"west\",\"channel_length\":7}",
            "{\"placement_key\":\"p\",\"channel_direction\":\"west\",\"channel_length\":8.5}",
            "{\"placement_key\":\"p\",\"channel_direction\":\"west\",\"channel_length\":\"8\"}"})
            assertThrows(RuntimeException.class,()->new ProjectedChannelWaterGuard(JsonParser.parseString(value).getAsJsonObject(),BlockPos.ZERO));
    }
    @Test void newGeometryUsesOriginalBucketReceiptsAndNeverChangesTheWorldDirectly()throws Exception{
        var base=Path.of("src/client/java/dev/twob2tkit/automation");
        var guard=Files.readString(base.resolve("ProjectedChannelWaterGuard.java"));
        assertTrue(guard.contains("LoadedServerChunkEvidence.isServerChunk"));
        assertTrue(guard.contains("model.getBlockState(floor).equals(c.level.getBlockState(floor))"));
        assertTrue(guard.contains("TrapDoorBlock.WATERLOGGED"));
        assertTrue(guard.contains("i==0&&actualRoof.isAir()"));
        assertFalse(guard.contains("setBlock("));assertFalse(guard.contains("useItem("));
        var action=Files.readString(base.resolve("BucketWaterAction.java"));
        assertTrue(action.contains("projectedChannel.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()))"));
        assertTrue(action.contains("BucketUseStore.claim(claimPath,claim);receipt.sendOnce()"));
        assertTrue(action.contains("inventoryUnchanged(c,true)"));
        assertTrue(action.contains("mode!=BucketWaterPolicy.Mode.PLACE||column||drain"));
    }
}
