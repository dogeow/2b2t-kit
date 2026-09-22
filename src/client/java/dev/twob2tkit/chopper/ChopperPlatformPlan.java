package dev.twob2tkit.chopper;

import dev.twob2tkit.runtime.engine.BorerFlyPath;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Choose one open work position and fly to it, rather than building an entire column. */
final class ChopperPlatformPlan {
	interface World extends BorerFlyPath.World { boolean replaceable(BlockPos p); boolean floor(BlockPos p); }
	record Work(BlockPos feet, boolean platform, int reachable, List<BlockPos> route) {}
	private record Candidate(BlockPos feet,boolean platform,int count,double score) {}
	static Work choose(World w,Vec3 position,Collection<BlockPos> logs,double reach) { return choose(w,position,logs,reach,Set.of()); }
	static Work choose(World w,Vec3 position,Collection<BlockPos> logs,double reach,Set<BlockPos> excluded) {
		Set<BlockPos> seen=new HashSet<>();List<Candidate> candidates=new ArrayList<>();
		for(BlockPos log:logs)for(int x=-3;x<=3;x++)for(int z=-3;z<=3;z++)for(int y=-3;y<=1;y++){
			BlockPos feet=log.offset(x,y,z);
			if(excluded.contains(feet)||!seen.add(feet)||!BorerFlyPath.open(w,feet))continue;
			boolean platform=!w.floor(feet.below());if(platform&&!w.replaceable(feet.below()))continue;
			Vec3 eye=Vec3.atBottomCenterOf(feet).add(0,1.62,0);
			int count=0;for(BlockPos target:logs)if(distanceSquared(eye,target)<(reach-.25)*(reach-.25))count++;
			if(count==0)continue;
			double score=-count*100+position.distanceTo(Vec3.atBottomCenterOf(feet))+(platform?2:0);
			candidates.add(new Candidate(feet,platform,count,score));
		}
		candidates.sort(Comparator.comparingDouble(Candidate::score).thenComparingLong(v->v.feet.asLong()));
		int attempts=0;
		for(Candidate c:candidates){
			if(++attempts>16)break;
			var route=BorerFlyPath.findExact(w,BlockPos.containing(position),c.feet,24,12000);
			if(!route.nodes().isEmpty())return new Work(c.feet,c.platform,c.count,route.nodes());
		}
		return null;
	}
	static double distanceSquared(Vec3 eye,BlockPos b){
		double x=Math.max(b.getX()-eye.x,Math.max(0,eye.x-b.getX()-1));
		double y=Math.max(b.getY()-eye.y,Math.max(0,eye.y-b.getY()-1));
		double z=Math.max(b.getZ()-eye.z,Math.max(0,eye.z-b.getZ()-1));return x*x+y*y+z*z;
	}
}
