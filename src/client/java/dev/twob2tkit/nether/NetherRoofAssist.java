package dev.twob2tkit.nether;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;
import dev.twob2tkit.KitClient;

/** 下界基岩顶：飞到高度后用末影珍珠穿缝上顶。 */
public final class NetherRoofAssist {
	private static final int PEARL_COOLDOWN = 24;
	private static final int MAX_THROWS = 8;

	private boolean active;
	private boolean startCruiseAfter;
	private double pendingX;
	private double pendingZ;
	private double pendingY;
	private int throwCooldown;
	private int throwsUsed;
	private String status = "";

	/** 是否正在珍珠上顶。 */
	public boolean isActive() {
		return active;
	}

	/** 最近状态文案。 */
	public String status() {
		return status;
	}

	/** 开始上基岩顶；可选上顶后巡航。 */
	public void start(Minecraft client, boolean thenCruise, double x, double z, double y) {
		if (client.player == null || client.level == null) return;
		if (!client.level.dimension().equals(Level.NETHER)) {
			message(client, "先到下界。穿基岩顶请用末影珍珠，点界面里的「珍珠上顶」");
			return;
		}
		if (onRoof(client.player)) {
			message(client, "已经在基岩顶上了（Y " + String.format("%.1f", client.player.getY()) + "）");
			if (thenCruise) KitClient.controller().start(client, x, z, y);
			return;
		}
		if (countPearls(client.player) <= 0) {
			message(client, "背包没有末影珍珠。穿基岩顶要用珍珠，点界面里的「珍珠上顶」");
			return;
		}
		active = true;
		startCruiseAfter = thenCruise;
		pendingX = x;
		pendingZ = z;
		pendingY = y;
		throwCooldown = 0;
		throwsUsed = 0;
		status = "准备用珍珠上基岩顶";
		message(client, "开始上基岩顶：先飞到约 Y120，再对着基岩角或缝丢珍珠。End 可停");
	}

	/** 停止并松手。 */
	public void stop(Minecraft client, String reason) {
		if (!active) return;
		active = false;
		startCruiseAfter = false;
		release(client);
		status = "已停止：" + reason;
		message(client, "上基岩顶已停止：" + reason);
	}

	/** 飞到高度后对缝丢珍珠。 */
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		if (client.screen != null) {
			release(client);
			status = "先关掉界面";
			return;
		}

		LocalPlayer player = client.player;
		if (onRoof(player)) {
			release(client);
			active = false;
			status = "已经到顶";
			message(client, "已到下界基岩顶。可以开始巡航，建议高度 129");
			if (startCruiseAfter && KitClient.controller() != null) {
				KitClient.controller().start(client, pendingX, pendingZ, pendingY);
			}
			return;
		}

		if (throwsUsed >= MAX_THROWS) {
			stop(client, "珍珠丢了 " + MAX_THROWS + " 次还没上去。服里可能禁穿基岩，或改用手丢：站到 Y120+，对着基岩块的角疾跑丢珍珠");
			return;
		}

		if (player.getY() < 118.0) {
			releaseWalk(client);
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			player.setXRot(-35.0F);
			status = "先飞到基岩层附近（现在 Y " + String.format("%.0f", player.getY()) + "）";
			overlay(client, status, 0x55FFFF);
			return;
		}

		if (throwCooldown > 0) {
			throwCooldown--;
			releaseWalk(client);
			status = "等珍珠冷却";
			return;
		}

		if (player.getCooldowns().isOnCooldown(player.getMainHandItem()) && player.getMainHandItem().is(Items.ENDER_PEARL)) {
			status = "珍珠冷却中";
			return;
		}

		InteractionHand hand = selectPearl(client);
		if (hand == null) {
			stop(client, "没有末影珍珠了");
			return;
		}

