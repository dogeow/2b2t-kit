package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
class GuardEndermanGazePolicyTest {
 @Test void aHoverDirectlyAboveTheMobLooksUpInsteadOfAtItsHead(){
  var d=GuardEndermanGazePolicy.direction(new double[]{761428,87,793972},List.of(new double[]{761428,75,793972}));
  assertArrayEquals(new double[]{0,1,0},d,1e-10);
 }
 @Test void aGroundPlayerLooksDownWhenTheMobsEyesAreAbove(){
  assertArrayEquals(new double[]{0,-1,0},GuardEndermanGazePolicy.direction(new double[]{0,1.62,0},List.of(new double[]{0,2.55,0})),1e-10);
 }
 @Test void mobsAboveAndBelowSelectASidewaysGaze(){
  var d=GuardEndermanGazePolicy.direction(new double[]{0,0,0},List.of(new double[]{0,5,0},new double[]{0,-5,0}));
  assertEquals(0,d[1],1e-10);assertEquals(1,Math.hypot(d[0],d[2]),1e-10);
 }
 @Test void chosenGazeIsFiniteAndAvoidsEveryWitnessedMob(){
  var targets=List.of(new double[]{2,-10,1},new double[]{-3,-7,2},new double[]{1,-6,-5});
  var d=GuardEndermanGazePolicy.direction(new double[]{0,0,0},targets);
  assertEquals(1,Math.sqrt(d[0]*d[0]+d[1]*d[1]+d[2]*d[2]),1e-10);
  for(var t:targets)assertTrue(d[0]*t[0]+d[1]*t[1]+d[2]*t[2]<0);
 }
 @Test void absentInvalidOrCoincidentPositionsDoNotInventAGaze(){
  var eye=new double[]{0,0,0};assertNull(GuardEndermanGazePolicy.direction(eye,List.of()));
  assertNull(GuardEndermanGazePolicy.direction(eye,List.of(new double[]{0,0,0})));
  assertNull(GuardEndermanGazePolicy.direction(eye,List.of(new double[]{Double.NaN,2,3})));
  assertNull(GuardEndermanGazePolicy.direction(new double[]{Double.POSITIVE_INFINITY,0,0},List.of(new double[]{0,1,0})));
 }
}
