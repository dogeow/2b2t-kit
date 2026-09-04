package dev.twob2tkit.surround;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.network.chat.Component;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitKeys;

/**
 * 自动围箱：用勾选方块把自己封进 10 格壳（脚下、四面脚边、四面头边、头顶）。
 * <p>
 * 与 Meteor Surround 不同——那边是脚下黑曜石防水晶；这里是整人封盒躲怪。
 * 半空放置依赖玩家已开的隔空放置；本类只模拟视角与 useItemOn。
 */
public final class AutoSurround {
	/** 围箱模式：锁定原点，或每拍跟着玩家脚底。 */
	public enum Mode {
		FULL("十格锁定"),
		PLUS("十格跟随");

		public final String label;

		Mode(String label) {
			this.label = label;
		}

		/** 从配置字符串解析；非法或空则默认十格跟随。 */
		public static Mode fromConfig(String value) {
			try {
				return value == null ? PLUS : valueOf(value);
			} catch (IllegalArgumentException ignored) {
				return PLUS;
			}
		}
	}

	private final KitConfig config;
	private boolean active;
	private Mode mode = Mode.FULL;
	private BlockPos origin;
	private String status = "";
	private BlockPos lastTarget;
	private int completeStreak;

	public AutoSurround(KitConfig config) {
		this.config = config;
	}

	/** 是否正在围箱。 */
	public boolean isActive() {
		return active;
	}

	/** 当前模式。 */
	public Mode mode() {
		return mode;
	}

	/** 最近一条状态文案（界面与 HUD 共用）。 */
	public String status() {
		return status;
	}

	/** 按模式开始：钉住脚底原点、写入配置、发聊天提示。 */
	public void start(Minecraft client, Mode mode) {
		if (client.player == null || client.level == null) return;
		this.mode = mode;
		config.surroundMode = mode.name();
		config.save();
		origin = client.player.blockPosition();
		active = true;
		completeStreak = 0;
		lastTarget = null;
		Item item = SurroundBlocks.resolve(client.player, config.surroundBlockIds);
		status = "围箱：" + mode.label + "  优先 " + SurroundBlocks.summary(config.surroundBlockIds);
		message(client, status + "。半空用你的隔空放置。再按 "
			+ KitKeys.boundLabel(KitKeys.TOGGLE_SURROUND) + " 或 End 停止");
	}

	/** 停止围箱并说明原因。 */
	public void stop(Minecraft client, String reason) {
		if (!active) return;
		active = false;
		lastTarget = null;
		origin = null;
		completeStreak = 0;
		status = "已停止：" + reason;
		message(client, "围箱已停止：" + reason);
	}

	/** 热键切换：开则停，停则按配置模式开。 */
	public void toggle(Minecraft client) {
		if (active) stop(client, "按键停止");
		else start(client, Mode.fromConfig(config.surroundMode));
	}

	/**
	 * 每拍：补缺格、画 gizmo、更新叠加提示。
	 * 有界面时只提示不放；围满且未勾选继续补洞时连几拍后自动停。
	 */
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		if (client.screen != null) {
			status = "先关掉界面再围";
			return;
		}

		LocalPlayer player = client.player;
		Item item = SurroundBlocks.resolve(player, config.surroundBlockIds);
		if (!(item instanceof BlockItem) || item == Items.AIR) {
			status = "没有可用围箱方块，请在设置里勾选";
			client.gui.setOverlayMessage(Component.literal("[围箱] " + status).withColor(0xFF5555), false);
			return;
		}
		Block block = ((BlockItem)item).getBlock();
		if (followsPlayer()) {
			origin = player.blockPosition();
		}
		if (origin == null) origin = player.blockPosition();

		List<BlockPos> cells = shell(origin);
		int done = 0;
		List<BlockPos> missing = new ArrayList<>();
		for (BlockPos pos : cells) {
			BlockState state = client.level.getBlockState(pos);
			if (!isReplaceable(state)) {
				done++;
			} else {
				missing.add(pos);
			}
		}

		try {
			emitGizmos(cells);
		} catch (IllegalStateException ignored) {
		}

