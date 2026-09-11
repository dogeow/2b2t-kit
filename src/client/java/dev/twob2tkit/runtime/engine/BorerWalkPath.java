package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import java.util.*;
import java.util.function.Predicate;

/** Bounded shortest path over already-open body columns. Mining remains the fallback, not a fake walk edge. */
final class BorerWalkPath {
	interface World { boolean clear(BlockPos p); boolean floor(BlockPos p); }
	record Result(List<BlockPos> nodes, int expanded) {}
	private record Node(BlockPos pos, double cost) {}
	static Result find(World w, BlockPos start, Predicate<BlockPos> goal, int radius, int budget, int maxDrop, boolean step) {
		if (!standable(w, start)) return new Result(List.of(), 0);
		Map<BlockPos, Double> costs = new HashMap<>(); Map<BlockPos, BlockPos> parent = new HashMap<>();
		PriorityQueue<Node> queue = new PriorityQueue<>(Comparator.comparingDouble(Node::cost)
			.thenComparingInt(n -> n.pos.getX()).thenComparingInt(n -> n.pos.getZ()).thenComparingInt(n -> n.pos.getY()));
		queue.add(new Node(start, 0)); costs.put(start, 0.0);
		int expanded = 0;
		while (!queue.isEmpty() && expanded < budget) {
			Node n = queue.remove();
			if (n.cost != costs.getOrDefault(n.pos, Double.POSITIVE_INFINITY)) continue;
			expanded++;
			if (goal.test(n.pos)) {
				LinkedList<BlockPos> path = new LinkedList<>();
				for (BlockPos p = n.pos; p != null; p = parent.get(p)) path.addFirst(p);
				return new Result(List.copyOf(path), expanded);
			}
			for (Direction d : Direction.Plane.HORIZONTAL) {
				BlockPos next = n.pos.relative(d);
				if (Math.abs(next.getX() - start.getX()) > radius || Math.abs(next.getZ() - start.getZ()) > radius) continue;
				if (!standable(w, next)) {
					if (step && w.clear(n.pos.above(2)) && standable(w, next.above())) next = next.above();
					else {
						int down = 0;
						while (down <= maxDrop && w.clear(next) && w.clear(next.above()) && !w.floor(next.below())) { next = next.below(); down++; }
						if (down > maxDrop || !standable(w, next)) continue;
					}
				}
				if (Math.abs(next.getY() - start.getY()) > Math.max(radius, maxDrop)) continue;
				double cost = n.cost + 1 + Math.abs(next.getY() - n.pos.getY()) * .4;
				if (cost >= costs.getOrDefault(next, Double.POSITIVE_INFINITY)) continue;
				costs.put(next, cost); parent.put(next, n.pos); queue.add(new Node(next, cost));
			}
		}
		return new Result(List.of(), expanded);
	}
	static boolean standable(World w, BlockPos p) { return w.clear(p) && w.clear(p.above()) && w.floor(p.below()); }
}
