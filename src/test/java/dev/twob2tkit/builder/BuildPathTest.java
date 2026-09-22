package dev.twob2tkit.builder;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.util.*;
import java.util.function.Predicate;
import static org.junit.jupiter.api.Assertions.*;
class BuildPathTest {
    private BuildPath.World world(Predicate<BlockPos> clear){return new BuildPath.World(){public boolean clear(BlockPos p){return clear.test(p);}public boolean edge(BlockPos a,BlockPos b){return true;}};}
    @Test void routesAroundWallInsteadOfRevisitingTheBlockedCell(){
        var w=world(p->p.getY()==0&&p.getX()>=0&&p.getX()<=4&&p.getZ()>=0&&p.getZ()<=2&&!(p.getX()==2&&p.getZ()<2));
        var r=BuildPath.find(w,new BlockPos(0,0,0),p->p.equals(new BlockPos(4,0,0)),100);
        assertFalse(r.nodes().isEmpty());assertTrue(r.nodes().stream().anyMatch(p->p.getZ()==2));
        for(int i=1;i<r.nodes().size();i++)assertEquals(1,r.nodes().get(i).distManhattan(r.nodes().get(i-1)));
    }
    @Test void canChangeAltitudeThroughAnActualOpening(){
        var w=world(p->p.getX()>=0&&p.getX()<=2&&p.getZ()==0&&p.getY()>=0&&p.getY()<=2&&(p.getY()!=1||p.getX()==0));
        var r=BuildPath.find(w,new BlockPos(2,0,0),p->p.equals(new BlockPos(2,2,0)),100);
        assertTrue(r.nodes().contains(new BlockPos(0,1,0)));
    }
    @Test void collisionCheckedEdgesPreventCuttingThroughObstacles(){
        var r=BuildPath.find(new BuildPath.World(){public boolean clear(BlockPos p){return p.getY()==0&&p.getZ()==0&&p.getX()>=0&&p.getX()<=2;}public boolean edge(BlockPos a,BlockPos b){return b.getX()!=1;}},new BlockPos(0,0,0),p->p.getX()==2,100);
        assertTrue(r.nodes().isEmpty());
    }
    @Test void searchIsBoundedAndNeverReturnsAPathFromAnOccupiedStart(){
        var r=BuildPath.find(world(p->true),BlockPos.ZERO,p->false,32);assertTrue(r.nodes().isEmpty());assertEquals(32,r.expanded());
        assertEquals(0,BuildPath.find(world(p->false),BlockPos.ZERO,p->true,100).expanded());
    }
    @Test void depotSearchReachesAcrossOpenSpaceWithoutExploringAnEntireCube(){
        var r=BuildPath.find(world(p->true),BlockPos.ZERO,List.of(new BlockPos(60,0,0)),100);
        assertEquals(61,r.nodes().size());assertTrue(r.expanded()<=100);
    }
    @Test void goalAwareSearchStillUsesDoorwayAndCollisionCheckedEdges(){
        var w=world(p->p.getY()==0&&p.getX()>=0&&p.getX()<=8&&p.getZ()>=0&&p.getZ()<=4&&!(p.getX()==4&&p.getZ()<4));
        var r=BuildPath.find(w,BlockPos.ZERO,List.of(new BlockPos(8,0,0)),100);
        assertFalse(r.nodes().isEmpty());assertTrue(r.nodes().contains(new BlockPos(4,0,4)));
        for(int n=1;n<r.nodes().size();n++)assertEquals(1,r.nodes().get(n).distManhattan(r.nodes().get(n-1)));
    }

    @Test void incrementalSearchPreservesFrontierAcrossSmallSlices(){
        var search=new BuildPath.GoalSearch(world(p->true),BlockPos.ZERO,List.of(new BlockPos(60,0,0)));
        BuildPath.Result result=null;int slices=0;
        while(result==null&&slices++<30){int before=search.expanded();result=search.advance(3,Long.MAX_VALUE);assertTrue(search.expanded()-before<=3);}
        assertNotNull(result);assertEquals(61,result.nodes().size());assertTrue(slices>1);
        assertEquals(result,search.advance(3,Long.MAX_VALUE));
    }
    @Test void pendingBudgetAndExhaustedFrontierHaveDifferentResults(){
        var search=new BuildPath.GoalSearch(world(p->p.getY()==0&&p.getZ()==0&&p.getX()>=0&&p.getX()<=3),BlockPos.ZERO,List.of(new BlockPos(5,0,0)));
        assertNull(search.advance(2,Long.MAX_VALUE));assertEquals(2,search.expanded());
        var result=search.advance(2,Long.MAX_VALUE);assertNotNull(result);assertTrue(result.nodes().isEmpty());assertEquals(4,result.expanded());
    }
    @Test void expiredTimeSliceKeepsWorkForTheNextTick(){
        var search=new BuildPath.GoalSearch(world(p->true),BlockPos.ZERO,List.of(new BlockPos(5,0,0)));
        assertNull(search.advance(100,System.nanoTime()-1));assertEquals(0,search.expanded());
        assertEquals(6,search.advance(100,Long.MAX_VALUE).nodes().size());
    }
    @Test void incrementalSearchStillRejectsBlockedEdges(){
        var w=new BuildPath.World(){public boolean clear(BlockPos p){return p.getY()==0&&p.getZ()==0&&p.getX()>=0&&p.getX()<=3;}public boolean edge(BlockPos a,BlockPos b){return b.getX()!=2;}};
        var search=new BuildPath.GoalSearch(w,BlockPos.ZERO,List.of(new BlockPos(3,0,0)));
        assertNull(search.advance(1,Long.MAX_VALUE));
        var result=search.advance(1,Long.MAX_VALUE);assertNotNull(result);assertTrue(result.nodes().isEmpty());
    }
}
