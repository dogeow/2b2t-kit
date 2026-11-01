package dev.twob2tkit.runtime.engine;

import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.*;
import dev.twob2tkit.runtime.api.BuildNavigation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class NavigationHostileClearanceTest {
 private static AABB body(double x,double y,double z){return new AABB(x+.2,y+.02,z+.2,x+.8,y+1.82,z+.8);}
 private static NavigationHostileClearance.Threat threat(NavigationHostileClearance.Kind kind,AABB box){
  return new NavigationHostileClearance.Threat(kind,box,new Vec3((box.minX+box.maxX)*.5,box.maxY-.1,(box.minZ+box.maxZ)*.5),true);
 }
 @Test void creeperRadiusDoesNotTreatAnOccludingWallAsBlastProof(){
  var k=NavigationHostileClearance.Kind.CREEPER;
  assertFalse(NavigationHostileClearance.permit(k,true,64,false));
  assertTrue(NavigationHostileClearance.permit(k,true,64.01,false));
  assertFalse(NavigationHostileClearance.permit(NavigationHostileClearance.Kind.CHARGED_CREEPER,true,100,false));
  assertTrue(NavigationHostileClearance.permit(NavigationHostileClearance.Kind.CHARGED_CREEPER,true,144.01,false));
 }
 @Test void rangedThreatNeedsRealCoverWhileDistantMeleeDoesNotBlockAllConstruction(){
  var r=NavigationHostileClearance.Kind.RANGED;var m=NavigationHostileClearance.Kind.MELEE;
  assertFalse(NavigationHostileClearance.permit(r,true,100,true));
  assertTrue(NavigationHostileClearance.permit(r,true,100,false));
  assertTrue(NavigationHostileClearance.permit(r,true,401,true));
  assertFalse(NavigationHostileClearance.permit(m,true,9,true));
  assertTrue(NavigationHostileClearance.permit(m,true,9.01,true));
  assertTrue(NavigationHostileClearance.permit(m,true,4,false));
 }
 @Test void missingCurrentEntityOrInvalidDistanceNeverAuthorizesApproach(){
  for(var k:NavigationHostileClearance.Kind.values()){
   assertFalse(NavigationHostileClearance.permit(k,false,0,false));
   assertFalse(NavigationHostileClearance.permit(k,true,Double.NaN,false));
   assertFalse(NavigationHostileClearance.permit(k,true,-1,false));
  }
 }
 @Test void hidingOnlyTheEyesDoesNotHideExposedFeet(){
  var mob=threat(NavigationHostileClearance.Kind.RANGED,new AABB(8,0,0,8.6,1.8,.6));
  assertFalse(NavigationHostileClearance.safe(body(0,0,0),List.of(mob),(a,b)->b.y<.3));
  assertTrue(NavigationHostileClearance.safe(body(0,0,0),List.of(mob),(a,b)->false));
 }
 @Test void previouslyObservedLowerCorridorThreatExcludesTheUnsafeCandidate(){
  // Geometry from an earlier observed corridor threat; not a replay of entity state.
  var creeper=threat(NavigationHostileClearance.Kind.CREEPER,
   new AABB(761418.85,61,793995.55,761419.45,62.7,793996.15));
  assertFalse(NavigationHostileClearance.safe(body(761416,60,793989),List.of(creeper),(a,b)->false));
  assertTrue(NavigationHostileClearance.safe(body(761416,73,793989),List.of(creeper),(a,b)->false));
 }
 @Test void directShortcutAndGridRouteBothAvoidTheOccupiedDangerZone(){
  var creep=threat(NavigationHostileClearance.Kind.CREEPER,new AABB(9.7,0,-.3,10.3,1.7,.3));
  java.util.function.Predicate<BlockPos> safe=p->NavigationHostileClearance.safe(body(p.getX(),p.getY(),p.getZ()),List.of(creep),(a,b)->false);
  var nav=new DefaultBuildNavigation(safe);var w=new BuildNavigation.World(){
   public boolean clear(BlockPos p){return p.getY()==0&&p.getX()>=0&&p.getX()<=20&&p.getZ()>=0&&p.getZ()<=12;}
   public boolean edge(BlockPos a,BlockPos b){return true;}
  };
  var search=nav.search(w,BlockPos.ZERO,List.of(new BlockPos(20,0,0)));BuildNavigation.Result result=null;
  while(result==null)result=search.advance(256,Long.MAX_VALUE);
  assertFalse(result.nodes().isEmpty());assertTrue(result.nodes().size()>2);
  assertTrue(result.nodes().stream().allMatch(safe));
 }
 @Test void newThreatStopsAnAlreadyPlannedStepWithoutFakeArrivalAndClearanceCanResume(){
  var proposed=new BuildNavigation.Motion(false,true,.024,new Vec3(.1,-.1,0));
  var stopped=DefaultBuildNavigation.guardedMotion(proposed,false);
  assertFalse(stopped.arrived());assertEquals(0,stopped.speed());assertEquals(Vec3.ZERO,stopped.probe());
  assertSame(proposed,DefaultBuildNavigation.guardedMotion(proposed,true));
 }
 @Test void aDistantThreatDoesNotRequireAnUnnecessaryVisibilityProbe(){
  var mob=threat(NavigationHostileClearance.Kind.RANGED,new AABB(30,0,0,30.6,1.8,.6));
  assertTrue(NavigationHostileClearance.safe(body(0,0,0),List.of(mob),(a,b)->{fail("No distant ray needed");return true;}));
 }
}
