package dev.twob2tkit.runtime.engine;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BorerPeekSideAngleTest {
 @Test void highVerticalRetryNeedsARealSidePosition(){
  var mob=new Vec3(0,72,0);
  assertFalse(BorerCombatPeek.sideAngleUseful(new Vec3(.2,87,.2),mob));
  assertFalse(BorerCombatPeek.sideAngleUseful(new Vec3(1.5,87,0),mob));
  assertTrue(BorerCombatPeek.sideAngleUseful(new Vec3(6,87,0),mob));
 }
 @Test void ordinaryLowPositionsAndHigherEnemiesKeepTheirExistingPath(){
  assertTrue(BorerCombatPeek.sideAngleUseful(new Vec3(0,75,0),new Vec3(0,72,0)));
  assertTrue(BorerCombatPeek.sideAngleUseful(new Vec3(0,70,0),new Vec3(0,72,0)));
  assertFalse(BorerCombatPeek.sideAngleUseful(new Vec3(Double.NaN,87,0),new Vec3(0,72,0)));
 }
}
