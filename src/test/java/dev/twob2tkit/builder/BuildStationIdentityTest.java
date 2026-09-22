package dev.twob2tkit.builder;
import net.minecraft.world.phys.Vec3;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BuildStationIdentityTest {
 @Test void smallFlightDriftDoesNotTurnAnExhaustedStationIntoANewStation(){
  var intended=ProjectionBuildJob.stationKey(new Vec3(15.491,67.055,836.398));
  assertEquals(new BlockPos(15,67,836),intended);
  assertEquals(intended,ProjectionBuildJob.stationKey(new Vec3(15.491,66.864,836.398)));
  assertNotEquals(intended,ProjectionBuildJob.stationKey(new Vec3(15.491,68.02,836.398)));
 }
}
