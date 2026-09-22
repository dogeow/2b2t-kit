package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.Vec3;

import java.util.Locale;

/** 沿路点回家、飞回地狱门。状态从盾构引擎拆出。 */
final class BorerHome {
	private final DefaultTunnelBorerEngine engine;
	private RotationAim.Look movementLook;
	private final BorerHomeFlight flight;

	BorerHome(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
		this.flight = new BorerHomeFlight(engine);
	}

	void reset() { flight.close(); movementLook = null; engine.walkRoute.clear(); }
	void prepareFlight(Minecraft client) { flight.prepare(client); }

	void reapplyLook(Minecraft client) {
		if (movementLook != null && engine.currentTarget == null && !client.options.keyAttack.isDown()) {
			RotationAim.apply(client.player, movementLook);
		}
	}

	private void rememberLook(LocalPlayer player) {
		movementLook = new RotationAim.Look(player.getYRot(), player.getXRot());
	}

	static boolean canResumeWalking(boolean ownedFlight, double goalDeltaY, int landingDrop) {
		return ownedFlight && goalDeltaY <= .6 && landingDrop >= 0 && landingDrop <= 1;
	}

	/** 推进回家/回门；已接管返回 true。 */
	boolean handle(Minecraft client, LocalPlayer player) {
		if (engine.waitForMiningConfirmation(client)) return true;
		if (engine.trail.returnRouteHasGap(client, player)) {
			engine.stop(client, "前方回程路线缺失，已保留最初起点；请先接回已记录矿道");
			return true;
		}
		BlockPos dest = engine.trail.nextTowardHome(client, player);
		if ((dest == null || engine.trail.arrivedHome(client, player)) && engine.returningToPortal && engine.trail.portal() != null
			&& player.position().distanceToSqr(Vec3.atCenterOf(engine.trail.portal())) > 2.4 * 2.4) {
			dest = engine.trail.portal();
		}
		boolean arrived = engine.returningToPortal && engine.trail.portal() != null
			? player.position().distanceToSqr(Vec3.atCenterOf(engine.trail.portal())) <= 2.4 * 2.4
			: engine.trail.arrivedHome(client, player);
		if (dest == null || arrived) {
			engine.trail.save(client);
			if (engine.pendingLogoutReason != null) {
				String why = engine.pendingLogoutReason;
				engine.pendingLogoutReason = null;
				engine.stop(client, why + "，已到家后下线");
				engine.disconnectFromServer(client, why);
			} else {
				engine.stop(client, engine.returningToPortal ? "已飞回地狱门" : "已沿原路回到起点");
			}
			return true;
		}
		if (engine.returningToPortal || BorerItems.allMiningToolsWorn(player)) {
			engine.returningToPortal = true;
			return flyTowardPortal(client, player, dest);
		}
		// The temporary lift has reached the next floor. Leaving Flight on would
		// permanently bypass the ground pathfinder and drive straight into bends.
		if (canResumeWalking(engine.meteorFlightHeldByEngine, dest.getY() - player.getY(),
			BorerHazards.safeFallDepth(client, player.blockPosition()))) {
			engine.releaseMine(client);
			client.options.keyShift.setDown(false);
			engine.releaseMeteorFlightIfHeld(client);
			engine.walkRoute.clear();
			engine.status = "回程已越过台阶，落稳后继续沿通道走";
			return true;
		}
		// Recorded points can straddle a corner. Follow open body columns before
		// trying to mine a straight ray to the distant point.
		if (engine.walkRoute.walkHome(client, dest)) {
			engine.clearMiningTarget(client, "home-open-route");
			rememberLook(player);
			engine.status = "沿已通矿道返回，剩余 " + engine.trail.remainingTowardHome(client, player)
				+ " 路点 " + BorerText.block(dest);
			return true;
		}
		double dx = dest.getX() + 0.5 - player.getX();
		double dz = dest.getZ() + 0.5 - player.getZ();
		double dy = dest.getY() + 0.1 - player.getY();
		chooseHeading(dx, dz);
		if (engine.currentTarget != null && engine.shouldMine(client, engine.currentTarget)) {
			engine.status = "回家路上清挡 " + BorerText.block(engine.currentTarget)
				+ "，剩余 " + engine.trail.remainingTowardHome(client, player);
			return false;
		}
		BlockPos obstruction = engine.visibleObstructionToward(client, player, dest);
		if (obstruction != null && engine.shouldMine(client, obstruction) && engine.inMiningReach(player, obstruction)) {
			engine.setMiningTarget(client, player, obstruction, "home-obstruction");
			engine.status = "回家路上清挡 " + BorerText.block(obstruction)
				+ "，剩余 " + engine.trail.remainingTowardHome(client, player);
			return false;
		}
		engine.releaseMine(client);
		boolean moving = Math.hypot(dx, dz) > 0.35 || Math.abs(dy) > 0.6;
		if (dy > 1.1) engine.enableMeteorFlight(player);
		if (moving && engine.unsafeToWalk(client, player) && !BorerFlight.isFlying(player)) {
			if (alignWalk(client, player, dx, dz)) moving = true;
			else if (dy < -0.4 && engine.safeShortDropTowardLoot(client, player)) moving = true;
			else if (dy > 0.6 && engine.enableMeteorFlight(player)) moving = true;
			else if (engine.place.shouldBridgeDrops(player) && engine.place.placeWalkingSupport(client, player)
				&& !engine.unsafeToWalk(client, player)) {
				moving = true;
			} else moving = false;
		}
		engine.faceForward(player);
		rememberLook(player);
		client.options.keyUp.setDown(moving);
		client.options.keyJump.setDown(BorerFlight.isFlying(player) ? dy > 0.4 : player.onGround() && dy > 0.55);
		client.options.keyShift.setDown(BorerFlight.isFlying(player) && dy < -0.4);
		engine.attemptedForward = moving;
		int remain = engine.trail.remainingTowardHome(client, player);
		boolean connected = engine.trail.connectedToTrail(client, player);
		if (!connected && moving) {
			engine.status = String.format(Locale.ROOT, "巷道不通，朝最近路点挖回去 剩余 %d %s", remain, BorerText.block(dest));
		} else if (moving) {
			engine.status = String.format(Locale.ROOT, "沿原路返回 剩余 %d 路点 %s", remain, BorerText.block(dest));
		} else {
			engine.status = String.format(Locale.ROOT, "回家通道被挡，剩余 %d 路点 %s", remain, BorerText.block(dest));
		}
		engine.overlay(client, engine.status, moving ? 0x55FF55 : 0xFFFF55);
		return true;
	}

