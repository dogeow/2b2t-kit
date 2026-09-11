package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Follow cardinal waypoints without cutting wall corners or sprinting past a turn. ORE/loot only. */
final class BorerWalkRoute {
	private final DefaultTunnelBorerEngine engine;
	private List<BlockPos> path = List.of();
	private BlockPos target;
	private boolean loot;
	private int index, stall;
	private long nextPlan;
	private double best = Double.POSITIVE_INFINITY;
	private long progress;
	BorerWalkRoute(DefaultTunnelBorerEngine engine) { this.engine = engine; }
	void clear() { path = List.of(); target = null; index = stall = 0; nextPlan = 0; best = Double.POSITIVE_INFINITY; }
	long progress() { return progress; }
	boolean walk(Minecraft c, Vec3 goal, boolean pickup) {
		var p = c.player;
		if (BorerFlight.isFlying(p)) return false;
		BlockPos block = BlockPos.containing(goal);
		if (!block.equals(target) || loot != pickup) { clear(); target = block; loot = pickup; }
		long now = c.level.getGameTime();
		if (path.isEmpty()) {
			if (!p.onGround() || now < nextPlan) return false;
			nextPlan = now + 10;
			var w = world(c);
			var route = BorerWalkPath.find(w, p.blockPosition(), foot -> pickup
				? BorerLootPolicy.inVanillaPickupRange(goal.x - foot.getX() - .5, goal.y - foot.getY(), goal.z - foot.getZ() - .5)
				: Math.abs(foot.getX() - block.getX()) + Math.abs(foot.getZ() - block.getZ()) <= 1
					&& block.getY() - foot.getY() >= -1 && block.getY() - foot.getY() <= 2,
				12, 640, Math.min(12, BorerFallPolicy.maxSafeFallBlocks(BorerFlight.meteorNoFallActive())), BorerFlight.canStepOneBlock(p));
			if (route.nodes().size() <= 1) return false;
			path = route.nodes(); index = 0; stall = 0; best = Double.POSITIVE_INFINITY;
			engine.fileLog(c, "ore-walk-route kind=" + (pickup ? "loot" : "ore") + " goal=" + block + " steps=" + path.size() + " expanded=" + route.expanded());
		}
		engine.releaseMine(c);
		c.options.keyDown.setDown(false); c.options.keyLeft.setDown(false); c.options.keyRight.setDown(false);
		c.options.keyShift.setDown(false); c.options.keyJump.setDown(false); c.options.keySprint.setDown(false); p.setSprinting(false);
		if (!p.onGround()) { c.options.keyUp.setDown(false); return true; }
		while (index < path.size()) {
			BlockPos node = path.get(index);
			if (!BorerCenterPolicy.reachedWaypoint(node.getX() + .5 - p.getX(), node.getY() - p.getY(), node.getZ() + .5 - p.getZ())) break;
			if (index > 0) progress++;
			index++; stall = 0; best = Double.POSITIVE_INFINITY;
		}
		if (index >= path.size()) { path = List.of(); c.options.keyUp.setDown(false); return false; }
		BlockPos node = path.get(index);
		if (!BorerWalkPath.standable(world(c), node)) { invalidate(c, "waypoint-changed"); return false; }
		double dx = node.getX() + .5 - p.getX(), dz = node.getZ() + .5 - p.getZ();
		double distance = Math.hypot(dx, dz);
		if (distance < best - .04) { best = distance; stall = 0; } else stall++;
		if (stall >= 30) { invalidate(c, "no-waypoint-progress"); return false; }
		// Validate the swept body, not a single ray through the middle of a doorway.
		var input = BorerCenterPolicy.walkInput(dx, dz);
		double dy = node.getY() > p.getY() + .5 && BorerFlight.canStepOneBlock(p) ? 1 : 0;
		if (!c.level.noCollision(p, p.getBoundingBox().move(input.probeX(), dy, input.probeZ()))) {
			invalidate(c, "body-blocked"); return false;
		}
		RotationAim.apply(p, input.yaw(), 0);
		engine.rememberOreMove(p);
		c.options.keyUp.setDown(input.forward()); engine.attemptedForward = input.forward();
		engine.overlay(c, "沿已通路线" + (pickup ? "拾取矿物" : "接近矿点") + " · " + index + "/" + (path.size() - 1), 0x55FFFF);
		return true;
	}
	private void invalidate(Minecraft c, String why) {
		engine.fileLog(c, "ore-walk-replan reason=" + why + " goal=" + target + " waypoint=" + index);
		path = List.of(); c.options.keyUp.setDown(false); nextPlan = c.level.getGameTime() + 10;
	}
	private BorerWalkPath.World world(Minecraft c) {
		Map<BlockPos, Boolean> clear = new HashMap<>(), floor = new HashMap<>();
		return new BorerWalkPath.World() {
			public boolean clear(BlockPos b) { return clear.computeIfAbsent(b, p -> c.level.hasChunkAt(p)
				&& p.getY() >= c.level.getMinY() && p.getY() < c.level.getMaxY()
				&& c.level.getBlockState(p).getFluidState().isEmpty()
				&& !c.level.getBlockState(p).is(Blocks.FIRE) && !c.level.getBlockState(p).is(Blocks.SOUL_FIRE)
				&& !c.level.getBlockState(p).is(Blocks.POWDER_SNOW) && !c.level.getBlockState(p).is(Blocks.COBWEB)
				&& !c.level.getBlockState(p).is(Blocks.SWEET_BERRY_BUSH)
				&& c.level.getBlockState(p).getCollisionShape(c.level, p).isEmpty()); }
			public boolean floor(BlockPos b) { return floor.computeIfAbsent(b, p -> c.level.hasChunkAt(p)
				&& !BorerHazards.isMagma(c, p) && c.level.getBlockState(p).getFluidState().isEmpty()
				&& c.level.getBlockState(p).isFaceSturdy(c.level, p, net.minecraft.core.Direction.UP)); }
		};
	}
}
