package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Flight return owns a precise settings lease and follows collision-checked local waypoints. */
final class BorerHomeFlight {
	private final DefaultTunnelBorerEngine engine;
	private final BorerAreaFlightSession flight = new BorerAreaFlightSession();
	private List<BlockPos> path = List.of();

    List<BlockPos> mapNext() {
        return List.copyOf(path.subList(Math.min(index, path.size()), Math.min(index + 24, path.size())));
    }
	private BlockPos goal;
	private boolean escapingPocket, bypassingLiquid;
	private int index, idle;
	private final Obstructions obstructions = new Obstructions();
	private double best = Double.POSITIVE_INFINITY;
	BorerHomeFlight(DefaultTunnelBorerEngine engine) { this.engine = engine; }
	void prepare(Minecraft c) { flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/home-flight-speed.bak")); }
	boolean isFollowing() { return goal != null; }
	void close() {
		flight.closeKeepingFlight(); // A stop in midair must not drop the player or disable user-owned Flight.
		path = List.of(); goal = null; escapingPocket = bypassingLiquid = false; index = idle = 0; obstructions.reset(); best = Double.POSITIVE_INFINITY;
	}
	boolean beginPocketEscape(Minecraft c, boolean repeatedBedrockSkips) {
		var p = c.player;
		BlockPos start = p.blockPosition();
		int walls = 0;
		for (var direction : net.minecraft.core.Direction.Plane.HORIZONTAL) {
			BlockPos side = start.relative(direction);
			if (BorerHazards.isUnbreakable(c, side) || BorerHazards.isUnbreakable(c, side.above())) walls++;
		}
		if (!repeatedBedrockSkips && walls < 2) return false;
		Map<BlockPos, Boolean> cache = new HashMap<>();
		var route = BorerFlyPath.escapePocket(b -> cache.computeIfAbsent(b, v -> clear(c, v)),
			start, b -> landing(c, b));
		if (route.nodes().isEmpty()) {
			engine.stop(c, "基岩挡路，未找到通往上方的安全落脚点，已停挖");
			return true;
		}
		goal = route.nodes().getLast();
		path = route.nodes();
		escapingPocket = true;
		engine.releaseMine(c);
		engine.fileLog(c, "bedrock-pocket-escape path=" + path + " player=" + BorerText.precise(p));
		return true;
	}

	boolean beginLiquidBypass(Minecraft c, BlockPos ore, java.util.function.Predicate<BlockPos> dryApproach) {
		Map<BlockPos, Boolean> cache = new HashMap<>();
		var route = BorerFlyPath.liquidBypass(b -> cache.computeIfAbsent(b, v -> clear(c, v)),
			c.player.blockPosition(), ore, b -> landing(c, b) && dryApproach.test(b));
		if (route.nodes().isEmpty()) {
			engine.fileLog(c, "liquid-bypass-unavailable ore=" + ore + " expanded=" + route.expanded());
			return false;
		}
		path = route.nodes();
		goal = path.getLast();
		index = idle = 0; obstructions.reset();
		best = Double.POSITIVE_INFINITY;
		bypassingLiquid = true;
		engine.releaseMine(c);
		engine.fileLog(c, "liquid-bypass ore=" + ore + " landing=" + goal + " steps=" + path.size());
		return true;
	}

	boolean tickPocketEscape(Minecraft c) {
		return (escapingPocket || bypassingLiquid) && tick(c, goal);
	}

	private boolean landing(Minecraft c, BlockPos feet) {
		BlockPos floor = feet.below();
		if (!c.level.hasChunkAt(floor) || engine.miningConfirmation.pending(c.level, floor)) return false;
		var state = c.level.getBlockState(floor);
		return state.getFluidState().isEmpty() && !state.is(Blocks.MAGMA_BLOCK)
			&& !state.is(Blocks.CAMPFIRE) && !state.is(Blocks.SOUL_CAMPFIRE)
			&& state.isFaceSturdy(c.level, floor, net.minecraft.core.Direction.UP);
	}

	boolean tick(Minecraft c, BlockPos target) {
		var p = c.player;
		engine.releaseMine(c);
		c.options.keyShift.setDown(false); c.options.keySprint.setDown(false); p.setSprinting(false);
		try {
			prepare(c);
			String error = flight.acquire(p);
			if (error != null) return stopInFlight(c, "回程飞行：" + error);
			if (!target.equals(goal)) {
				goal = target.immutable(); path = List.of(); index = idle = 0; obstructions.reset(); best = Double.POSITIVE_INFINITY;
			}
			if (path.isEmpty()) {
				Map<BlockPos, Boolean> cache = new HashMap<>();
				BorerFlyPath.World world = b -> cache.computeIfAbsent(b, v -> clear(c, v));
				var route = bypassingLiquid ? BorerFlyPath.findExact(world, p.blockPosition(), target, BorerFlyPath.BYPASS_RADIUS, BorerFlyPath.BYPASS_BUDGET) : escapingPocket
					? BorerFlyPath.findExact(world, p.blockPosition(), target, 8, 512)
					: BorerFlyPath.find(world, p.blockPosition(), target, 12, 2400);
				if (route.nodes().isEmpty()) {
					flight.hover(); engine.fileLog(c, "home-flight-blocked goal=" + target + " expanded=" + route.expanded() + " player=" + BorerText.precise(p));
					return stopInFlight(c, "回程下一段没有可通行空间 " + BorerText.block(target) + "，已停下并保留路线");
				}
				path = route.nodes(); index = 0; idle = 0; best = Double.POSITIVE_INFINITY;
				engine.fileLog(c, "home-flight-path goal=" + target + " steps=" + path.size() + " expanded=" + route.expanded() + " player=" + BorerText.precise(p));
			}
			while (index < path.size() && reached(p.position(), BorerFlyPath.waypoint(path.get(index)))) {
				index++; idle = 0; best = Double.POSITIVE_INFINITY;
			}
			if (index == path.size()) {
				if (bypassingLiquid) {
					if (!landing(c, target)) return stopInFlight(c, "绕行落脚点已变化，已停挖");
					flight.close();
					close();
					engine.ores.resetBlockedRouteSkips();
				} else if (escapingPocket) {
					if (!landing(c, target)) return stopInFlight(c, "基岩脱困落脚点已变化，已停挖");
					flight.close();
					engine.stop(c, "已退出基岩口袋，到达上方矿道，挖矿已停止");
				} else {
					path = List.of();
					flight.hover();
				}
				return true;
			}
			BlockPos node = path.get(index);
			Vec3 destination = BorerFlyPath.waypoint(node);
			double distance = p.position().distanceTo(destination);
			if (distance < best - .025) { best = distance; idle = 0; } else idle++;
			var input = clearanceInput(p.position(), destination, p.getYRot(),
				delta -> clearStep(c, delta));
			boolean safe = input != null;
			if (!safe || idle >= 80) {
				flight.hover();
				engine.fileLog(c, "home-flight-replan reason=" + (!safe ? "body-blocked" : "no-progress") + " goal=" + target + " node=" + node + " idle=" + idle + " player=" + BorerText.precise(p));
				if (obstructions.repeated(p.position())) return stopInFlight(c, (bypassingLiquid ? "绕行在 " : "回程在 ") + BorerText.block(node) + " 受阻，已停下并保留路线");
				path = List.of(); return true;
			}
			RotationAim.apply(p, input.yaw(), 0);
			flight.speed(input.speed());
			c.options.keyUp.setDown(input.forward()); c.options.keyJump.setDown(input.up()); c.options.keyShift.setDown(input.down());
			engine.attemptedForward = !escapingPocket && !bypassingLiquid && input.forward();
			engine.status = bypassingLiquid ? "沿干燥通道绕行 · " + BorerText.block(target) : escapingPocket ? "沿空隙退出基岩口袋 · " + BorerText.block(target) : "沿通道飞回 · 剩" + engine.trail.remainingTowardHome(c, p) + "路点 · " + BorerText.block(target);
			engine.overlay(c, engine.status, 0x55FF55);
			return true;
		} catch (IllegalStateException failure) { return stopInFlight(c, "回程飞行已停止：" + failure.getMessage()); }
	}
	/** A small height correction in the current column can clear a lip before crossing it. */
	static BorerFlyPath.Input clearanceInput(Vec3 position, Vec3 destination, float yaw,
			java.util.function.Predicate<Vec3> clearStep) {
		var input = BorerFlyPath.input(position, destination, yaw);
		if (clearStep.test(input.delta())) return input;
		double dy = destination.y - position.y;
		if (!input.forward() || Math.abs(dy) <= .07 || Math.abs(dy) > .25) return null;
		var vertical = BorerFlyPath.input(position, position.add(0, dy, 0), yaw);
		return clearStep.test(vertical.delta()) ? vertical : null;
	}

	private boolean clearStep(Minecraft c, Vec3 delta) {
		var p = c.player;
		var swept = p.getBoundingBox().expandTowards(delta).deflate(.0001);
		if (!c.level.noCollision(p, swept)) return false;
		for (BlockPos b : BlockPos.betweenClosed(BlockPos.containing(swept.minX, swept.minY, swept.minZ),
				BlockPos.containing(swept.maxX, swept.maxY, swept.maxZ))) {
			if (!clear(c, b)) return false;
		}
		return true;
	}

	static final class Obstructions {
		private Vec3 last;
		boolean repeated(Vec3 current) {
			if (last != null && last.distanceToSqr(current) <= 4) return true;
			last = current;
			return false;
		}
		void reset() { last = null; }
	}

	private boolean stopInFlight(Minecraft client, String reason) {
		// An ordinary home return can also be hovering over a drop on an engine-owned lift.
		engine.meteorFlightHeldByEngine = false;
		engine.stop(client, reason);
		return true;
	}
	static boolean reached(Vec3 p, Vec3 target) {
		return Math.abs(p.x - target.x) <= .07 && Math.abs(p.y - target.y) <= .07 && Math.abs(p.z - target.z) <= .07;
	}
	private boolean clear(Minecraft c, BlockPos p) {
		if (p.getY() < c.level.getMinY() || p.getY() >= c.level.getMaxY() || !c.level.hasChunkAt(p)
			|| engine.miningConfirmation.pending(c.level, p)) return false;
		var state = c.level.getBlockState(p);
		return state.getFluidState().isEmpty() && state.getCollisionShape(c.level, p).isEmpty()
			&& !state.is(Blocks.FIRE) && !state.is(Blocks.SOUL_FIRE) && !state.is(Blocks.COBWEB)
			&& !state.is(Blocks.POWDER_SNOW) && !state.is(Blocks.SWEET_BERRY_BUSH);
	}
}
