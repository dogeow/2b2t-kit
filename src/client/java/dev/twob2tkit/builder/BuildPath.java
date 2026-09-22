package dev.twob2tkit.builder;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import java.util.*;
import java.util.function.Predicate;

/** Bounded cardinal routes through verified empty body space, not a straight line into a target block. */
public final class BuildPath {
    private BuildPath() {}
    public interface World { boolean clear(BlockPos p); boolean edge(BlockPos from,BlockPos to); }
    public record Result(List<BlockPos> nodes,int expanded) {}
    public static Result find(World world,BlockPos start,Predicate<BlockPos> goal,int budget){
        if(!world.clear(start))return new Result(List.of(),0);
        var queue=new ArrayDeque<BlockPos>();var parent=new HashMap<BlockPos,BlockPos>();queue.add(start);parent.put(start,null);int n=0;
        while(!queue.isEmpty() && n<budget){
            var p=queue.remove();n++;
            if(goal.test(p)){var path=new LinkedList<BlockPos>();for(var q=p;q!=null;q=parent.get(q))path.addFirst(q);return new Result(List.copyOf(path),n);}
            for(var d:Direction.values()){
                var q=p.relative(d);if(parent.containsKey(q)||!world.clear(q)||!world.edge(p,q))continue;
                parent.put(q,p);queue.add(q);
            }
        }
        return new Result(List.of(),n);
    }
    /** Compatibility wrapper for callers that deliberately request one bounded search. */
    public static Result find(World world,BlockPos start,Collection<BlockPos> goals,int budget){
        var search=new GoalSearch(world,start,goals);
        var result=search.advance(budget,Long.MAX_VALUE);
        return result==null?new Result(List.of(),search.expanded()):result;
    }
    /** Resumable A*. A null slice result means pending, never proof that a path is absent. */
    public static final class GoalSearch {
        private final dev.twob2tkit.runtime.api.BuildNavigation.Search delegate;
        public GoalSearch(World world,BlockPos start,Collection<BlockPos> goals){
            delegate=new dev.twob2tkit.runtime.engine.DefaultBuildNavigation().search(new dev.twob2tkit.runtime.api.BuildNavigation.World(){
                public boolean clear(BlockPos p){return world.clear(p);}public boolean edge(BlockPos a,BlockPos b){return world.edge(a,b);}
            },start,goals);
        }
        public int expanded(){return delegate.expanded();}
        public Result advance(int maxNodes,long deadlineNanos){var r=delegate.advance(maxNodes,deadlineNanos);return r==null?null:new Result(r.nodes(),r.expanded());}
    }
}
