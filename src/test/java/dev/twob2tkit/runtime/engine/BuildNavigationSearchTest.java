package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.BuildNavigation;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import org.junit.jupiter.api.Test;
import java.util.*;
import java.util.function.Predicate;
import static org.junit.jupiter.api.Assertions.*;

class BuildNavigationSearchTest {
    private BuildNavigation.World world(Predicate<BlockPos> clear){
        return new BuildNavigation.World(){
            public boolean clear(BlockPos p){return clear.test(p);}
            public boolean edge(BlockPos a,BlockPos b){return true;}
        };
    }
    private BuildNavigation.Result finish(BuildNavigation.Search search,int budget){
        BuildNavigation.Result result=null;
        while(result==null&&search.expanded()<budget){
            int before=search.expanded();
            result=search.advance(Math.min(7,budget-before),Long.MAX_VALUE);
            assertTrue(search.expanded()-before<=7,"Search must preserve the caller's slice budget");
        }
        return result;
    }
    private void legalPath(BuildNavigation.World world,BlockPos start,Set<BlockPos> goals,List<BlockPos> path){
        assertFalse(path.isEmpty());assertEquals(start,path.getFirst());assertTrue(goals.contains(path.getLast()));
        for(var p:path)assertTrue(world.clear(p));
        for(int i=1;i<path.size();i++){
            assertEquals(1,path.get(i-1).distManhattan(path.get(i)));
            assertTrue(world.edge(path.get(i-1),path.get(i)),"Every returned edge is checked in travel direction");
        }
    }

    @Test void oneWayEdgesAreCheckedFromPredecessorToCurrentNotBackwards(){
        var w=new BuildNavigation.World(){
            public boolean clear(BlockPos p){return p.getY()==0&&p.getZ()==0&&p.getX()>=0&&p.getX()<=4;}
            public boolean edge(BlockPos from,BlockPos to){return to.getX()==from.getX()+1;}
        };
        var goal=new BlockPos(4,0,0);
        var result=finish(new DefaultBuildNavigation.GoalSearch(w,BlockPos.ZERO,List.of(goal)),20);
        assertNotNull(result);assertEquals(5,result.nodes().size());legalPath(w,BlockPos.ZERO,Set.of(goal),result.nodes());
        var forbidden=finish(new DefaultBuildNavigation.GoalSearch(w,goal,List.of(BlockPos.ZERO)),20);
        assertNotNull(forbidden);assertTrue(forbidden.nodes().isEmpty());
    }

    @Test void sealedNearGoalsCannotConsumeTheBudgetBeforeFarReachableGoal(){
        var sealed=Set.of(new BlockPos(0,2,0),new BlockPos(0,22,0),new BlockPos(0,45,0),new BlockPos(0,67,0));
        var w=world(p->p.getX()>=-12&&p.getX()<=14&&p.getZ()>=-10&&p.getZ()<=10
            &&p.getY()>=0&&p.getY()<=129&&sealed.stream().noneMatch(goal->p.distManhattan(goal)==1));
        var start=new BlockPos(11,124,0);var reachable=new BlockPos(11,0,0);
        var goals=new HashSet<>(sealed);goals.add(reachable);
        var result=finish(new DefaultBuildNavigation.GoalSearch(w,start,goals),160);
        assertNotNull(result,"Do not explore the ~74k-cell external air volume around sealed stations");
        legalPath(w,start,goals,result.nodes());assertEquals(reachable,result.nodes().getLast());
        assertEquals(125,result.nodes().size());assertTrue(result.expanded()<160);
    }

    @Test void allSealedGoalsReturnNoPathByExhaustingOnlyTheirComponents(){
        var goals=Set.of(new BlockPos(0,22,0),new BlockPos(0,67,0));
        var w=world(p->goals.stream().noneMatch(goal->p.distManhattan(goal)==1));
        var result=finish(new DefaultBuildNavigation.GoalSearch(w,new BlockPos(11,124,0),goals),10);
        assertNotNull(result);assertTrue(result.nodes().isEmpty());assertEquals(2,result.expanded());
    }

