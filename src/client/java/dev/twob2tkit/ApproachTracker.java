package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/** 走近目标：进度跟踪、卡住判定、直走按键。 */
public final class ApproachTracker {
	private Object targetKey;
	private int ticks;
	private double startDist = -1.0;

	/** 清空当前目标与计时。 */
	public void reset() {
		targetKey = null;
		ticks = 0;
		startDist = -1.0;
	}

	/**
	 * 跟踪同一目标是否卡住。
	 * @return true 表示已卡住，应跳过当前目标
	 */
	public boolean track(Object key, double dist, int stuckTicks) {
		if (key == null) {
			reset();
			return false;
		}
		if (!key.equals(targetKey)) {
			targetKey = key;
			ticks = 0;
			startDist = dist;
			return false;
		}
		ticks++;
		if (dist < startDist - 0.35) {
			startDist = dist;
			ticks = 0;
			return false;
		}
		return ticks >= stuckTicks && dist > startDist - 0.4;
	}

	/** 当前目标已连续跟踪的 tick 数。 */
	public int ticks() {
		return ticks;
	}

	/** 朝水平目标按前进键，必要时跳一格台阶或卡住时跳。 */
	public static void walkToward(Minecraft client, LocalPlayer player, Vec3 dest, int stuckTicks, ApproachTracker tracker) {
		double horiz = Math.hypot(dest.x - player.getX(), dest.z - player.getZ());
		client.options.keyUp.setDown(horiz > 0.2);
		client.options.keyDown.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		double dy = dest.y - player.getY();
		boolean stepUp = dy > 0.45 && dy <= 1.25;
		boolean jumpStuck = tracker.ticks > 8 && horiz > 0.5 && player.onGround();
		client.options.keyJump.setDown((stepUp && player.onGround()) || jumpStuck);
	}
}
