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
    @Test void exactOptionalWestCeilingIsValidatedAndLegacySourceRemainsDefault(){
        var r=JsonParser.parseString("{\"placement_key\":\"p\",\"channel_direction\":\"west\",\"channel_length\":8}").getAsJsonObject();
        var source=new BlockPos(20,63,30);
        assertEquals(source.above(),new ProjectedChannelWaterGuard(r,source).serviceCeiling());
        r.add("channel_service_ceiling",JsonParser.parseString("[19,64,30]"));
        assertEquals(new BlockPos(19,64,30),new ProjectedChannelWaterGuard(r,source).serviceCeiling());
        for(String bad:new String[]{"null","{}","[19,64]","[19.5,64,30]","[\"19\",64,30]","[18,64,30]","[21,64,30]","[19,63,30]","[19,64,31]","[2147483648,64,30]"}){
            r.add("channel_service_ceiling",JsonParser.parseString(bad));
            assertThrows(RuntimeException.class,()->new ProjectedChannelWaterGuard(r,source));
        }
    }
    @Test void newGeometryUsesOriginalBucketReceiptsAndNeverChangesTheWorldDirectly()throws Exception{
        var base=Path.of("src/client/java/dev/twob2tkit/automation");
        var guard=Files.readString(base.resolve("ProjectedChannelWaterGuard.java"));
        assertTrue(guard.contains("LoadedServerChunkEvidence.isServerChunk"));
        assertTrue(guard.contains("model.getBlockState(floor).equals(c.level.getBlockState(floor))"));
        assertTrue(guard.contains("TrapDoorBlock.WATERLOGGED"));
        assertTrue(guard.contains("ProjectedChannelCeilingPolicy.roof"));
        assertFalse(guard.contains("setBlock("));assertFalse(guard.contains("useItem("));
        var action=Files.readString(base.resolve("BucketWaterAction.java"));
        assertTrue(action.contains("projectedChannel.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()))"));
        assertTrue(action.contains("BucketUseStore.claim(claimPath,claim);receipt.sendOnce()"));
        assertTrue(action.contains("inventoryUnchanged(c,true)"));
        assertTrue(action.contains("mode!=BucketWaterPolicy.Mode.PLACE||column||drain"));
    }
}