    @Test void startItselfIsTheGoalAndKeepsStableStartToGoalResult(){
        var start=new BlockPos(3,4,5);var search=new DefaultBuildNavigation.GoalSearch(world(p->true),start,List.of(start,new BlockPos(9,8,7)));
        assertNull(search.advance(0,Long.MAX_VALUE));assertEquals(0,search.expanded());
        var result=search.advance(1,Long.MAX_VALUE);
        assertEquals(List.of(start),result.nodes());assertEquals(1,result.expanded());
        assertEquals(result,search.advance(100,Long.MAX_VALUE));
    }

    @Test void shortestReachableGoalWinsEvenWhenAnotherIsCloserInStraightLine(){
        var w=world(p->p.getY()==0&&p.getX()>=0&&p.getX()<=2&&p.getZ()>=0&&p.getZ()<=4
            &&!(p.getX()==1&&p.getZ()<4));
        var near=new BlockPos(2,0,0);var shortRoute=new BlockPos(0,0,4);var goals=Set.of(near,shortRoute);
        var result=finish(new DefaultBuildNavigation.GoalSearch(w,BlockPos.ZERO,goals),40);
        assertNotNull(result);legalPath(w,BlockPos.ZERO,goals,result.nodes());
        assertEquals(shortRoute,result.nodes().getLast());assertEquals(5,result.nodes().size());
    }

    @Test void occupiedEndpointsNeverProducePathsAndExpiredSlicesDoNotConsumeFrontier(){
        var line=world(p->p.getY()==0&&p.getZ()==0&&p.getX()>=0&&p.getX()<=3);
        var occupied=new DefaultBuildNavigation.GoalSearch(line,BlockPos.ZERO,List.of(new BlockPos(4,0,0)));
        assertTrue(occupied.advance(1,Long.MAX_VALUE).nodes().isEmpty());assertEquals(0,occupied.expanded());
        var badStart=new DefaultBuildNavigation.GoalSearch(line,new BlockPos(4,0,0),List.of(BlockPos.ZERO));
        assertTrue(badStart.advance(1,Long.MAX_VALUE).nodes().isEmpty());
        var pending=new DefaultBuildNavigation.GoalSearch(line,BlockPos.ZERO,List.of(new BlockPos(3,0,0)));
        assertNull(pending.advance(100,System.nanoTime()-1));assertEquals(0,pending.expanded());
        assertEquals(4,finish(pending,10).nodes().size());
    }

    @Test void returnedPathsMatchIndependentForwardBreadthFirstSearchOnDirectedWorlds(){
        var start=new BlockPos(0,0,0);var goals=Set.of(new BlockPos(5,0,5),new BlockPos(5,2,0),new BlockPos(0,1,5));
        for(int seed=0;seed<20;seed++){
            int salt=seed;
            var w=new BuildNavigation.World(){
                public boolean clear(BlockPos p){
                    return p.getX()>=0&&p.getX()<=5&&p.getY()>=0&&p.getY()<=2&&p.getZ()>=0&&p.getZ()<=5
                        &&(p.equals(start)||goals.contains(p)||Math.floorMod(p.asLong()+salt*17L,9)!=0);
                }
                public boolean edge(BlockPos a,BlockPos b){return Math.floorMod(a.asLong()*31+b.asLong()+salt,7)!=0;}
            };
            int expected=forwardDistance(w,start,goals);
            var result=finish(new DefaultBuildNavigation.GoalSearch(w,start,goals),200);
            assertNotNull(result);
            if(expected<0)assertTrue(result.nodes().isEmpty());
            else{legalPath(w,start,goals,result.nodes());assertEquals(expected+1,result.nodes().size(),"seed="+seed);}
        }
    }

    private int forwardDistance(BuildNavigation.World world,BlockPos start,Set<BlockPos> goals){
        var queue=new ArrayDeque<BlockPos>();var distance=new HashMap<BlockPos,Integer>();queue.add(start);distance.put(start,0);
        while(!queue.isEmpty()){
            var current=queue.removeFirst();int cost=distance.get(current);
            if(goals.contains(current))return cost;
            for(var direction:Direction.values()){
                var next=current.relative(direction);
                if(!distance.containsKey(next)&&world.clear(next)&&world.edge(current,next)){
                    distance.put(next,cost+1);queue.addLast(next);
                }
            }
        }
        return -1;
    }
}
