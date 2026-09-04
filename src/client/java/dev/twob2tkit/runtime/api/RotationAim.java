package dev.twob2tkit.runtime.api;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.util.Mth;
import net.minecraft.world.phys.Vec3;

/**
 * 核心与功能包共用的视角原语。只准依赖 net.minecraft：这个包在引擎的
 * ChildFirstEngineLoader 里走 parent-first，两边必须是同一个 Class。
 */
public final class RotationAim {
	private RotationAim() {
	}

	/** 一次瞄准的完整朝向。 */
	public record Look(float yaw, float pitch) {
	}

	/** 从眼睛看向目标的朝向。 */
	public static Look lookAt(Vec3 eye, Vec3 target) {
		Vec3 delta = target.subtract(eye);
		double horiz = Math.hypot(delta.x, delta.z);
		float yaw = (float)Math.toDegrees(Math.atan2(delta.z, delta.x)) - 90.0F;
		float pitch = (float)Math.toDegrees(-Math.atan2(delta.y, Math.max(0.001, horiz)));
		return new Look(yaw, pitch);
	}

	/** 从眼睛看向目标的朝向。 */
	public static Look lookAt(LocalPlayer player, Vec3 target) {
		return lookAt(player.getEyePosition(), target);
	}

	/** 水平朝向：巡航这类只看 yaw 的场合。 */
	public static float yawToward(double dx, double dz) {
		return (float)Math.toDegrees(Math.atan2(dz, dx)) - 90.0F;
	}

	/**
	 * 把朝向写进玩家，连同 yRotO/xRotO。渲染准星用旧值插值，漏写的话画面
	 * 会慢一格（见被收编前的 ChopperKeys.lookAt 注释）。
	 */
	public static void apply(LocalPlayer player, float yaw, float pitch) {
		player.setYRot(yaw);
		player.setXRot(pitch);
		player.setYHeadRot(yaw);
		player.setYBodyRot(yaw);
		player.yRotO = yaw;
		player.xRotO = pitch;
	}

	/** 用 {@link Look} 写入玩家朝向（含插值旧值）。 */
	public static void apply(LocalPlayer player, Look look) {
		apply(player, look.yaw(), look.pitch());
	}

	/**
	 * 朝 target 走一步，最大不超过 maxStepPerTick 度。大误差全速收敛，
	 * 小误差按 0.35 倍比例减速，0.5 度内直接对准。yaw/pitch 通用。
	 */
	public static float step(float current, float target, float maxStepPerTick) {
		float delta = Mth.wrapDegrees(target - current);
		if (Math.abs(delta) < 0.5F) return target;
		float step = Math.min(Math.max(maxStepPerTick, 1.0F), Math.max(1.0F, Math.abs(delta) * 0.35F));
		return current + Math.signum(delta) * Math.min(step, Math.abs(delta));
	}
}
