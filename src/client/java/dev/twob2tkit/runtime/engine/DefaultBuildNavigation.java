package dev.twob2tkit.runtime.engine;
import dev.twob2tkit.runtime.api.BuildNavigation;
import net.minecraft.core.*;
import net.minecraft.world.phys.Vec3;
import java.util.*;
/** Hot-reloadable construction navigation. Never references host implementation classes. */
public final class DefaultBuildNavigation implements BuildNavigation {
    public String version(){return EngineBuildVersion.VALUE;}
    public Policy policy(){return new Policy(256,4_000_000L,50000,6,100,50);}
    public Search search(World world,BlockPos start,Collection<BlockPos> goals){return new GoalSearch(world,start,goals);}
    public List<BlockPos> stations(BlockPos target){
        var cells=new ArrayList<BlockPos>();
        for(int dx=-3;dx<=3;dx++)for(int dz=-3;dz<=3;dz++)for(int dy=-3;dy<=2;dy++){
            double eyeDeltaY=dy+1.14;
            if(dx*dx+dz*dz+eyeDeltaY*eyeDeltaY>4.15*4.15||dx==0&&dz==0&&dy<=0)continue;
            cells.add(target.offset(dx,dy,dz));
        }return cells;
    }
    public Motion motion(Vec3 delta){
        // Feet waypoints sit 0.02 above the grid; accept the real collision floor
        // and tiny Flight rounding instead of blocking horizontal movement on a micro-step.
        // The host still collision-checks every proposed movement.
        double horizontal=Math.hypot(delta.x,delta.z);boolean vertical=Math.abs(delta.y)>.025001;
        boolean arrived=horizontal<.005001&&!vertical;
        // Move briskly between path cells, then taper before the exact station.
        // The collision probe below remains ahead of the actual movement.
        double speed=arrived?0:vertical?Math.min(.024,Math.abs(delta.y)/10):Math.min(.024,horizontal/20);
        Vec3 probe=arrived?Vec3.ZERO:vertical?new Vec3(0,Math.copySign(speed*5,delta.y),0):new Vec3(delta.x,0,delta.z).normalize().scale(speed*10);
        return new Motion(arrived,vertical,speed,probe);
    }
    public static final class GoalSearch implements BuildNavigation.Search {
        private record Node(BlockPos pos,int g,int h){}
        private final BuildNavigation.World world;
        private final BlockPos start;
        private final Map<BlockPos,BlockPos> parent=new HashMap<>();
        private final Map<BlockPos,Integer> costs=new HashMap<>();
        private final PriorityQueue<Node> open=new PriorityQueue<>(Comparator.<Node>comparingInt(n->n.g+n.h)
            .thenComparingInt(Node::h).thenComparingLong(n->n.pos.asLong()));
        private int expanded;
        private BuildNavigation.Result result;
        public GoalSearch(BuildNavigation.World world,BlockPos start,Collection<BlockPos> goals){
            this.world=world;this.start=start.immutable();
            var destinations=new HashSet<BlockPos>();goals.forEach(p->destinations.add(p.immutable()));
            if(destinations.isEmpty()||!world.clear(this.start)){result=new BuildNavigation.Result(List.of(),0);return;}
            // Search backwards from verified stations. A sealed nearby station
            // then exhausts its own small component instead of pulling a search
            // through the player's entire surrounding volume of open sky.
            if(destinations.contains(this.start)){destinations.clear();destinations.add(this.start);}
            for(var goal:destinations){
                if(!world.clear(goal))continue;
                open.add(new Node(goal,0,heuristic(goal)));costs.put(goal,0);parent.put(goal,null);
            }
            if(open.isEmpty())result=new BuildNavigation.Result(List.of(),0);
        }
        private int heuristic(BlockPos p){
            return p.distManhattan(start);
        }
        public int expanded(){return expanded;}
        /** Limits both expanded nodes and elapsed slice time; frontier survives between ticks. */
        public BuildNavigation.Result advance(int maxNodes,long deadlineNanos){
            if(maxNodes<0)throw new IllegalArgumentException("Negative search slice");
            if(result!=null)return result;
            int end=expanded+maxNodes;
            while(!open.isEmpty()&&expanded<end&&System.nanoTime()<deadlineNanos){
                var node=open.remove();var p=node.pos;
                if(node.g!=costs.getOrDefault(p,Integer.MAX_VALUE))continue;
                expanded++;
                if(p.equals(start)){
                    var path=new ArrayList<BlockPos>();for(var q=p;q!=null;q=parent.get(q))path.add(q);
                    return result=new BuildNavigation.Result(List.copyOf(path),expanded);
                }
                for(var direction:Direction.values()){
                    var q=p.relative(direction);int cost=node.g+1;
                    // q is a predecessor in the real start-to-goal route. The
                    // world API may have directional edges, so do not invert it.
                    if(cost>=costs.getOrDefault(q,Integer.MAX_VALUE)||!world.clear(q)||!world.edge(q,p))continue;
                    costs.put(q,cost);parent.put(q,p);open.add(new Node(q,cost,heuristic(q)));
                }
            }
            return open.isEmpty()?(result=new BuildNavigation.Result(List.of(),expanded)):null;
        }
    }
}
