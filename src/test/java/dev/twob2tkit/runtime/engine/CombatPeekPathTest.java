package dev.twob2tkit.runtime.engine;
import java.util.*;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class CombatPeekPathTest {
 @Test void findsVisibleAirAroundWallUsingOnlyOrthogonalSteps(){
  var start=new BlockPos(0,0,0);
  var path=CombatPeekPath.find(new CombatPeekPath.World(){
   public boolean clear(BlockPos p){return p.getY()==0&&!(p.getX()==1&&p.getZ()==0);}
   public boolean edge(BlockPos a,BlockPos b){return true;}
   public boolean visible(BlockPos p){return p.equals(new BlockPos(2,0,0));}
  },start,3,200);
  assertFalse(path.isEmpty());assertFalse(path.contains(new BlockPos(1,0,0)));
  for(int i=1;i<path.size();i++)assertEquals(1,path.get(i).distManhattan(path.get(i-1)));
 }
 @Test void refusesSealedRoutesAndOutOfBoundsTargets(){
  var start=BlockPos.ZERO;
  var w=new CombatPeekPath.World(){public boolean clear(BlockPos p){return p.getY()==0;}public boolean edge(BlockPos a,BlockPos b){return false;}public boolean visible(BlockPos p){return !p.equals(start);}};
  assertTrue(CombatPeekPath.find(w,start,4,200).isEmpty());
  var far=new CombatPeekPath.World(){public boolean clear(BlockPos p){return p.getY()==0;}public boolean edge(BlockPos a,BlockPos b){return true;}public boolean visible(BlockPos p){return p.getX()>5;}};
  assertTrue(CombatPeekPath.find(far,start,4,200).isEmpty());
 }
 @Test void budgetExhaustionNeverInventsAPath(){
  var w=new CombatPeekPath.World(){public boolean clear(BlockPos p){return true;}public boolean edge(BlockPos a,BlockPos b){return true;}public boolean visible(BlockPos p){return false;}};
  assertTrue(CombatPeekPath.find(w,BlockPos.ZERO,12,5).isEmpty());
 }
}
