package dev.twob2tkit.fisher;

import dev.twob2tkit.mixin.FishingHookBiteAccess;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerFlight;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.projectile.FishingHook;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ChestMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.HopperMenu;
import net.minecraft.world.inventory.ShulkerBoxMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.FishingRodItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.CopperChestBlock;
import net.minecraft.world.level.block.EnderChestBlock;
import net.minecraft.world.level.block.ShulkerBoxBlock;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitKeys;

/** 定点定视角钓鱼；满包后找附近箱子存完再钓。钩子也可交给 Meteor auto-fish。 */
public final class AutoFisher {
	private static final int CAST_COOLDOWN = 12;
	private static final int CATCH_WAIT = 6;
	private static final int DUMP_COOLDOWN = 3;
	private static final int OPEN_WAIT = 8;
	private static final double SPOT_TOLERANCE = 0.45;

	private final KitConfig config;
	private boolean active;
	private String status = "";
	private double spotX;
	private double spotY;
	private double spotZ;
	private float spotYaw;
	private float spotPitch;
	private BlockPos chestPos;
	private Phase phase = Phase.FISH;
	private int cooldown;
	private int openWait;
	private int caughtWait;
	private boolean sawBite;
	private int dumpStreak;
	private int caughtCount;
	private long sessionStartMs;

	private enum Phase {
		FISH, APPROACH_CHEST, OPEN_CHEST, DUMP, RETURN
	}

	/** 按配置构造钓鱼控制器。 */
	public AutoFisher(KitConfig config) {
		this.config = config;
	}

	/** 是否正在自动钓鱼。 */
	public boolean isActive() {
		return active;
	}

	/** 是否在走向/打开/倒箱阶段（非抛竿）。 */
	public boolean isDepositing() {
		return active && phase != Phase.FISH;
	}

	/** 最近状态文案。 */
	public String status() {
		return status;
	}

	/** 锁定脚底与视角，找附近箱子并开始。 */
	public void start(Minecraft client) {
		if (client.player == null || client.level == null) return;
		LocalPlayer player = client.player;
		active = true;
		phase = Phase.FISH;
		cooldown = 0;
		openWait = 0;
		caughtWait = 0;
		sawBite = false;
		dumpStreak = 0;
		caughtCount = 0;
		sessionStartMs = System.currentTimeMillis();
		spotX = player.getX();
		spotY = player.getY();
		spotZ = player.getZ();
		spotYaw = player.getYRot();
		spotPitch = player.getXRot();
		chestPos = findNearbyChest(client, player);
		status = "开始钓鱼";
		String chest = chestPos == null ? "附近没看到箱子，满了会停" : "箱子 " + chestPos.getX() + " " + chestPos.getY() + " " + chestPos.getZ();
		message(client, "已锁定脚底和视角。" + chest + "。再按 "
			+ KitKeys.boundLabel(KitKeys.TOGGLE_FISHER) + " 或 End 停止");
		if (config.fisherLeaveHookToMeteor && meteorAutoFishActive()) {
			message(client, "钩子交给 Meteor auto-fish，这边只锁视角、满包存箱");
		}
	}

	/** 停止钓鱼、松键、关箱并说明原因。 */
	public void stop(Minecraft client, String reason) {
		if (!active) return;
		active = false;
		phase = Phase.FISH;
		releaseKeys(client);
		if (client.screen instanceof AbstractContainerScreen<?>) {
			client.player.closeContainer();
		}
		status = "已停止：" + reason;
		message(client, "自动钓鱼已停止：" + reason + (caughtCount > 0 ? "（本次收了 " + caughtCount + " 次）" : ""));
	}

	/** 主循环：满包存箱、抛收钩或交给 Meteor。 */
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		LocalPlayer player = client.player;
		if (cooldown > 0) cooldown--;

		if (phase == Phase.DUMP || phase == Phase.OPEN_CHEST) {
			handleStash(client, player);
			return;
		}
		if (client.screen != null) {
			releaseKeys(client);
			status = "先关掉界面再钓";
			return;
		}