		Vec3 aim = aimPoint(client, player);
		lookAt(player, aim);
		client.options.keySprint.setDown(true);
		client.options.keyJump.setDown(false);
		client.options.keyUp.setDown(false);
		InteractionResult result = client.gameMode.useItem(player, hand);
		player.swing(hand);
		client.options.keySprint.setDown(false);
		throwsUsed++;
		throwCooldown = PEARL_COOLDOWN;
		status = result.consumesAction()
			? "已丢第 " + throwsUsed + " 颗珍珠"
			: "这次没丢出去，再试";
		overlay(client, status, 0x55FFFF);
	}

	/** 上顶时保持瞄准。 */
	public void reapplyLook(Minecraft client) {
		if (!active || client.player == null || client.level == null || client.screen != null) return;
		if (client.player.getY() < 118.0) {
			client.player.setXRot(-35.0F);
			return;
		}
		lookAt(client.player, aimPoint(client, client.player));
	}

	/** 是否已在基岩顶上。 */
	public static boolean onRoof(LocalPlayer player) {
		return player.getY() >= 127.6;
	}

	/** 是否在下界维度。 */
	public static boolean inNether(Minecraft client) {
		return client.level != null && client.level.dimension().equals(Level.NETHER);
	}

	/** 到顶后建议巡航高度。 */
	public static double roofCruiseY() {
		return 129.0;
	}

	/** 基岩顶下面巡航高度：人能飞、头顶还能挖下界岩。 */
	public static double underRoofCruiseY() {
		return 120.0;
	}

	/** 本次珍珠瞄准点。 */
	private Vec3 aimPoint(Minecraft client, LocalPlayer player) {
		BlockPos hole = findHole(client, player);
		if (hole != null) return Vec3.atCenterOf(hole).add(0.0, 0.6, 0.0);
		BlockPos roof = findRoofBedrock(client, player);
		if (roof != null) {
			return new Vec3(roof.getX() + 0.08, roof.getY() + 0.98, roof.getZ() + 0.08);
		}
		return player.getEyePosition().add(0.0, 8.0, 0.0);
	}

	/** 找基岩缝/洞。 */
	private BlockPos findHole(Minecraft client, LocalPlayer player) {
		BlockPos origin = player.blockPosition();
		BlockPos best = null;
		double bestDist = Double.MAX_VALUE;
		for (int dx = -6; dx <= 6; dx++) {
			for (int dz = -6; dz <= 6; dz++) {
				for (int y = 124; y <= 127; y++) {
					BlockPos pos = new BlockPos(origin.getX() + dx, y, origin.getZ() + dz);
					if (!client.level.hasChunkAt(pos)) continue;
					if (client.level.getBlockState(pos).is(Blocks.BEDROCK)) continue;
					if (!client.level.getBlockState(pos).getCollisionShape(client.level, pos).isEmpty()) continue;
					boolean openAbove = true;
					for (int ay = y + 1; ay <= 128; ay++) {
						BlockPos above = new BlockPos(pos.getX(), ay, pos.getZ());
						if (client.level.getBlockState(above).is(Blocks.BEDROCK)) {
							openAbove = false;
							break;
						}
					}
					if (!openAbove) continue;
					double dist = player.position().distanceToSqr(Vec3.atCenterOf(pos));
					if (dist < bestDist) {
						bestDist = dist;
						best = pos.immutable();
					}
				}
			}
		}
		return best;
	}

	/** 找头顶基岩块。 */
	private BlockPos findRoofBedrock(Minecraft client, LocalPlayer player) {
		BlockPos origin = player.blockPosition();
		BlockPos best = null;
		double bestDist = Double.MAX_VALUE;
		for (int dx = -4; dx <= 4; dx++) {
			for (int dz = -4; dz <= 4; dz++) {
				BlockPos pos = new BlockPos(origin.getX() + dx, 127, origin.getZ() + dz);
				if (!client.level.hasChunkAt(pos) || !client.level.getBlockState(pos).is(Blocks.BEDROCK)) continue;
				double dist = player.position().distanceToSqr(Vec3.atCenterOf(pos));
				if (dist < bestDist) {
					bestDist = dist;
					best = pos.immutable();
				}
			}
		}
		return best;
	}

	/** 主手或背包换上末影珍珠。 */
	private InteractionHand selectPearl(Minecraft client) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().is(Items.ENDER_PEARL)) return InteractionHand.MAIN_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!inventory.getItem(slot).is(Items.ENDER_PEARL)) continue;
			inventory.setSelectedSlot(slot);
			return InteractionHand.MAIN_HAND;
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(Items.ENDER_PEARL)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			if (player.getMainHandItem().is(Items.ENDER_PEARL)) return InteractionHand.MAIN_HAND;
		}
		if (player.getOffhandItem().is(Items.ENDER_PEARL)) return InteractionHand.OFF_HAND;
		return null;
	}

	/** 背包珍珠数量。 */
	private static int countPearls(LocalPlayer player) {
		int total = 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (stack.is(Items.ENDER_PEARL)) total += stack.getCount();
		}
		if (player.getOffhandItem().is(Items.ENDER_PEARL)) total += player.getOffhandItem().getCount();
		return total;
	}

	/** 瞬间对准目标点。 */
	private static void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/** 松开移动键。 */
	private static void releaseWalk(Minecraft client) {
		client.options.keyUp.setDown(false);
		client.options.keySprint.setDown(false);
	}

	/** 松开移动与使用相关键。 */
	private static void release(Minecraft client) {
		if (client.options == null) return;
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		client.options.keySprint.setDown(false);
	}

	/** 叠字幕提示。 */
	private static void overlay(Minecraft client, String text, int color) {
		client.gui.setOverlayMessage(Component.literal("[下界顶] " + text).withColor(color), false);
	}

	/** 发系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[下界顶] " + text));
	}
}
