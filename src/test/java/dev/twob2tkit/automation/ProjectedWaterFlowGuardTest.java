package dev.twob2tkit.automation;

import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProjectedWaterFlowGuardTest {
    @Test void ordinaryBucketCallsRemainOptedOutAndStringsCannotEnableLongFlow(){
        assertFalse(ProjectedWaterFlowGuard.requested(JsonParser.parseString("{}").getAsJsonObject()));
        assertFalse(ProjectedWaterFlowGuard.requested(JsonParser.parseString("{\"projected_water_column\":false}").getAsJsonObject()));
        assertTrue(ProjectedWaterFlowGuard.requested(JsonParser.parseString("{\"projected_water_column\":true}").getAsJsonObject()));
        for(String value:new String[]{"\"true\"","1","null","[]"})
            assertThrows(IllegalArgumentException.class,()->ProjectedWaterFlowGuard.requested(
                JsonParser.parseString("{\"projected_water_column\":"+value+"}").getAsJsonObject()));
    }
    @Test void downstreamBoundsAndPlacementAreExplicitAndBounded(){
        for(String data:new String[]{"{}","{\"placement_key\":\"p\"}",
            "{\"placement_key\":\"p\",\"water_column_bounds\":{\"min\":[0,0,0],\"max\":[32,191,32]}}",
            "{\"placement_key\":\"p\",\"water_column_bounds\":{\"min\":[0,0.5,0],\"max\":[8,130,8]}}"})
            assertThrows(RuntimeException.class,()->new ProjectedWaterFlowGuard(JsonParser.parseString(data).getAsJsonObject(),net.minecraft.core.BlockPos.ZERO));
    }
}
