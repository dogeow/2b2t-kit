package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.item.Items;
import net.minecraft.world.phys.AABB;

import net.minecraft.world.entity.Pose;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** 苦力怕、敌对扫描、举盾和向前挖时躲怪拐弯。 */
final class BorerMobs {
	private final DefaultTunnelBorerEngine engine;

	BorerMobs(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 苦力怕要炸时举盾；默认不围箱，能拐就拐。 */
	void handleCreeper(Minecraft client, LocalPlayer player, Creeper creeper) {
		engine.releaseMine(client);
		raiseShield(client, player);
		boolean swelling = creeper.isIgnited() || creeper.getSwelling(1.0F) > 0.15F || creeper.getSwellDir() > 0;
		double distance = player.distanceTo(creeper);
		boolean blast = swelling || distance < 5.0 || creeper.isPowered() && distance < 8.0;
		if (engine.host.borerSurroundOnCreeper() && blast && !engine.host.surroundActive()) {
			engine.host.startEmergencySurround(client);
			engine.status = "苦力怕靠近，已围箱";
		} else if (blast && retreatFrom(client, player, creeper)) {
			engine.status = swelling ? "苦力怕要炸，面朝它举盾后撤" : "苦力怕贴近，面朝它举盾后撤";
		} else if (tryTurnAround(client, player)) {
			engine.status = "躲开苦力怕，" + engine.status;
		} else {
			engine.status = swelling ? "苦力怕要炸，举盾躲开，不围墙" : "附近有苦力怕，举盾躲开，不围墙";
		}
		engine.overlay(client, engine.status, 0xFF5555);
	}

	/** 面朝威胁按后退拉开距离：盾牌只挡正面，转身跑反而挡不住爆炸。 */
	boolean retreatFrom(Minecraft client, LocalPlayer player, Entity threat) {
		double dx = threat.getX() - player.getX();
		double dz = threat.getZ() - player.getZ();
		if (dx * dx + dz * dz < 1.0E-4) return false;
		float toward = (float) Math.toDegrees(Math.atan2(dz, dx)) - 90.0F;
		for (float offset : new float[]{0.0F, -35.0F, 35.0F}) {
			float yaw = toward + offset;
			if (!safeRetreatYaw(client, player, yaw + 180.0F)) continue;
			player.setYRot(yaw);
			player.setYHeadRot(yaw);
			player.setXRot(12.0F);
			client.options.keyDown.setDown(true);
			client.options.keyUp.setDown(false);
			client.options.keyShift.setDown(false);
			engine.retreating = true;
			return true;
		}
		return false;
	}

	/** 该后退偏航是否安全。 */
	private boolean safeRetreatYaw(Minecraft client, LocalPlayer player, float yaw) {
		double rad = Math.toRadians(yaw);
		AABB moved = player.getBoundingBox().move(-Math.sin(rad) * 0.4, 0.0, Math.cos(rad) * 0.4);
		if (!client.level.noCollision(player, moved)) return false;
		BlockPos dest = BlockPos.containing(
			player.getX() - Math.sin(rad) * 1.1,
			player.getY(),
			player.getZ() + Math.cos(rad) * 1.1);
		if (BorerHazards.isLavaFluid(client, dest) || BorerHazards.isLavaFluid(client, dest.above())
			|| BorerHazards.isLavaFluid(client, dest.below()) || BorerHazards.isLavaFluid(client, dest.below(2))) {
			return false;
		}
		return BorerHazards.canWalkOrFallInto(client, dest);
	}

	/**
	 * 向前挖时用已加载实体（和 ESP 同一批）看通道里的怪物，往更空的一侧拐。
	 * @return 本 tick 已经改了朝向
	 */
	boolean tryTurnAround(Minecraft client, LocalPlayer player) {
		if (engine.mode != DefaultTunnelBorerEngine.Mode.FORWARD || engine.goingHome || player == null || client.level == null) {
			return false;
		}
		if (!engine.host.borerPauseOnMob() || engine.turnCooldown > 0) return false;
		double maxAlong = Math.max(engine.effectiveLookAhead() + 2, engine.host.borerMobRadius());
		List<Entity> hostiles = nearby(client, player, Math.max(16.0, maxAlong + 4.0));
		int ahead = along(player, hostiles, engine.forward, maxAlong);
		if (ahead == 0) return false;
		Direction cw = engine.forward.getClockWise();
		Direction ccw = engine.forward.getCounterClockWise();
		int cwScore = along(player, hostiles, cw, maxAlong);
		int ccwScore = along(player, hostiles, ccw, maxAlong);
		boolean clockwise;
		if (cwScore != ccwScore) clockwise = cwScore < ccwScore;
		else clockwise = !engine.lastTurnClockwise;
		int chosenScore = clockwise ? cwScore : ccwScore;
		if (chosenScore >= ahead) return false;
		Direction chosen = clockwise ? cw : ccw;
		Direction was = engine.forward;
		engine.commitTurn(client, player, chosen, clockwise);
		engine.status = "躲开怪物 拐弯 " + BorerText.direction(engine.forward);
		engine.overlay(client, engine.status, 0x55FFFF);
		engine.fileLog(client, "mob-turn from=" + was + " to=" + engine.forward
			+ " ahead=" + ahead + " cw=" + cwScore + " ccw=" + ccwScore
			+ " player=" + BorerText.precise(player));
		return true;
	}

	/** 半径内最近苦力怕；无则 null。 */
	Creeper findCreeper(Minecraft client, LocalPlayer player) {
		double radius = Math.max(6.0, engine.host.borerMobRadius());
		AABB box = player.getBoundingBox().inflate(radius);
		Creeper closest = null;
		double best = Double.MAX_VALUE;
		for (Entity entity : client.level.getEntities(player, box)) {
			if (entity instanceof Creeper creeper && creeper.isAlive()) {
				double distance = player.distanceTo(creeper);
				if (distance <= radius && distance < best) {
					closest = creeper;
					best = distance;
				}
			}
		}
		return closest;
	}

	/** 苦力怕是否即将爆炸需后撤。 */
	boolean creeperImminent(LocalPlayer player, Creeper creeper) {
		if (creeper == null || !creeper.isAlive()) return false;
		double distance = player.distanceTo(creeper);
		boolean swelling = creeper.isIgnited() || creeper.getSwelling(1.0F) > 0.15F || creeper.getSwellDir() > 0;
		return swelling || distance < 4.0 || creeper.isPowered() && distance < 6.0;
	}

	/** 已加载实体里、装甲过滤后仍危险的敌对。通道拐弯用这个。 */
	List<Entity> nearby(Minecraft client, LocalPlayer player, double radius) {
		return nearby(client, player, radius, false);
	}

	/** 半径里会打人的敌对，钻石套也算骷髅僵尸。停挖交给 KillAura 用这个。 */
	List<Entity> nearbyCombat(Minecraft client, LocalPlayer player, double radius) {
		return nearby(client, player, radius, true);
	}

	/** 半径内敌对；anyHostile 为真时放宽装甲过滤。 */
	private List<Entity> nearby(Minecraft client, LocalPlayer player, double radius, boolean anyHostile) {
		List<Entity> result = new ArrayList<>();
		if (client.level == null) return result;
		AABB box = player.getBoundingBox().inflate(radius, 12.0, radius);
		BorerThreats.Loadout loadout = BorerThreats.loadout(player);
		for (Entity entity : client.level.getEntities(player, box)) {
			if (!(entity instanceof Enemy) || !entity.isAlive()) continue;
			if (player.distanceTo(entity) > radius) continue;
			if (anyHostile) {
				if (!BorerThreats.shouldYieldWhenNearby(entity, loadout)) continue;
				if (!BorerCombatEngagePolicy.canEngageThreat(player.hasLineOfSight(entity))) continue;
			} else if (!BorerThreats.shouldAvoidInCorridor(entity, loadout)) {
				continue;
			}
			result.add(entity);
		}
		return result;
	}

	/** 沿当前朝向的侧向偏移相关量。 */
	int along(LocalPlayer player, List<Entity> hostiles, Direction dir, double maxAlong) {
		Direction right = dir.getClockWise();
		double half = engine.effectiveWidth() / 2.0 + 2.5;
		int count = 0;
		for (Entity entity : hostiles) {
			double dx = entity.getX() - player.getX();
			double dz = entity.getZ() - player.getZ();
			double along = dx * dir.getStepX() + dz * dir.getStepZ();
			if (along < 0.2 || along > maxAlong) continue;
			double side = dx * right.getStepX() + dz * right.getStepZ();
			if (Math.abs(side) > half) continue;
			if (Math.abs(entity.getY() - player.getY()) > engine.effectiveHeight() + 3.0) continue;
			count++;
		}
		return count;
	}

	/** 半径内最近敌对。 */
	Entity closest(Minecraft client, LocalPlayer player, double radius) {
		return closestOf(player, nearby(client, player, radius), radius);
	}

	/** 半径内最近需交战的敌对。 */
	Entity closestCombat(Minecraft client, LocalPlayer player, double radius) {
		return closestOf(player, nearbyCombat(client, player, radius), radius);
	}

	/** 半径内最近敌对。 */
	private static Entity closestOf(LocalPlayer player, List<Entity> hostiles, double radius) {
		Entity closest = null;
		double best = radius;
		for (Entity entity : hostiles) {
			double distance = player.distanceTo(entity);
			if (distance <= best) {
				closest = entity;
				best = distance;
			}
		}
		return closest;
	}

	/** 该位置附近是否有敌对。 */
	boolean nearPos(Minecraft client, LocalPlayer player, BlockPos pos, double radius) {
		if (client.level == null || pos == null) return false;
		return nearCached(nearby(client, player, radius + 4.0), pos, radius);
	}

	/** 用缓存判断附近是否有敌对。 */
	boolean nearCached(List<Entity> hostiles, BlockPos pos, double radius) {
		double range = radius * radius;
		double x = pos.getX() + 0.5;
		double y = pos.getY() + 0.5;
		double z = pos.getZ() + 0.5;
		for (Entity entity : hostiles) {
			if (entity.distanceToSqr(x, y, z) <= range) return true;
		}
		return false;
	}

	/** 举起副手盾。 */
	void raiseShield(Minecraft client, LocalPlayer player) {
		if (!engine.host.borerShieldOnMob()) return;
		boolean off = player.getOffhandItem().is(Items.SHIELD);
		boolean main = player.getMainHandItem().is(Items.SHIELD);
		if (!off && !main) return;
		client.options.keyUse.setDown(true);
		engine.holdingShield = true;
	}

	/** 放下副手盾。 */
	void lowerShield(Minecraft client) {
		if (!engine.holdingShield) return;
		client.options.keyUse.setDown(false);
		engine.holdingShield = false;
	}

	/** 交战移动。 */
	void releaseCombatMove(Minecraft client) {
		if (client.options == null) return;
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		engine.combatApproaching = false;
	}

	/**
	 * 遇怪停挖：开 KillAura + 飞行，默认飞到怪头顶再交给 KillAura；
	 * 头顶被挡才同高；苦力怕要炸则后撤举盾。
	 */
	String engageNearbyHostile(Minecraft client, LocalPlayer player, Entity threat) {
		if (!BorerCombatEngagePolicy.canEngageThreat(player.hasLineOfSight(threat))) {
			releaseCombatMove(client);
			return "墙后 " + threat.getName().getString() + "，无视";
		}
		engine.host.armAutoProtectIfEnabled(client);
		BorerFlight.ensureFlying(player, true);
		BorerItems.selectWeapon(client, player);

		if (threat instanceof Creeper creeper && BorerCombatEngagePolicy.shouldRetreatFromCreeper(creeper, player)) {
			raiseShield(client, player);
			if (retreatFrom(client, player, creeper)) return "苦力怕要炸，举盾后撤";
			return "苦力怕要炸，举盾";
		}

		double distance = player.distanceTo(threat);
		if (BorerCombatEngagePolicy.shouldRaiseShieldWhileClosing(threat, distance)) {
			raiseShield(client, player);
		}

		double targetFeetY = resolveCombatFeetY(client, player, threat);
		maintainCombatAltitude(client, player, targetFeetY);
		faceThreat(player, threat);

		if (BorerCombatEngagePolicy.shouldApproach(threat, distance)) {
			client.options.keyUp.setDown(true);
			engine.combatApproaching = true;
			String alt = altitudeNote(player, targetFeetY);
			return "开飞行贴近 " + threat.getName().getString() + alt;
		}

		client.options.keyUp.setDown(false);
		engine.combatApproaching = false;
		String alt = altitudeNote(player, targetFeetY);
		return "悬停攻击 " + threat.getName().getString() + alt;
	}

	/** 交战目标悬停脚底 Y。 */
	private double resolveCombatFeetY(Minecraft client, LocalPlayer player, Entity threat) {
		double preferred = BorerCombatEngagePolicy.hoverFeetY(
			threat.getY(), threat.getBbHeight(), BorerCombatEngagePolicy.HOVER_CLEARANCE);
		boolean blocked = !headroomClear(client, player, threat.getX(), preferred, threat.getZ());
		return BorerCombatEngagePolicy.resolveHoverFeetY(
			threat.getY(), threat.getBbHeight(), BorerCombatEngagePolicy.HOVER_CLEARANCE, blocked);
	}

	/** 目标高度头顶是否通。 */
	private boolean headroomClear(Minecraft client, LocalPlayer player, double x, double feetY, double z) {
		AABB box = player.getDimensions(Pose.STANDING).makeBoundingBox(x, feetY, z);
		return client.level.noCollision(player, box);
	}

	/** 维持交战飞行高度。 */
	private void maintainCombatAltitude(Minecraft client, LocalPlayer player, double targetFeetY) {
		if (!BorerFlight.isFlying(player)) {
			client.options.keyJump.setDown(false);
			client.options.keyShift.setDown(false);
			return;
		}
		double feetY = player.getY();
		if (BorerCombatEngagePolicy.shouldAscend(feetY, targetFeetY)) {
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
		} else if (BorerCombatEngagePolicy.shouldDescend(feetY, targetFeetY)) {
			client.options.keyJump.setDown(false);
			client.options.keyShift.setDown(true);
		} else {
			client.options.keyJump.setDown(false);
			client.options.keyShift.setDown(false);
		}
	}

	/** 把视角拧向威胁。 */
	private void faceThreat(LocalPlayer player, Entity threat) {
		Vec3 eye = player.getEyePosition();
		Vec3 target = threat.getBoundingBox().getCenter();
		double dx = target.x - eye.x;
		double dy = target.y - eye.y;
		double dz = target.z - eye.z;
		double horizontal = Math.sqrt(dx * dx + dz * dz);
		float yaw = (float) Math.toDegrees(Math.atan2(dz, dx)) - 90.0F;
		float pitch = (float) -Math.toDegrees(Math.atan2(dy, horizontal));
		player.setYRot(yaw);
		player.setYHeadRot(yaw);
		player.setXRot(pitch);
	}

	/** 高度差提示短文。 */
	private static String altitudeNote(LocalPlayer player, double targetFeetY) {
		double gap = targetFeetY - player.getY();
		if (Math.abs(gap) < 0.5) return "";
		if (gap > 0.5) return String.format(Locale.ROOT, "（拉高 %.1f 格）", gap);
		return String.format(Locale.ROOT, "（压低 %.1f 格）", -gap);
	}
}
