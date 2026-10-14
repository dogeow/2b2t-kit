package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import java.util.*;

/** Bounded natural-leaf connectivity joins branches separated by previously removed logs. */
final class ChopperCanopy {
	interface World {
		boolean wood(BlockPos p); boolean leaf(BlockPos p);
		default boolean stump(BlockPos p){return false;}
		default boolean loaded(BlockPos p){return true;}
	}
	record Crown(Set<BlockPos> logs,Set<BlockPos> witness,boolean complete) {}
	private enum Branch { SAME_TREE, OTHER_TREE, UNKNOWN }
	static Crown collect(World w, Collection<BlockPos> seed, int maxLogs) {
		if(seed.isEmpty())return new Crown(Set.of(),Set.of(),true);
		int minX=seed.stream().mapToInt(BlockPos::getX).min().orElseThrow()-8, maxX=seed.stream().mapToInt(BlockPos::getX).max().orElseThrow()+8;
		int minY=seed.stream().mapToInt(BlockPos::getY).min().orElseThrow()-8, maxY=seed.stream().mapToInt(BlockPos::getY).max().orElseThrow()+8;
		int minZ=seed.stream().mapToInt(BlockPos::getZ).min().orElseThrow()-8, maxZ=seed.stream().mapToInt(BlockPos::getZ).max().orElseThrow()+8;
		Map<BlockPos,Integer> depth=new HashMap<>();Set<BlockPos> logs=new HashSet<>(seed);ArrayDeque<BlockPos> queue=new ArrayDeque<>();
		Set<BlockPos> original=new HashSet<>(seed);Map<BlockPos,Branch> branchIdentity=new HashMap<>();
		for(BlockPos p:seed){depth.put(p,0);queue.add(p);}
		while(!queue.isEmpty()) {
			BlockPos p=queue.removeFirst();
			for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++){
				if(x==0&&y==0&&z==0)continue;
				BlockPos n=p.offset(x,y,z);
				if(n.getX()<minX||n.getX()>maxX||n.getY()<minY||n.getY()>maxY||n.getZ()<minZ||n.getZ()>maxZ)continue;
				if(!w.loaded(n))continue;
				boolean wood=w.wood(n);if(!wood&&!w.leaf(n))continue;
				if(wood&&!original.contains(n)){
					Branch known=branchIdentity.get(n);
					if(known==null)known=sameTreeBranch(w,n,original,branchIdentity,minX,maxX,minY,maxY,minZ,maxZ,maxLogs);
					if(known==Branch.UNKNOWN)return new Crown(Set.copyOf(logs),Set.copyOf(depth.keySet()),false);
					if(known==Branch.OTHER_TREE)continue;
				}
				int cost=wood?0:depth.get(p)+1;
				if(cost>4||cost>=depth.getOrDefault(n,Integer.MAX_VALUE))continue;
				depth.put(n,cost);queue.add(n);if(wood)logs.add(n);
				if(logs.size()>maxLogs||depth.size()>6000)return new Crown(Set.copyOf(logs),Set.copyOf(depth.keySet()),false);
			}
		}
		return new Crown(Set.copyOf(logs),Set.copyOf(depth.keySet()),true);
	}
	/** A disconnected branch may join through leaves; another rooted trunk may not. */
	private static Branch sameTreeBranch(World w,BlockPos start,Set<BlockPos> original,Map<BlockPos,Branch> identities,
		int minX,int maxX,int minY,int maxY,int minZ,int maxZ,int limit){
		Set<BlockPos> component=new HashSet<>();ArrayDeque<BlockPos> queue=new ArrayDeque<>();queue.add(start);
		Branch identity=Branch.SAME_TREE;boolean outsideCrown=false;
		while(!queue.isEmpty()&&identity==Branch.SAME_TREE){
			BlockPos p=queue.removeFirst();if(!component.add(p))continue;
			if(w.stump(p)&&!original.contains(p)){identity=Branch.OTHER_TREE;break;}
			if(component.size()>limit){identity=Branch.UNKNOWN;break;}
			if(p.getX()<minX||p.getX()>maxX||p.getY()<minY||p.getY()>maxY||p.getZ()<minZ||p.getZ()>maxZ)outsideCrown=true;
			for(int x=-1;x<=1&&identity==Branch.SAME_TREE;x++)for(int y=-1;y<=1&&identity==Branch.SAME_TREE;y++)for(int z=-1;z<=1&&identity==Branch.SAME_TREE;z++){
				if(x==0&&y==0&&z==0)continue;BlockPos n=p.offset(x,y,z);
				if(!w.loaded(n)){identity=Branch.UNKNOWN;break;}
				if(!w.wood(n)||component.contains(n))continue;
				// This read-only probe may follow a neighboring trunk down to
				// its soil. It never expands the accepted crown or mining box.
				if(n.getX()<minX-8||n.getX()>maxX+8||n.getY()<Math.max(-64,minY-32)||n.getY()>maxY+8||n.getZ()<minZ-8||n.getZ()>maxZ+8){identity=Branch.UNKNOWN;break;}
				queue.add(n);
			}
		}
		if(identity==Branch.SAME_TREE&&outsideCrown)identity=Branch.UNKNOWN;
		for(BlockPos p:component)identities.put(p.immutable(),identity);
		return identity;
	}
	/** Witness positions remain valid after leaves decay; never expand the job into a new area on completion. */
	static Set<BlockPos> remaining(World w,Collection<BlockPos> witness) {
		Set<BlockPos> found=new HashSet<>();for(BlockPos p:witness)if(w.wood(p))found.add(p.immutable());return found;
	}
}
