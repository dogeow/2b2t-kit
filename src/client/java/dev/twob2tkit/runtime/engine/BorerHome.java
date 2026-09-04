package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.Locale;

/** 沿路点回家、飞回地狱门。状态从盾构引擎拆出。 */
final class BorerHome {
	private final DefaultTunnelBorerEngine engine;

	BorerHome(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 推进回家/回门；已接管返回 true。 */
	boolean handle(Minecraft client, LocalPlayer player) {
		BlockPos dest = engine.trail.nextTowardHome(client, player);
		if (dest == null && engine.returningToPortal && engine.trail.portal() != null
			&& player.position().distanceToSqr(Vec3.atCenterOf(engine.trail.portal())) > 2.4 * 2.4) {
			dest = engine.trail.portal();
		}
		if (dest == null || engine.trail.arrivedHome(client, player)) {
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

	/** 开飞行沿巷道路点回去。不挖方块。头顶岩浆则先去绿色天井再升高。 */
	private boolean flyTowardPortal(Minecraft client, LocalPlayer player, BlockPos dest) {
		Vec3 position = player.position();
		if (engine.lastForwardPosition != null && position.distanceToSqr(engine.lastForwardPosition) < 0.0004) {
			engine.noMovementTicks++;
		} else {
			engine.noMovementTicks = 0;
		}
		engine.lastForwardPosition = position;
		engine.releaseMine(client);
		engine.enableMeteorFlight(player);
		client.options.keyAttack.setDown(false);

		engine.shaftScanTicks++;
		if (engine.shaftScanTicks >= 15 || engine.escapeShaft == null) {
			engine.shaftScanTicks = 0;
			engine.escapeShaft = BorerHazards.nearestSafeAscent(client, player, 12, 16);
		}

		boolean lavaAbove = BorerHazards.isLavaFluid(client, player.blockPosition().above(2))
			|| BorerHazards.isLavaFluid(client, player.blockPosition().above(3));
		boolean lavaBelow = BorerHazards.isLavaFluid(client, player.blockPosition())
			|| BorerHazards.isLavaFluid(client, player.blockPosition().below());
		BlockPos flyTo = dest;
		String extra = "";
		if (lavaAbove && engine.escapeShaft != null) {
			double shaftDist = Math.hypot(
				engine.escapeShaft.getX() + 0.5 - player.getX(),
				engine.escapeShaft.getZ() + 0.5 - player.getZ());
			if (shaftDist > 1.4) {
				flyTo = engine.escapeShaft;
				extra = " 先去无岩浆天井";
			} else {
				flyTo = engine.escapeShaft.above(8);
				extra = " 天井升高躲开岩浆";
			}
		}

		BlockPos look = flyTo == dest ? engine.trail.lookTowardHome(client, player, 5) : flyTo;
		if (look == null) look = flyTo;
		engine.lookAt(player, new Vec3(look.getX() + 0.5, player.getEyeY(), look.getZ() + 0.5));
		double dx = flyTo.getX() + 0.5 - player.getX();
		double dz = flyTo.getZ() + 0.5 - player.getZ();
		double dy = flyTo.getY() + 0.2 - player.getY();
		boolean lavaAhead = lavaInLookDirection(client, player);
		boolean blocked = engine.noMovementTicks >= 10;
		boolean moving = Math.hypot(dx, dz) > 0.4 && !lavaAhead;
		if (lavaAbove && engine.escapeShaft != null) moving = Math.hypot(dx, dz) > 1.4 && !lavaAhead;
		client.options.keyUp.setDown(moving);
		client.options.keyJump.setDown(lavaBelow || lavaAbove || dy > 0.5 || blocked && !lavaAhead);
		client.options.keyShift.setDown(BorerFlight.isFlying(player) && dy < -0.45 && !lavaBelow && !lavaAhead && !blocked);
		engine.attemptedForward = moving;
		int remain = Math.max(1, engine.trail.remainingTowardHome(client, player));
		String portalBit = engine.trail.portal() == null ? "" : " 门" + BorerText.compass(player.blockPosition(), engine.trail.portal());
		String shaftBit = lavaAbove
			? (engine.escapeShaft == null ? " 沿巷道躲开岩浆" : " 天井" + BorerText.compass(player.blockPosition(), engine.escapeShaft))
			: " 沿挖过的巷道飞回";
		engine.status = String.format(Locale.ROOT, "飞回家 剩%d路点%s%s%s", remain, extra, portalBit, shaftBit);
		engine.overlay(client, engine.status, 0x55FF55);
		logPortalReturnIfNeeded(client, player, dest, flyTo, extra, lavaAbove, lavaBelow, lavaAhead, blocked, moving, dx, dy, dz);
		return true;
	}

	/** 回家经门/巷道时节流写入诊断日志。 */
	private void logPortalReturnIfNeeded(
		Minecraft client,
		LocalPlayer player,
		BlockPos dest,
		BlockPos flyTo,
		String extra,
		boolean lavaAbove,
		boolean lavaBelow,
		boolean lavaAhead,
		boolean blocked,
		boolean moving,
		double dx,
		double dy,
		double dz
	) {
		engine.portalReturnLogTicks++;
		boolean destChanged = engine.lastLoggedHomeDest == null || !engine.lastLoggedHomeDest.equals(dest);
		boolean movingChanged = engine.lastLoggedHomeMoving != moving;
		boolean stalled = !moving && (engine.noMovementTicks == 10 || engine.noMovementTicks == 40
			|| engine.noMovementTicks > 0 && engine.noMovementTicks % 40 == 0);
		if (engine.portalReturnLogTicks < 20 && !destChanged && !movingChanged && !stalled) return;
		engine.portalReturnLogTicks = 0;
		engine.lastLoggedHomeDest = dest.immutable();
		engine.lastLoggedHomeMoving = moving;
		double horiz = Math.hypot(dx, dz);
		Vec3 velocity = player.getDeltaMovement();
		String look = lookHazardDetail(client, player);
		String whyStopped = moving ? "-"
			: lavaAhead ? "look-hazard=" + look
			: horiz <= 0.4 ? "already-at-flyTo-horiz"
			: "unknown";
		engine.fileLog(client, "portal-return remain=" + engine.trail.size()
			+ " dest=" + BorerText.block(dest)
			+ " flyTo=" + BorerText.block(flyTo)
			+ " extra=" + (extra.isBlank() ? "-" : extra.trim())
			+ " horiz=" + String.format(Locale.ROOT, "%.2f", horiz)
			+ " dy=" + String.format(Locale.ROOT, "%.2f", dy)
			+ " moving=" + moving
			+ " blocked=" + blocked
			+ " stallTicks=" + engine.noMovementTicks
			+ " why=" + whyStopped
			+ " look=" + look
			+ " lavaAbove=" + lavaAbove
			+ " lavaBelow=" + lavaBelow
			+ " flying=" + BorerFlight.isFlying(player)
			+ " meteor=" + BorerFlight.meteorFlightActive()
			+ " mayfly=" + player.getAbilities().mayfly
			+ " abilitiesFlying=" + player.getAbilities().flying
			+ " heldFlight=" + engine.meteorFlightHeldByEngine
			+ " flyCooldown=" + engine.flyToggleCooldown
			+ " keys=up:" + client.options.keyUp.isDown()
			+ ",jump:" + client.options.keyJump.isDown()
			+ ",shift:" + client.options.keyShift.isDown()
			+ " velocity=" + String.format(Locale.ROOT, "%.3f,%.3f,%.3f", velocity.x, velocity.y, velocity.z)
			+ " yaw=" + String.format(Locale.ROOT, "%.1f", player.getYRot())
			+ " pitch=" + String.format(Locale.ROOT, "%.1f", player.getXRot())
			+ " portal=" + (engine.trail.portal() == null ? "-" : BorerText.block(engine.trail.portal()))
			+ " shaft=" + (engine.escapeShaft == null ? "-" : BorerText.block(engine.escapeShaft))
			+ " tail=" + engine.trail.describeTail(4)
			+ " player=" + BorerText.precise(player));
	}

	/** 视线方向危险详情。 */
	private String lookHazardDetail(Minecraft client, LocalPlayer player) {
		Vec3 look = player.getViewVector(1.0F);
		for (int step = 1; step <= 3; step++) {
			BlockPos pos = BlockPos.containing(
				player.getX() + look.x * step,
				player.getY() + 0.4 + look.y * step * 0.3,
				player.getZ() + look.z * step
			);
			if (BorerHazards.isLavaFluid(client, pos)) return "lava@" + BorerText.block(pos);
			if (BorerHazards.isLavaFluid(client, pos.above())) return "lava@" + BorerText.block(pos.above());
			if (BorerHazards.isLavaFluid(client, pos.below())) return "lava@" + BorerText.block(pos.below());
		}
		AABB ahead = player.getBoundingBox().move(look.x * 0.7, 0.1, look.z * 0.7);
		if (!client.level.noCollision(player, ahead)) {
			BlockPos hit = BlockPos.containing(
				player.getX() + look.x * 0.7,
				player.getY() + 0.5,
				player.getZ() + look.z * 0.7
			);
			return "collision@" + engine.blockAt(client, hit);
		}
		return "clear";
	}

	/** 视线前方是否有岩浆。 */
	private boolean lavaInLookDirection(Minecraft client, LocalPlayer player) {
		Vec3 look = player.getViewVector(1.0F);
		for (int step = 1; step <= 3; step++) {
			BlockPos pos = BlockPos.containing(
				player.getX() + look.x * step,
				player.getY() + 0.4 + look.y * step * 0.3,
				player.getZ() + look.z * step
			);
			if (BorerHazards.isLavaFluid(client, pos)
				|| BorerHazards.isLavaFluid(client, pos.above())
				|| BorerHazards.isLavaFluid(client, pos.below())) {
				return true;
			}
		}
		return false;
	}
}
