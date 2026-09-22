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
	private BlockPos goal;
	private int index, idle, replans;
	private double best = Double.POSITIVE_INFINITY;
	BorerHomeFlight(DefaultTunnelBorerEngine engine) { this.engine = engine; }
	void prepare(Minecraft c) { flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/home-flight-speed.bak")); }
	void close() {
		flight.closeKeepingFlight(); // A stop in midair must not drop the player or disable user-owned Flight.
		path = List.of(); goal = null; index = idle = replans = 0; best = Double.POSITIVE_INFINITY;
	}
	boolean tick(Minecraft c, BlockPos target) {
		var p = c.player;
		engine.releaseMine(c);
		c.options.keyShift.setDown(false); c.options.keySprint.setDown(false); p.setSprinting(false);
		try {
			prepare(c);
			String error = flight.acquire(p);
			if (error != null) { engine.stop(c, "回程飞行：" + error); return true; }
			if (!target.equals(goal)) {
				goal = target.immutable(); path = List.of(); index = idle = replans = 0; best = Double.POSITIVE_INFINITY;
			}
			if (path.isEmpty()) {
				Map<BlockPos, Boolean> cache = new HashMap<>();
				var route = BorerFlyPath.find(b -> cache.computeIfAbsent(b, v -> clear(c, v)), p.blockPosition(), target, 12, 2400);
				if (route.nodes().isEmpty()) {
					flight.hover(); engine.fileLog(c, "home-flight-blocked goal=" + target + " expanded=" + route.expanded() + " player=" + BorerText.precise(p));
					engine.stop(c, "回程下一段没有可通行空间 " + BorerText.block(target) + "，已停下并保留路线"); return true;
				}
				path = route.nodes(); index = 0; idle = 0; best = Double.POSITIVE_INFINITY;
				engine.fileLog(c, "home-flight-path goal=" + target + " steps=" + path.size() + " expanded=" + route.expanded() + " player=" + BorerText.precise(p));
			}
			while (index < path.size() && reached(p.position(), BorerFlyPath.waypoint(path.get(index)))) {
				index++; idle = 0; best = Double.POSITIVE_INFINITY;
			}
			if (index == path.size()) { path = List.of(); flight.hover(); return true; }
			BlockPos node = path.get(index);
			Vec3 destination = BorerFlyPath.waypoint(node);
			double distance = p.position().distanceTo(destination);
			if (distance < best - .025) { best = distance; idle = 0; } else idle++;
			var input = BorerFlyPath.input(p.position(), destination, p.getYRot());
			// The whole swept body must fit, including off-centre initial positions and server corrections.
			var swept = p.getBoundingBox().expandTowards(input.delta()).deflate(.0001);
			boolean safe = c.level.noCollision(p, swept);
			if (safe) for (BlockPos b : BlockPos.betweenClosed(BlockPos.containing(swept.minX, swept.minY, swept.minZ),
				BlockPos.containing(swept.maxX, swept.maxY, swept.maxZ))) {
				if (!clear(c, b)) { safe = false; break; }
			}
			if (!safe || idle >= 80) {
				flight.hover();
				engine.fileLog(c, "home-flight-replan reason=" + (!safe ? "body-blocked" : "no-progress") + " goal=" + target + " node=" + node + " idle=" + idle + " player=" + BorerText.precise(p));
				if (++replans >= 2) { engine.stop(c, "回程在 " + BorerText.block(node) + " 受阻，已停下并保留路线"); return true; }
				path = List.of(); return true;
			}
			RotationAim.apply(p, input.yaw(), 0);
			flight.speed(input.speed());
			c.options.keyUp.setDown(input.forward()); c.options.keyJump.setDown(input.up()); c.options.keyShift.setDown(input.down());
			engine.attemptedForward = input.forward();
			engine.status = "沿通道飞回 · 剩" + engine.trail.remainingTowardHome(c, p) + "路点 · " + BorerText.block(target);
			engine.overlay(c, engine.status, 0x55FF55);
			return true;
		} catch (IllegalStateException failure) { engine.stop(c, "回程飞行已停止：" + failure.getMessage()); return true; }
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