	/** 根据位移选主轴朝向。 */
	private void chooseHeading(double dx, double dz) {
		double ax = Math.abs(dx);
		double az = Math.abs(dz);
		Direction xDir = dx >= 0 ? Direction.EAST : Direction.WEST;
		Direction zDir = dz >= 0 ? Direction.SOUTH : Direction.NORTH;
		if (engine.forward.getAxis() == Direction.Axis.X && ax + 0.9 >= az) {
			if (ax > 0.15) engine.forward = xDir;
			return;
		}
		if (engine.forward.getAxis() == Direction.Axis.Z && az + 0.9 >= ax) {
			if (az > 0.15) engine.forward = zDir;
			return;
		}
		if (ax >= az && ax > 0.15) engine.forward = xDir;
		else if (az > 0.15) engine.forward = zDir;
	}

	/** 回家时优先走进已经挖开的 1×2，而不是对着墙的那一侧。 */
	private boolean alignWalk(Minecraft client, LocalPlayer player, double dx, double dz) {
		BlockPos feet = player.blockPosition();
		Direction alongX = dx >= 0 ? Direction.EAST : Direction.WEST;
		Direction alongZ = dz >= 0 ? Direction.SOUTH : Direction.NORTH;
		boolean xOpen = Math.abs(dx) > 0.15 && BorerHazards.canWalkOrFallInto(client, feet.relative(alongX));
		boolean zOpen = Math.abs(dz) > 0.15 && BorerHazards.canWalkOrFallInto(client, feet.relative(alongZ));
		if (xOpen && (!zOpen || Math.abs(dx) >= Math.abs(dz))) {
			engine.forward = alongX;
			return true;
		}
		if (zOpen) {
			engine.forward = alongZ;
			return true;
		}
		return false;
	}

	/** Follow the immediate collision-checked segment; lookahead must never steer around a hidden corner. */
	private boolean flyTowardPortal(Minecraft client, LocalPlayer player, BlockPos dest) {
		boolean handled = flight.tick(client, dest);
		if (engine.active) rememberLook(player);
		return handled;
	}
}
