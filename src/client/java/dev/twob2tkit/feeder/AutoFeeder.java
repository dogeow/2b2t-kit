package dev.twob2tkit.feeder;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.network.chat.Component;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.animal.Animal;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.BowItem;
import net.minecraft.world.item.CrossbowItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.MaceItem;
import net.minecraft.world.item.TridentItem;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import dev.twob2tkit.ApproachTracker;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitKeys;

/** 自动喂养：走近勾选动物、喂食繁殖/催熟，喂完收起饲料避免误伤。 */
public final class AutoFeeder {
	private static final int ACTION_COOLDOWN = 8;
	private static final int BABY_COOLDOWN = 12;
	private static final int ADULT_COOLDOWN = 6100;
	private static final int STUCK_TICKS = 40;
	private static final int SKIP_TICKS = 80;
	private static final double STACK_DISTANCE = 0.55;

	private final KitConfig config;
	private final Map<UUID, Integer> fedUntilTick = new HashMap<>();
	private final Map<UUID, Integer> skipUntilTick = new HashMap<>();
	private boolean active;
	private String status = "";
	private Animal target;
	private int cooldown;
	private int backupTicks;
	private int fedCount;
	private final ApproachTracker approach = new ApproachTracker();

	/** 按配置构造喂养控制器。 */
	public AutoFeeder(KitConfig config) {
		this.config = config;
	}

	/** 是否正在喂养。 */
	public boolean isActive() {
		return active;
	}

	/** 最近状态文案。 */
	public String status() {
		return status;
	}

	/** 本局已喂次数。 */
	public int fedCount() {
		return fedCount;
	}

	/** 开始喂养并清冷却表。 */
	public void start(Minecraft client) {
		if (client.player == null || client.level == null) return;
		active = true;
		cooldown = 0;
		backupTicks = 0;
		fedCount = 0;
		target = null;
		approach.reset();
		fedUntilTick.clear();
		skipUntilTick.clear();
		status = "开始喂养";
		message(client, "自动喂养已开启。喂完会收起饲料并换成非武器，避免自动攻击误伤。再按 "
			+ KitKeys.boundLabel(KitKeys.TOGGLE_FEEDER) + " 或 End 停止");
	}

	/** 停止、松键、收起饲料并说明原因。 */
	public void stop(Minecraft client, String reason) {
		if (!active) return;
		active = false;
		target = null;
		approach.reset();
		releaseKeys(client);
		hideTemptFood(client);
		status = "已停止：" + reason;
		message(client, "自动喂养已停止：" + reason + (fedCount > 0 ? "（本次喂了 " + fedCount + " 次）" : ""));
	}

	/** 热键开/关。 */
	public void toggle(Minecraft client) {
		if (active) stop(client, "按键停止");
		else start(client);
	}

	/** 主循环：选动物、走近、喂食或后退。 */
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		if (client.screen != null) {
			releaseKeys(client);
			status = "先关掉界面再喂";
			return;
		}

		LocalPlayer player = client.player;
		int now = player.tickCount;
		prune(fedUntilTick, now);
		prune(skipUntilTick, now);

		List<Animal> nearby = collect(client, player);
		try {
			emitGizmos(nearby);
		} catch (IllegalStateException ignored) {
		}

		if (backupTicks > 0) {
			backupTicks--;
			hideTemptFood(client);
			lookAt(player, player.position().add(player.getLookAngle().scale(-1.0)));
			client.options.keyUp.setDown(false);
			client.options.keyDown.setDown(true);
			status = offhandHint(player, "先走开，避免牛羊再挤上来");
			overlay(client, status, 0xFFFF55);
			return;
		}

		if (cooldown > 0) {
			cooldown--;
			releaseKeys(client);
			hideTemptFood(client);
			return;
		}

		Animal next = pick(player, nearby, now);
		target = next;
		if (next == null) {
			releaseKeys(client);
			hideTemptFood(client);
			status = offhandHint(player, emptyStatus(player, nearby));
			overlay(client, status, nearby.isEmpty() ? 0xA0A0A0 : 0xFFFF55);
			return;
		}

		boolean inReach = player.isWithinEntityInteractionRange(next, 0.0);
		if (!inReach) {
			hideTemptFood(client);
			if (!approach(client, player, next, now)) return;
			status = (isStacked(next, nearby) ? "叠在一起，走近分开喂  " : "走向 ") + next.getName().getString();
			overlay(client, status, 0x55FFFF);
			return;
		}