		if (phase == Phase.APPROACH_CHEST) {
			approachChest(client, player);
			return;
		}
		if (phase == Phase.RETURN) {
			returnToSpot(client, player);
			return;
		}

		releaseKeys(client);
		holdSpot(player);
		if (inventoryFull(player)) {
			if (player.fishing != null) {
				useRod(client, player);
				status = "背包满了，先收钩再存箱";
				overlay(client, status, 0xFFFF55);
				return;
			}
			if (chestPos == null) chestPos = findNearbyChest(client, player);
			if (chestPos == null) {
				stop(client, "背包满了，附近没有箱子");
				return;
			}
			phase = Phase.APPROACH_CHEST;
			status = "背包满了，去存箱子";
			overlay(client, status, 0xFFFF55);
			return;
		}

		if (!holdRod(client, player)) {
			status = "快捷栏没有鱼竿";
			overlay(client, status, 0xFF5555);
			return;
		}

		if (config.fisherLeaveHookToMeteor && meteorAutoFishActive()) {
			showStats(client);
			return;
		}

		castOrCatch(client, player);
		if (active && phase == Phase.FISH) showStats(client);
	}

	/** 钓鱼阶段被改视角后写回锁定朝向。 */
	public void reapplyLook(Minecraft client) {
		if (!active || client.player == null) return;
		if (phase != Phase.FISH) return;
		if (client.screen != null) return;
		applySpotLook(client.player);
	}

	/** 无钩抛竿；咬钩后短等再收。 */
	private void castOrCatch(Minecraft client, LocalPlayer player) {
		FishingHook hook = player.fishing;
		if (hook == null) {
			sawBite = false;
			caughtWait = 0;
			if (cooldown > 0) return;
			useRod(client, player);
			return;
		}
		if (hook.getHookedIn() != null) {
			useRod(client, player);
			caughtCount++;
			return;
		}
		boolean biting = hook instanceof FishingHookBiteAccess access && access.kit$biting();
		if (biting && !sawBite) {
			sawBite = true;
			caughtWait = CATCH_WAIT;
			return;
		}
		if (sawBite) {
			if (caughtWait > 0) {
				caughtWait--;
				return;
			}
			useRod(client, player);
			caughtCount++;
		}
	}

	/** 用统计策略刷新字幕。 */
	private void showStats(Minecraft client) {
		long elapsed = sessionStartMs <= 0L ? 0L : System.currentTimeMillis() - sessionStartMs;
		status = FisherStatsPolicy.hud(caughtCount, elapsed);
		overlay(client, status, 0x55FFFF);
	}

	/** 走向附近箱子。 */
	private void approachChest(Minecraft client, LocalPlayer player) {
		if (chestPos == null) chestPos = findNearbyChest(client, player);
		if (chestPos == null) {
			stop(client, "附近没有箱子");
			return;
		}
		Vec3 target = Vec3.atCenterOf(chestPos);
		if (player.distanceToSqr(target) > 20.25) {
			lookAt(player, target);
			client.options.keyUp.setDown(true);
			status = "走向箱子";
			overlay(client, status, 0xFFFF55);
			return;
		}
		releaseKeys(client);
		phase = Phase.OPEN_CHEST;
		openWait = 0;
	}

	/** 打开箱子并把非鱼竿物品快移进去。 */
	private void handleStash(Minecraft client, LocalPlayer player) {
		if (phase == Phase.OPEN_CHEST) {
			if (client.screen instanceof AbstractContainerScreen<?> screen && isChestMenu(screen.getMenu())) {
				phase = Phase.DUMP;
				dumpStreak = 0;
				cooldown = 2;
				status = "开始往箱子里放";
				return;
			}
			if (openWait++ > 40) {
				phase = Phase.APPROACH_CHEST;
				openWait = 0;
				status = "没打开箱子，再试";
				return;
			}
			if (openWait == 1 || openWait % OPEN_WAIT == 0) {
				lookAt(player, Vec3.atCenterOf(chestPos));
				BlockHitResult hit = new BlockHitResult(Vec3.atCenterOf(chestPos), facingFrom(player, chestPos), chestPos, false);
				client.gameMode.useItemOn(player, InteractionHand.MAIN_HAND, hit);
			}
			status = "打开箱子";
			return;
		}
		if (!(client.screen instanceof AbstractContainerScreen<?> screen) || !isChestMenu(screen.getMenu())) {
			phase = Phase.RETURN;
			releaseKeys(client);
			return;
		}
		if (cooldown > 0) return;
		AbstractContainerMenu menu = screen.getMenu();
		Slot dump = nextDumpSlot(player, menu);
		if (dump == null) {
			player.closeContainer();
			phase = Phase.RETURN;
			status = "箱子已存完，回钓点";
			overlay(client, status, 0x55FF55);
			return;
		}
		int before = dump.getItem().getCount();
		client.gameMode.handleContainerInput(menu.containerId, dump.index, 0, ContainerInput.QUICK_MOVE, player);
		cooldown = DUMP_COOLDOWN;
		if (dump.hasItem() && dump.getItem().getCount() == before) {
			dumpStreak++;
		} else {
			dumpStreak = 0;
		}
		if (dumpStreak >= 2) {
			player.closeContainer();
			if (inventoryFull(player)) {
				stop(client, "箱子满了，背包还是满的");
				return;
			}
			phase = Phase.RETURN;
			status = "箱子装不下了，先回去钓";
			overlay(client, status, 0xFFFF55);
		} else {
			status = "往箱子里放";
		}
	}

	/** 存完走回钓点并恢复视角。 */
	private void returnToSpot(Minecraft client, LocalPlayer player) {
		double dx = spotX - player.getX();
		double dz = spotZ - player.getZ();
		double dist = Math.hypot(dx, dz);
		if (dist > SPOT_TOLERANCE) {
			lookAt(player, new Vec3(spotX, player.getEyeY(), spotZ));
			client.options.keyUp.setDown(true);
			status = "走回钓点";
			overlay(client, status, 0xFFFF55);
			return;
		}
		releaseKeys(client);
		player.setPos(spotX, player.getY(), spotZ);
		applySpotLook(player);
		phase = Phase.FISH;
		cooldown = CAST_COOLDOWN;
		sawBite = false;
		status = "回到钓点，继续钓";
		overlay(client, status, 0x55FF55);
	}

	/** 保持锁定视角；偏出容差则拉回坐标。 */
	private void holdSpot(LocalPlayer player) {
		applySpotLook(player);
		double dist = Math.hypot(player.getX() - spotX, player.getZ() - spotZ);
		if (dist > SPOT_TOLERANCE) {
			player.setPos(spotX, player.getY(), spotZ);
		}
	}

	/** 瞬间对准开局 yaw/pitch。 */
	private void applySpotLook(LocalPlayer player) {
		player.setYRot(spotYaw);
		player.setXRot(spotPitch);
		player.setYHeadRot(spotYaw);
		player.setYBodyRot(spotYaw);
	}

	/** 快捷栏选完好鱼竿握在主手。 */
	private boolean holdRod(Minecraft client, LocalPlayer player) {
		if (player.getMainHandItem().getItem() instanceof FishingRodItem
			&& !almostBroken(player.getMainHandItem())) {
			return true;
		}
		Inventory inv = player.getInventory();
		int best = -1;
		for (int i = 0; i < 9; i++) {
			ItemStack stack = inv.getItem(i);
			if (stack.getItem() instanceof FishingRodItem && !almostBroken(stack)) {
				best = i;
				break;
			}
		}
		if (best < 0) return false;
		inv.setSelectedSlot(best);
		return player.getMainHandItem().getItem() instanceof FishingRodItem;
	}

	/** 右键抛/收竿并进入冷却。 */
	private void useRod(Minecraft client, LocalPlayer player) {
		if (cooldown > 0) return;
		client.gameMode.useItem(player, InteractionHand.MAIN_HAND);
		sawBite = false;
		caughtWait = 0;
		cooldown = CAST_COOLDOWN;
	}

	/** 耐久只剩 1 及以下。 */
	private static boolean almostBroken(ItemStack stack) {
		return stack.isDamageableItem() && stack.getMaxDamage() - stack.getDamageValue() <= 1;
	}

	/** 主背包 36 格无空位。 */
	private static boolean inventoryFull(LocalPlayer player) {
		Inventory inv = player.getInventory();
		for (int i = 0; i < 36; i++) {
			if (inv.getItem(i).isEmpty()) return false;
		}
		return true;
	}

	/** 下一个可快移进箱的非鱼竿槽。 */
	private static Slot nextDumpSlot(LocalPlayer player, AbstractContainerMenu menu) {
		for (Slot slot : menu.slots) {
			if (slot.container != player.getInventory() || !slot.hasItem()) continue;
			if (slot.getItem().getItem() instanceof FishingRodItem) continue;
			return slot;
		}
		return null;
	}

	/** 是否箱子/潜影盒/漏斗菜单。 */
	private static boolean isChestMenu(AbstractContainerMenu menu) {
		return menu instanceof ChestMenu || menu instanceof ShulkerBoxMenu || menu instanceof HopperMenu;
	}

	/** 半径内按优先级找最近存储方块。 */
	private BlockPos findNearbyChest(Minecraft client, LocalPlayer player) {
		int range = Math.max(2, Math.min(8, config.fisherChestRange));
		BlockPos feet = player.blockPosition();
		BlockPos best = null;
		int bestRank = Integer.MAX_VALUE;
		double bestDist = Double.MAX_VALUE;
		for (int dy = -2; dy <= 2; dy++) {
			for (int dx = -range; dx <= range; dx++) {
				for (int dz = -range; dz <= range; dz++) {
					BlockPos pos = feet.offset(dx, dy, dz);
					int rank = storageRank(client, pos);
					if (rank < 0) continue;
					double dist = player.distanceToSqr(Vec3.atCenterOf(pos));
					if (rank < bestRank || rank == bestRank && dist < bestDist) {
						bestRank = rank;
						bestDist = dist;
						best = pos.immutable();
					}
				}
			}
		}
		return best;
	}

	/** 铜箱子优先，末影箱最后。 */
	private static int storageRank(Minecraft client, BlockPos pos) {
		var block = client.level.getBlockState(pos).getBlock();
		if (block instanceof CopperChestBlock) return 0;
		if (block instanceof ChestBlock || block instanceof BarrelBlock || block instanceof ShulkerBoxBlock) return 1;
		if (block instanceof EnderChestBlock) return 2;
		return -1;
	}

	/** 从眼睛指向目标格推断放置朝向。 */
	private static Direction facingFrom(LocalPlayer player, BlockPos pos) {
		Vec3 eye = player.getEyePosition();
		Vec3 center = Vec3.atCenterOf(pos);
		Vec3 delta = center.subtract(eye);
		if (Math.abs(delta.y) > Math.abs(delta.x) && Math.abs(delta.y) > Math.abs(delta.z)) {
			return delta.y > 0 ? Direction.DOWN : Direction.UP;
		}
		if (Math.abs(delta.x) > Math.abs(delta.z)) {
			return delta.x > 0 ? Direction.WEST : Direction.EAST;
		}
		return delta.z > 0 ? Direction.NORTH : Direction.SOUTH;
	}

	/** 瞬间对准目标点。 */
	private static void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/** Meteor auto-fish 是否开着。 */
	private static boolean meteorAutoFishActive() {
		return BorerFlight.meteorAutoFishActive();
	}

	/** 松开前进/后退。 */
	private static void releaseKeys(Minecraft client) {
		if (client.options == null) return;
		client.options.keyUp.setDown(false);
		client.options.keyDown.setDown(false);
	}

	/** 叠字幕提示。 */
	private static void overlay(Minecraft client, String text, int color) {
		client.gui.setOverlayMessage(Component.literal("[钓鱼] " + text).withColor(color), false);
	}

	/** 发系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[钓鱼] " + text));
	}
}
