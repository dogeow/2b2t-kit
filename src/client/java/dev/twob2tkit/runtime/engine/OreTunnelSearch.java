package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import java.util.*;

/** Incremental A* over loaded terrain. Costs include the rock that each step must clear. */
final class OreTunnelSearch {
	interface World {
		int cell(BlockPos pos); // 0 open, 1 mineable, -1 forbidden or unloaded
		boolean floor(BlockPos pos);
		default boolean safeFeet(BlockPos pos) { return true; }
	}
	record Visit(BlockPos pos, int cost, double rank) {}
	private final BlockPos goal;
	private final List<BlockPos> stances = new ArrayList<>(8);
	private boolean initialized;
	private int expanded;
	int expanded() { return expanded; }
	private final Map<BlockPos,Integer> costs = new HashMap<>();
	private final Map<BlockPos,BlockPos> parent = new HashMap<>();
	private final PriorityQueue<Visit> open = new PriorityQueue<>(Comparator.comparingDouble(Visit::rank)
		.thenComparingInt(Visit::cost).thenComparingLong(v -> v.pos.asLong()));
	List<BlockPos> path = List.of();
	boolean done;

	OreTunnelSearch(BlockPos start, BlockPos goal) {
		this.goal = goal.immutable();
		costs.put(start, 0);
		open.add(new Visit(start, 0, 0));
	}

	private int estimate(BlockPos p) {
		int best = Integer.MAX_VALUE;
		for (BlockPos stance : stances) {
			int horizontal = Math.abs(p.getX()-stance.getX()) + Math.abs(p.getZ()-stance.getZ());
			int vertical = p.getY()-stance.getY();
			best = Math.min(best, vertical < 0 ? horizontal-vertical : Math.max(horizontal,vertical));
		}
		return best;
	}

	static List<BlockPos> clearance(BlockPos from, BlockPos to) {
		if (to.getY() < from.getY() && (to.getX()!=from.getX() || to.getZ()!=from.getZ()))
			return List.of(to.above(2), to.above(), to);
		return List.of(to.above(), to);
	}

	private void offer(World w, Visit here, BlockPos next, boolean downInPlace) {
		if (!w.safeFeet(next) || (next.getY() < here.pos.getY() && !downInPlace && !w.safeFeet(next.above()))) return;
		int cost = here.cost + 1;
		if (cost >= costs.getOrDefault(next,Integer.MAX_VALUE)) return;
		for (BlockPos b : clearance(here.pos,next)) {
			if (b.equals(goal) || b.equals(goal.below())) return;
			int cell = w.cell(b);
			if (cell < 0 || downInPlace && cell != 0) return;
			cost += 3 * cell;
		}
		if (cost >= costs.getOrDefault(next,Integer.MAX_VALUE)) return;
		costs.put(next,cost);
		parent.put(next,here.pos);
		open.add(new Visit(next,cost,cost+8.0*estimate(next)));
	}

	void advance(World world, int budget, long deadline) {
		if (!initialized) {
			initialized = true;
			for (Direction direction : Direction.Plane.HORIZONTAL) {
				BlockPos side = goal.relative(direction);
				for (BlockPos feet : List.of(side, side.below())) {
					if (world.floor(feet.below()) && world.cell(feet)>=0 && world.cell(feet.above())>=0)
						stances.add(feet);
				}
			}
			if (stances.isEmpty()) { done=true; return; }
		}
		while (!done && budget-- > 0 && System.nanoTime()<deadline) {
			Visit v=open.poll();
			if (v==null) { done=true; return; }
			if (costs.get(v.pos)!=v.cost) continue;
			expanded++;
			if (stances.contains(v.pos) && world.floor(v.pos.below())) {
				var nodes=new ArrayDeque<BlockPos>();
				for (var p=v.pos;p!=null;p=parent.get(p)) nodes.addFirst(p);
				// An earlier clearance cannot also be the floor used by the final stance.
				BlockPos support = v.pos.below();
				BlockPos previous = nodes.getFirst();
				boolean preserved = true;
				for (BlockPos next : nodes) {
					if (!next.equals(previous) && clearance(previous, next).contains(support)) {
						preserved = false;
						break;
					}
					previous = next;
				}
				if (preserved) { path=List.copyOf(nodes); done=true; return; }
			}
			for (Direction d:Direction.Plane.HORIZONTAL) {
				BlockPos beside=v.pos.relative(d);
				offer(world,v,beside,false);
				if (world.floor(beside.below(2))) offer(world,v,beside.below(),false);
			}
			offer(world,v,v.pos.above(),false);
			offer(world,v,v.pos.below(),true);
		}
	}
}