		releaseKeys(client);
		if (feed(client, player, next, now)) {
			fedCount++;
			boolean stacked = isStacked(next, nearby);
			status = "已喂 " + next.getName().getString() + "  共 " + fedCount + " 次"
				+ (stacked ? "，先走开" : "");
			overlay(client, status, 0x55FF55);
			cooldown = ACTION_COOLDOWN;
			if (stacked || config.feederHideFood) backupTicks = stacked ? 10 : 0;
			hideTemptFood(client);
			return;
		}

		hideTemptFood(client);
		status = "这次没喂上，换一只";
		skipUntilTick.put(next.getUUID(), now + 20);
		overlay(client, status, 0xFFFF55);
	}

	/** 对准当前目标。 */
	public void reapplyLook(Minecraft client) {
		if (!active || target == null || !target.isAlive() || client.player == null) return;
		if (client.screen != null) return;
		lookAt(client.player, target.getBoundingBox().getCenter());
	}

	/** 走近目标；卡住则跳过。 */
	private boolean approach(Minecraft client, LocalPlayer player, Animal animal, int now) {
		if (!config.feederWalk) {
			releaseKeys(client);
			status = "太远，走近一点或打开「走近再喂」";
			overlay(client, status, 0xFFFF55);
			return false;
		}
		if (player.isPassenger()) {
			releaseKeys(client);
			status = "先下来再喂";
			overlay(client, status, 0xFFFF55);
			return false;
		}
		double vertical = player.getY() - animal.getY();
		if (player.getAbilities().flying && vertical > 2.8) {
			releaseKeys(client);
			status = "飞低一点再喂";
			overlay(client, status, 0xFFFF55);
			return false;
		}

		double dist = Math.sqrt(player.distanceToSqr(animal));
		if (approach.track(animal.getUUID(), dist, STUCK_TICKS)) {
			skipUntilTick.put(animal.getUUID(), now + SKIP_TICKS);
			approach.reset();
			releaseKeys(client);
			status = "过不去，先换一只";
			overlay(client, status, 0xFFFF55);
			return false;
		}

		lookAt(player, animal.getBoundingBox().getCenter());
		boolean overlapping = player.getBoundingBox().inflate(0.05).intersects(animal.getBoundingBox());
		client.options.keyUp.setDown(!overlapping);
		client.options.keyDown.setDown(overlapping);
		return true;
	}

	/** 选饲料并交互喂食。 */
	private boolean feed(Minecraft client, LocalPlayer player, Animal animal, int now) {
		InteractionHand hand = selectFood(client, animal);
		if (hand == null) return false;
		lookAt(player, animal.getBoundingBox().getCenter());
		EntityHitResult hit = new EntityHitResult(animal, animal.getBoundingBox().getCenter());
		InteractionResult result = client.gameMode.interact(player, animal, hit, hand);
		player.swing(hand);
		fedUntilTick.put(animal.getUUID(), now + (animal.isBaby() ? BABY_COOLDOWN : ADULT_COOLDOWN));
		approach.reset();
		return result.consumesAction() || result != InteractionResult.FAIL;
	}

	/** 按优先顺序与距离挑下一只。 */
	private Animal pick(LocalPlayer player, List<Animal> nearby, int now) {
		Animal best = null;
		double bestScore = Double.MAX_VALUE;
		List<String> order = config.feederTypeOrder();
		for (Animal animal : nearby) {
			if (!canFeedNow(player, animal, now)) continue;
			if (!hasFood(player, animal)) continue;
			double dist = player.distanceToSqr(animal);
			int rank = order.indexOf(typeId(animal));
			if (rank < 0) rank = 99;
			double score = rank * 1_000_000.0 + dist;
			if (isStacked(animal, nearby)) score += 4.0;
			if (player.isWithinEntityInteractionRange(animal, 0.0)) score -= 8.0;
			if (score < bestScore) {
				bestScore = score;
				best = animal;
			}
		}
		return best;
	}

	/** 范围内勾选类型的存活动物。 */
	private List<Animal> collect(Minecraft client, LocalPlayer player) {
		List<Animal> result = new ArrayList<>();
		double range = Math.max(3.0, config.feederRange);
		double rangeSqr = range * range;
		for (Entity entity : client.level.entitiesForRendering()) {
			if (!(entity instanceof Animal animal) || !animal.isAlive() || animal.isRemoved()) continue;
			if (!typeEnabled(animal)) continue;
			if (player.distanceToSqr(animal) > rangeSqr) continue;
			result.add(animal);
		}
		return result;
	}

	/** 类型开着、不在冷却、且可繁殖或催熟。 */
	private boolean canFeedNow(LocalPlayer player, Animal animal, int now) {
		if (!typeEnabled(animal)) return false;
		Integer skip = skipUntilTick.get(animal.getUUID());
		if (skip != null && now < skip) return false;
		Integer fed = fedUntilTick.get(animal.getUUID());
		if (fed != null && now < fed) return false;
		if (animal.isBaby()) return config.feederGrowBabies && !animal.isAgeLocked();
		return config.feederBreedAdults && animal.canFallInLove();
	}

	/** 该动物类型是否勾选。 */
	private boolean typeEnabled(Animal animal) {
		return config.feederTypeEnabled(typeId(animal));
	}

	/** 实体类型转配置 id。 */
	private static String typeId(Animal animal) {
		EntityType<?> type = animal.getType();
		if (type == EntityType.COW) return "cow";
		if (type == EntityType.SHEEP) return "sheep";
		if (type == EntityType.PIG) return "pig";
		if (type == EntityType.CHICKEN) return "chicken";
		if (type == EntityType.MOOSHROOM) return "mooshroom";
		if (type == EntityType.GOAT) return "goat";
		if (type == EntityType.RABBIT) return "rabbit";
		return "";
	}

	/** 是否与附近同类叠在一起。 */
	private boolean isStacked(Animal animal, List<Animal> nearby) {
		for (Animal other : nearby) {
			if (other == animal) continue;
			double dx = animal.getX() - other.getX();
			double dz = animal.getZ() - other.getZ();
			if (dx * dx + dz * dz <= STACK_DISTANCE * STACK_DISTANCE
				&& Math.abs(animal.getY() - other.getY()) < 1.2) {
				return true;
			}
		}
		return false;
	}

	/** 没有可喂时的说明文案。 */
	private String emptyStatus(LocalPlayer player, List<Animal> nearby) {
		if (!config.feederBreedAdults && !config.feederGrowBabies) return "请先勾选繁殖成体或催熟幼体";
		int adults = 0;
		int babies = 0;
		int cooling = 0;
		int now = player.tickCount;
		for (Animal animal : nearby) {
			if (animal.isBaby()) babies++;
			else adults++;
			Integer fed = fedUntilTick.get(animal.getUUID());
			if (fed != null && now < fed && !animal.isBaby()) cooling++;
		}
		if (nearby.isEmpty()) return "附近 " + formatRange() + " 格没有勾选的动物";
		if (cooling > 0 && cooling >= adults && babies == 0) {
			return "成体都在冷却，大约 5 分钟后可再繁殖";
		}
		if (!hasAnyFood(player, nearby)) return "附近有动物，但背包没有能喂的饲料";
		return "附近 " + nearby.size() + " 只，暂时不用喂（已喂 " + fedCount + " 次）";
	}

	/** 副手是饲料时追加提醒。 */
	private String offhandHint(LocalPlayer player, String text) {
		return temptsEnabled(player.getOffhandItem()) ? text + "；副手也是饲料，先拿开" : text;
	}

	/** 搜寻范围显示字符串。 */
	private String formatRange() {
		double range = Math.max(3.0, config.feederRange);
		return range == Math.rint(range) ? Integer.toString((int)range) : String.format("%.1f", range);
	}

	/** 附近是否有能喂的饲料。 */
	private boolean hasAnyFood(LocalPlayer player, List<Animal> nearby) {
		for (Animal animal : nearby) {
			if (hasFood(player, animal)) return true;
		}
		return false;
	}

	/** 背包是否有该动物可吃的饲料。 */
	private boolean hasFood(LocalPlayer player, Animal animal) {
		if (animal.isFood(player.getMainHandItem()) || animal.isFood(player.getOffhandItem())) return true;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (animal.isFood(stack)) return true;
		}
		return false;
	}

	/** 主手/快捷栏/背包/副手选出饲料手。 */
	private InteractionHand selectFood(Minecraft client, Animal animal) {
		LocalPlayer player = client.player;
		if (animal.isFood(player.getMainHandItem())) return InteractionHand.MAIN_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!animal.isFood(inventory.getItem(slot))) continue;
			inventory.setSelectedSlot(slot);
			return InteractionHand.MAIN_HAND;
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!animal.isFood(inventory.getItem(slot))) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			if (animal.isFood(player.getMainHandItem()) || animal.isFood(inventory.getItem(inventory.getSelectedSlot()))) {
				return InteractionHand.MAIN_HAND;
			}
		}
		if (animal.isFood(player.getOffhandItem())) return InteractionHand.OFF_HAND;
		return null;
	}

	/** 喂完换成空手或非武器，避免引怪与误伤。 */
	private void hideTemptFood(Minecraft client) {
		if (!config.feederHideFood || client.player == null) return;
		LocalPlayer player = client.player;
		if (isSafeHideStack(player.getMainHandItem())) return;
		Inventory inventory = player.getInventory();
		int emptyHotbar = -1;
		int safeHotbar = -1;
		for (int slot = 0; slot < 9; slot++) {
			ItemStack stack = inventory.getItem(slot);
			if (stack.isEmpty()) {
				if (emptyHotbar < 0) emptyHotbar = slot;
				continue;
			}
			if (safeHotbar < 0 && isSafeHideStack(stack)) safeHotbar = slot;
		}
		if (emptyHotbar >= 0) {
			inventory.setSelectedSlot(emptyHotbar);
			return;
		}
		if (safeHotbar >= 0) {
			inventory.setSelectedSlot(safeHotbar);
			return;
		}
		for (int slot = 9; slot < 36; slot++) {
			ItemStack stack = inventory.getItem(slot);
			if (!stack.isEmpty() && !isSafeHideStack(stack)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			return;
		}
	}

	/** 空格或方块等；不要换成剑斧，Meteor KillAura 默认拿着武器就会打。 */
	private boolean isSafeHideStack(ItemStack stack) {
		return !temptsEnabled(stack) && !isWeapon(stack);
	}

	/** 是否剑斧矛三叉戟钉头锤弓弩。 */
	private static boolean isWeapon(ItemStack stack) {
		if (stack.isEmpty()) return false;
		if (stack.is(ItemTags.SWORDS) || stack.is(ItemTags.AXES) || stack.is(ItemTags.SPEARS)) return true;
		return stack.getItem() instanceof TridentItem
			|| stack.getItem() instanceof MaceItem
			|| stack.getItem() instanceof BowItem
			|| stack.getItem() instanceof CrossbowItem;
	}

	/** 是否勾选动物会跟着的饲料。 */
	private boolean temptsEnabled(ItemStack stack) {
		if (stack.isEmpty()) return false;
		if ((config.feederCow || config.feederMooshroom) && stack.is(ItemTags.COW_FOOD)) return true;
		if (config.feederSheep && stack.is(ItemTags.SHEEP_FOOD)) return true;
		if (config.feederPig && stack.is(ItemTags.PIG_FOOD)) return true;
		if (config.feederChicken && stack.is(ItemTags.CHICKEN_FOOD)) return true;
		if (config.feederGoat && stack.is(ItemTags.GOAT_FOOD)) return true;
		if (config.feederRabbit && stack.is(ItemTags.RABBIT_FOOD)) return true;
		return false;
	}

	/** 画出附近动物碰撞箱与当前目标。 */
	private void emitGizmos(List<Animal> nearby) {
		Minecraft client = Minecraft.getInstance();
		if (client.player == null) return;
		int now = client.player.tickCount;
		for (Animal animal : nearby) {
			boolean current = animal == target;
			boolean stacked = isStacked(animal, nearby);
			boolean ready = canFeedNow(client.player, animal, now);
			int stroke = current ? 0xFF00FFFF : stacked ? 0xFFFF5555 : ready ? 0xFF55FF55 : 0x66AAAAAA;
			int fill = current ? 0x3300FFFF : stacked ? 0x33FF5555 : ready ? 0x2200FF55 : 0x11AAAAAA;
			Gizmos.cuboid(animal.getBoundingBox().inflate(0.05), GizmoStyle.strokeAndFill(stroke, current ? 2.5F : 1.2F, fill));
			if (current) {
				Gizmos.billboardTextOverMob(animal, 0, "喂", 0xFF55FFFF, 0.35F);
			}
		}
	}

	/** 瞬间对准目标点。 */
	private void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/** 清掉已过期的 UUID 冷却。 */
	private static void prune(Map<UUID, Integer> map, int now) {
		Iterator<Map.Entry<UUID, Integer>> iterator = map.entrySet().iterator();
		while (iterator.hasNext()) {
			if (iterator.next().getValue() < now) iterator.remove();
		}
	}

	/** 松开前进/后退。 */
	private static void releaseKeys(Minecraft client) {
		client.options.keyUp.setDown(false);
		client.options.keyDown.setDown(false);
	}

	/** 叠字幕提示。 */
	private static void overlay(Minecraft client, String text, int color) {
		client.gui.setOverlayMessage(Component.literal("[喂养] " + text).withColor(color), false);
	}

	/** 发系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[喂养] " + text));
	}
}
