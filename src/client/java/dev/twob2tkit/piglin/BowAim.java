package dev.twob2tkit.piglin;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.Optional;

/**
 * 满弓箭的弹道解算。先按抛物线算抬头角，再逐 tick 模拟一遍确认箭真的会命中，
 * 而不是撞进地形里。目标在坑里或者隔着墙时直接判定打不到，免得对着地面空放二十箭。
 */
public final class BowAim {
	/** 满弓初速约 3 格/tick，之后每 tick 乘 0.99 阻力再扣 0.05 重力。 */
	private static final double SPEED = 3.0;
	private static final double GRAVITY = 0.05;
	private static final double DRAG = 0.99;
	private static final int MAX_TICKS = 100;
	/** 解析解没算阻力会略微打短，按这些角度依次上抬重试。 */
	private static final double[] NUDGES = {0.0, 1.0, 2.0, 3.0, 4.5, 6.0, 8.0, 11.0};
	/** 原版箭的命中判定会把实体碰撞箱放大一点。 */
	private static final double HIT_MARGIN = 0.3;

	/** aim 为 null 表示这一枪打不出去，problem 是给玩家看的原因。 */
	public record Shot(Vec3 aim, String problem) {
		boolean feasible() {
			return aim != null;
		}
	}

	private BowAim() {
	}

	/** 解出满弓瞄准点；打不到则 aim 为 null 并带原因。 */
	public static Shot solve(Minecraft client, LocalPlayer player, Entity target) {
		if (client.level == null) return new Shot(null, "没有世界");
		Vec3 eye = player.getEyePosition();
		Vec3 center = target.getBoundingBox().getCenter();
		// 提前量：按模拟飞行 tick 数把目标往移动方向推（BowAim 内已做弹道校验）。
		double flightTicks = Math.max(4.0, eye.distanceTo(center) / (SPEED * 0.92));
		Vec3 lead = target.getDeltaMovement().scale(flightTicks);
		AABB box = target.getBoundingBox().move(lead).inflate(HIT_MARGIN);
		Vec3 aimPoint = center.add(lead);

		double dx = aimPoint.x - eye.x;
		double dz = aimPoint.z - eye.z;
		double horizontal = Math.sqrt(dx * dx + dz * dz);
		double rise = aimPoint.y - eye.y;

		// 几乎在正上方/正下方，抛物线公式会除零，直接照直线打。
		if (horizontal < 0.5) {
			Vec3 direct = aimPoint.subtract(eye);
			if (direct.lengthSqr() < 1.0E-6) return new Shot(null, "距离太近");
			Vec3 dir = direct.normalize();
			return simulate(client, player, eye, dir, box)
				? new Shot(eye.add(dir.scale(4.0)), null)
				: new Shot(null, "被挡住了");
		}

		double speedSq = SPEED * SPEED;
		double discriminant = speedSq * speedSq
			- GRAVITY * (GRAVITY * horizontal * horizontal + 2.0 * rise * speedSq);
		if (discriminant < 0.0) return new Shot(null, "超出弓的射程");
		double base = Math.atan((speedSq - Math.sqrt(discriminant)) / (GRAVITY * horizontal));

		double unitX = dx / horizontal;
		double unitZ = dz / horizontal;
		for (double nudge : NUDGES) {
			double theta = base + Math.toRadians(nudge);
			if (theta > Math.toRadians(85.0)) break;
			double flat = Math.cos(theta);
			Vec3 dir = new Vec3(unitX * flat, Math.sin(theta), unitZ * flat);
			if (simulate(client, player, eye, dir, box)) return new Shot(eye.add(dir.scale(4.0)), null);
		}
		return new Shot(null, "地形挡着，射不中");
	}

	/** 按原版箭的顺序推进：先位移，再乘阻力，再扣重力。 */
	private static boolean simulate(Minecraft client, LocalPlayer player, Vec3 start, Vec3 dir, AABB box) {
		Vec3 pos = start;
		Vec3 velocity = dir.scale(SPEED);
		double floor = box.minY - 48.0;
		for (int tick = 0; tick < MAX_TICKS; tick++) {
			Vec3 next = pos.add(velocity);
			Optional<Vec3> onTarget = box.clip(pos, next);
			BlockHitResult blocked = client.level.clip(new ClipContext(
				pos, next, ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, player
			));
			if (blocked.getType() == HitResult.Type.BLOCK) {
				// 同一段里既撞墙又蹭到目标时，看谁在前面。
				return onTarget.isPresent()
					&& onTarget.get().distanceToSqr(pos) <= blocked.getLocation().distanceToSqr(pos);
			}
			if (onTarget.isPresent()) return true;
			pos = next;
			velocity = velocity.scale(DRAG);
			velocity = new Vec3(velocity.x, velocity.y - GRAVITY, velocity.z);
			if (pos.y < floor) return false;
		}
		return false;
	}
}