		if (missing.isEmpty()) {
			lastTarget = null;
			completeStreak++;
			status = config.surroundKeepRepair
				? "已围好 " + done + "/10，地形已有的不算，破了会补"
				: "已围好 " + done + "/10，地形已有的已跳过";
			client.gui.setOverlayMessage(Component.literal("[围箱] " + status).withColor(0x55FF55), false);
			if (!config.surroundKeepRepair && completeStreak > 4) {
				stop(client, "已经围好");
			}
			return;
		}
		completeStreak = 0;

		if (!player.hasInfiniteMaterials() && SurroundBlocks.count(player, item) <= 0) {
			status = "背包没有勾选的围箱方块，缺 " + missing.size() + " 格。当前优先：" + SurroundBlocks.summary(config.surroundBlockIds);
			client.gui.setOverlayMessage(Component.literal("[围箱] " + status).withColor(0xFF5555), false);
			return;
		}

		missing.sort(Comparator
			.comparingInt((BlockPos pos) -> layer(origin, pos))
			.thenComparingInt(pos -> findSupport(client, pos, block) == null ? 1 : 0)
			.thenComparingDouble(pos -> pos.distSqr(origin)));

		int budget = Math.max(1, Math.min(4, config.surroundPlacesPerTick));
		int placed = 0;
		boolean sawReach = false;
		for (BlockPos pos : missing) {
			if (placed >= budget) break;
			if (player.getBoundingBox().intersects(new AABB(pos))) continue;
			if (!inReach(player, pos)) continue;
			sawReach = true;
			InteractionHand hand = selectItem(client, item);
			if (hand == null) {
				status = "拿不到 " + itemLabel(item);
				client.gui.setOverlayMessage(Component.literal("[围箱] " + status).withColor(0xFF5555), false);
				return;
			}
			if (placeAt(client, player, pos, block, hand)) {
				lastTarget = pos;
				placed++;
			}
		}

		if (placed > 0) {
			status = mode.label + "  已有 " + (done + placed) + "/10，还缺 "
				+ Math.max(0, missing.size() - placed) + "  " + itemLabel(item);
			client.gui.setOverlayMessage(Component.literal("[围箱] " + status).withColor(0x55FFFF), false);
			return;
		}

