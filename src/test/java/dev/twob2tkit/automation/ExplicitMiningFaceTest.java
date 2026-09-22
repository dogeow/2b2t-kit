package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ExplicitMiningFaceTest {
 @Test void miningUsesTheVisibleFaceSelectedByTheApproach(){
  var r=new JsonObject();r.addProperty("face","west");var aim=AutomationBridge.blockAim(new BlockPos(18,69,33),r);
  assertEquals(18.001,aim.x,1e-8);assertEquals(69.5,aim.y);assertEquals(33.5,aim.z);
 }
 @Test void legacyUnspecifiedMiningKeepsItsCenterAim(){
  var aim=AutomationBridge.blockAim(new BlockPos(18,69,33),new JsonObject());assertEquals(18.5,aim.x);
 }
 @Test void invalidFacesAreRejected(){var r=new JsonObject();r.addProperty("face","teleport");assertThrows(IllegalArgumentException.class,()->AutomationBridge.blockAim(BlockPos.ZERO,r));}
}
