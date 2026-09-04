package dev.twob2tkit.chopper;

import com.mojang.blaze3d.platform.InputConstants;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerFlight;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.Vec3;

/** 挖树共用的朝向、松键和提示。 */
public final class ChopperKeys {
	private static float smoothYaw = Float.NaN;
	private static float smoothPitch = Float.NaN;

	private ChopperKeys() {
	}

	/** 瞬间对准目标点，并记下当前平滑朝向。 */
	public static void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
		smoothYaw = player.getYRot();
		smoothPitch = player.getXRot();
	}

	/** 每拍最多转 {@code maxStepPerTick} 度，朝向目标点。 */
	public static void smoothLookAt(LocalPlayer player, Vec3 target, float maxStepPerTick) {
		RotationAim.Look want = RotationAim.lookAt(player, target);
		if (Float.isNaN(smoothYaw)) {
			smoothYaw = player.getYRot();
			smoothPitch = player.getXRot();
		}
		smoothYaw = RotationAim.step(smoothYaw, want.yaw(), maxStepPerTick);
		smoothPitch = RotationAim.step(smoothPitch, want.pitch(), maxStepPerTick);
		RotationAim.apply(player, smoothYaw, smoothPitch);
	}

	/** Meteor 改朝向后，把本模块记下的平滑朝向写回去。 */
	public static void reapplySmoothLook(LocalPlayer player) {
		if (!Float.isNaN(smoothYaw)) RotationAim.apply(player, smoothYaw, smoothPitch);
	}

	/** 清平滑朝向缓存（换树或停止时）。 */
	public static void resetSmoothLook() {
		smoothYaw = Float.NaN;
		smoothPitch = Float.NaN;
	}

	/** 瞬间对准方块中心。 */
	public static void lookAt(LocalPlayer player, BlockPos pos) {
		lookAt(player, Vec3.atCenterOf(pos));
	}

	/** 松开左键并停止破坏进度。 */
	public static void releaseMine(Minecraft client) {
		if (client.options != null) client.options.keyAttack.setDown(false);
		if (client.gameMode != null) client.gameMode.stopDestroyBlock();
	}

	/** 松开前进/后退/跳/潜行。 */
	public static void releaseWalk(Minecraft client) {
		if (client.options == null) return;
		client.options.keyUp.setDown(false);
		client.options.keyDown.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
	}

	/** 挖与走都停住。 */
	public static void holdStill(Minecraft client) {
		releaseMine(client);
		releaseWalk(client);
	}

	/** 按拾取策略走向目标（自行算水平/垂直距离）。 */
	public static void walkToward(Minecraft client, LocalPlayer player, Vec3 dest) {
		double horiz = Math.hypot(dest.x - player.getX(), dest.z - player.getZ());
		double dy = dest.y - player.getY();
		double dist = player.position().distanceTo(dest);
		walkToward(client, player, dest, horiz, dy, dist);
	}

	/**
	 * 按拾取策略写朝向与移动键。
	 * <p>
	 * 副作用：改玩家朝向与 {@code keyUp}/{@code keyJump}/{@code keyShift}。
	 */
	public static void walkToward(Minecraft client, LocalPlayer player, Vec3 dest, double horiz, double dy, double dist) {
		lookAt(player, dest);
		boolean flying = BorerFlight.isFlying(player);
		client.options.keyUp.setDown(ChopperLootPolicy.shouldWalkForward(horiz, dy, dist, flying));
		client.options.keyDown.setDown(false);
		client.options.keyJump.setDown(ChopperLootPolicy.shouldJump(flying, player.onGround(), dy));
		client.options.keyShift.setDown(flying && dy < -0.35 && horiz > 0.35);
	}

	/** 屏幕字幕提示（带 [挖树] 前缀）。 */
	public static void overlay(Minecraft client, String text, int color) {
		client.gui.setOverlayMessage(Component.literal("[挖树] " + text).withColor(color), false);
	}

	/** 聊天系统消息（带 [挖树] 前缀）。 */
	public static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[挖树] " + text));
	}

	/** 模拟点一次攻击键（秒破树叶用）。 */
	public static void clickAttack(Minecraft client) {
		KeyMapping.click(InputConstants.getKey(client.options.keyAttack.saveString()));
	}
}
