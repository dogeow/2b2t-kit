package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import java.util.*;

/** Bounded natural-leaf connectivity joins branches separated by previously removed logs. */
final class ChopperCanopy {
	interface World { boolean wood(BlockPos p); boolean leaf(BlockPos p); }
	record Crown(Set<BlockPos> logs,Set<BlockPos> witness,boolean complete) {}
	static Crown collect(World w, Collection<BlockPos> seed, int maxLogs) {
		if(seed.isEmpty())return new Crown(Set.of(),Set.of(),true);
		int minX=seed.stream().mapToInt(BlockPos::getX).min().orElseThrow()-8, maxX=seed.stream().mapToInt(BlockPos::getX).max().orElseThrow()+8;
		int minY=seed.stream().mapToInt(BlockPos::getY).min().orElseThrow()-8, maxY=seed.stream().mapToInt(BlockPos::getY).max().orElseThrow()+8;
		int minZ=seed.stream().mapToInt(BlockPos::getZ).min().orElseThrow()-8, maxZ=seed.stream().mapToInt(BlockPos::getZ).max().orElseThrow()+8;
		Map<BlockPos,Integer> depth=new HashMap<>();Set<BlockPos> logs=new HashSet<>(seed);ArrayDeque<BlockPos> queue=new ArrayDeque<>();
		for(BlockPos p:seed){depth.put(p,0);queue.add(p);}
		while(!queue.isEmpty()) {
			BlockPos p=queue.removeFirst();
			for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++){
				if(x==0&&y==0&&z==0)continue;
				BlockPos n=p.offset(x,y,z);
				if(n.getX()<minX||n.getX()>maxX||n.getY()<minY||n.getY()>maxY||n.getZ()<minZ||n.getZ()>maxZ)continue;
				boolean wood=w.wood(n);if(!wood&&!w.leaf(n))continue;
				int cost=wood?0:depth.get(p)+1;
				if(cost>4||cost>=depth.getOrDefault(n,Integer.MAX_VALUE))continue;
				depth.put(n,cost);queue.add(n);if(wood)logs.add(n);
				if(logs.size()>maxLogs||depth.size()>6000)return new Crown(Set.copyOf(logs),Set.copyOf(depth.keySet()),false);
			}
		}
		return new Crown(Set.copyOf(logs),Set.copyOf(depth.keySet()),true);
	}
	/** Witness positions remain valid after leaves decay; never expand the job into a new area on completion. */
	static Set<BlockPos> remaining(World w,Collection<BlockPos> witness) {
		Set<BlockPos> found=new HashSet<>();for(BlockPos p:witness)if(w.wood(p))found.add(p.immutable());return found;
	}
}