		status = sawReach ? "这一格没放上，下下再试" : "有的格子太远，站回箱子中间";
		client.gui.setOverlayMessage(Component.literal("[围箱] " + status).withColor(0xFFFF55), false);
	}

	/** 十格跟随模式下原点每拍跟脚底。 */
	private boolean followsPlayer() {
		return mode == Mode.PLUS;
	}

	/**
	 * 相对脚底生成 10 格壳：脚下 1、四面脚边、四面头边、头顶 1。
	 * 不做四角，也不铺额外地板/屋顶。
	 */
	public static List<BlockPos> shell(BlockPos feet) {
		List<BlockPos> cells = new ArrayList<>();
		cells.add(feet.below());
		for (Direction direction : Direction.Plane.HORIZONTAL) {
			cells.add(feet.relative(direction));
			cells.add(feet.above().relative(direction));
		}
		cells.add(feet.above(2));
		return cells;
	}

	/** 放置优先级层：脚下优先，再脚边，再头边，再顶。 */
	private static int layer(BlockPos origin, BlockPos pos) {
		int dy = pos.getY() - origin.getY();
		if (dy < 0) return 0;
		return dy + 1;
	}

	/** 先对邻接支撑面放，失败再试朝准星的空气点击（隔空放置）。 */
	private boolean placeAt(Minecraft client, LocalPlayer player, BlockPos pos, Block block, InteractionHand hand) {
		lookAt(player, Vec3.atCenterOf(pos));
		BlockHitResult support = findSupport(client, pos, block);
		BlockHitResult air = airHit(player, pos);
		if (tryPlace(client, player, pos, block, hand, support != null ? support : air)) return true;
		return support != null && tryPlace(client, player, pos, block, hand, air);
	}

	/** 对指定命中调用 useItemOn；动作消耗或方块已非可替换则视为成功。 */
	private boolean tryPlace(Minecraft client, LocalPlayer player, BlockPos pos, Block block, InteractionHand hand, BlockHitResult hit) {
		lookAt(player, hit.getLocation());
		InteractionResult result = client.gameMode.useItemOn(player, hand, hit);
		return result.consumesAction() || !isReplaceable(client.level.getBlockState(pos));
	}

	/** 找邻接实体方块作支撑；同种围箱方块优先，否则任意实心邻接。 */
	private BlockHitResult findSupport(Minecraft client, BlockPos pos, Block want) {
		Direction[] order = {Direction.DOWN, Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST, Direction.UP};
		BlockHitResult typed = null;
		BlockHitResult any = null;
		for (Direction direction : order) {
			BlockPos neighbor = pos.relative(direction);
			BlockState state = client.level.getBlockState(neighbor);
			if (isReplaceable(state)) continue;
			BlockHitResult hit = click(neighbor, direction.getOpposite());
			if (state.is(want) && typed == null) typed = hit;
			if (any == null) any = hit;
		}
		return typed != null ? typed : any;
	}

	/** 从眼睛指向目标格中心，构造隔空放置用的 BlockHitResult。 */
	private BlockHitResult airHit(LocalPlayer player, BlockPos pos) {
		Vec3 center = Vec3.atCenterOf(pos);
		Vec3 eye = player.getEyePosition();
		Direction face = Direction.getApproximateNearest(eye.x - center.x, eye.y - center.y, eye.z - center.z);
		return click(pos, face);
	}

	/** 在支撑面朝外半格处造点击命中。 */
	private BlockHitResult click(BlockPos support, Direction face) {
		Vec3 location = Vec3.atCenterOf(support).add(face.getStepX() * 0.51, face.getStepY() * 0.51, face.getStepZ() * 0.51);
		return new BlockHitResult(location, face, support, false);
	}

	/** 瞬间对准目标点（交给 RotationAim）。 */
	private void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/**
	 * 把手中物品切到目标围箱方块：主手/副手/热栏，必要时从背包与热栏交换。
	 * @return 可用的手；拿不到则 null
	 */
	private InteractionHand selectItem(Minecraft client, Item item) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().is(item)) return InteractionHand.MAIN_HAND;
		if (player.getOffhandItem().is(item)) return InteractionHand.OFF_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).is(item)) {
				inventory.setSelectedSlot(slot);
				return InteractionHand.MAIN_HAND;
			}
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			if (player.getMainHandItem().is(item) || inventory.getItem(inventory.getSelectedSlot()).is(item)) {
				return InteractionHand.MAIN_HAND;
			}
		}
		return null;
	}

	/** 画出十格壳：已放绿、当前目标青、待放黄。 */
	private void emitGizmos(List<BlockPos> cells) {
		Minecraft client = Minecraft.getInstance();
		if (client.level == null) return;
		for (BlockPos pos : cells) {
			boolean done = !isReplaceable(client.level.getBlockState(pos));
			boolean next = pos.equals(lastTarget);
			int stroke = next ? 0xFF00FFFF : done ? 0xFF55FF55 : 0xAAFFAA00;
			int fill = next ? 0x6600FFFF : done ? 0x2200FF55 : 0x33FFAA00;
			Gizmos.cuboid(pos, GizmoStyle.strokeAndFill(stroke, next ? 3.0F : 1.5F, fill));
		}
	}

	/** 背包内目标物品数量（含副手）。 */
	public static int count(Player player, Item item) {
		return SurroundBlocks.count(player, item);
	}

	/** 取物品本地化显示名，用于状态栏提示。 */
	private static String itemLabel(Item item) {
		return new ItemStack(item).getHoverName().getString();
	}

	/** 眼睛到格心距离平方 ≤ 25（约 5 格）才尝试放置。 */
	private static boolean inReach(LocalPlayer player, BlockPos pos) {
		return player.getEyePosition().distanceToSqr(Vec3.atCenterOf(pos)) <= 25.0;
	}

	/** 空气、可替换方块或流体占位视为可被围箱覆盖。 */
	private static boolean isReplaceable(BlockState state) {
		return state.isAir() || state.canBeReplaced() || !state.getFluidState().isEmpty() && state.getFluidState().createLegacyBlock().is(state.getBlock());
	}

	/** 发带 [围箱] 前缀的系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[围箱] " + text));
	}
}
