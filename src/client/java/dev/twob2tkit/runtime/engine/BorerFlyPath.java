package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Bounded flight through open two-block body columns; never invent a diagonal through a corner. */
public final class BorerFlyPath {
	public interface World { boolean clear(BlockPos p); }
	public record Result(List<BlockPos> nodes, int expanded) {}
	private record Node(BlockPos pos, int cost, double priority) {}
	public static Result find(World world, BlockPos start, BlockPos target, int radius, int budget) {
		return find(world,start,target,radius,budget,1.25);
	}
	public static Result findExact(World world, BlockPos start, BlockPos target, int radius, int budget) {
		return find(world,start,target,radius,budget,0);
	}
	private static Result find(World world, BlockPos start, BlockPos target, int radius, int budget, double arrival) {
		if (!open(world, start)) return new Result(List.of(), 0);
		Map<BlockPos, Integer> costs = new HashMap<>();
		Map<BlockPos, BlockPos> parent = new HashMap<>();
		PriorityQueue<Node> queue = new PriorityQueue<>(Comparator.comparingDouble(Node::priority)
			.thenComparingInt(Node::cost).thenComparingLong(n -> n.pos.asLong()));
		queue.add(new Node(start, 0, distance(start, target))); costs.put(start, 0);
		int expanded = 0;
		while (!queue.isEmpty() && expanded < budget) {
			Node n = queue.remove();
			if (n.cost != costs.get(n.pos)) continue;
			expanded++;
			if (distance(n.pos, target) <= arrival) {
				LinkedList<BlockPos> path = new LinkedList<>();
				for (BlockPos p = n.pos; p != null; p = parent.get(p)) path.addFirst(p);
				return new Result(List.copyOf(path), expanded);
			}
			for (Direction direction : Direction.values()) {
				BlockPos next = n.pos.relative(direction);
				if (Math.abs(next.getX() - start.getX()) > radius || Math.abs(next.getY() - start.getY()) > radius
					|| Math.abs(next.getZ() - start.getZ()) > radius || !open(world, next)) continue;
				int cost = n.cost + 1;
				if (cost >= costs.getOrDefault(next, Integer.MAX_VALUE)) continue;
				costs.put(next, cost); parent.put(next, n.pos);
				queue.add(new Node(next, cost, cost + Math.max(0, distance(next, target) - arrival)));
			}
		}
		return new Result(List.of(), expanded);
	}
	public static boolean open(World world, BlockPos p) { return world.clear(p) && world.clear(p.above()); }
	private static double distance(BlockPos a, BlockPos b) { return Math.sqrt(a.distSqr(b)); }

	/** Leave room for fractional height error above a floor while still fitting a two-block tunnel. */
	public static Vec3 waypoint(BlockPos node) { return Vec3.atBottomCenterOf(node).add(0,.10,0); }

	/** One movement axis per tick. Meteor Velocity moves horizontally at speed*10, vertically at speed*5. */
	public record Input(float yaw, boolean forward, boolean up, boolean down, double speed, Vec3 delta) {}
	public static Input input(Vec3 position, Vec3 target, float yaw) {
		double dx = target.x - position.x, dy = target.y - position.y, dz = target.z - position.z;
		if (Math.abs(dx) > .07 || Math.abs(dz) > .07) {
			boolean x = Math.abs(dx) >= Math.abs(dz);
			double error = x ? dx : dz;
			double step = Math.min(.20, Math.abs(error) * .6);
			return new Input(x ? error > 0 ? -90 : 90 : error > 0 ? 0 : 180, true, false, false, step / 10,
				x ? new Vec3(Math.copySign(step, error), 0, 0) : new Vec3(0, 0, Math.copySign(step, error)));
		}
		if (Math.abs(dy) > .07) {
			double step = Math.min(.15, Math.abs(dy) * .6);
			return new Input(yaw, false, dy > 0, dy < 0, step / 5, new Vec3(0, Math.copySign(step, dy), 0));
		}
		return new Input(yaw, false, false, false, 0, Vec3.ZERO);
	}
}
