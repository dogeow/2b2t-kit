package dev.twob2tkit.storage;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ChestMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.HopperMenu;
import net.minecraft.world.inventory.ShulkerBoxMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.BlockHitResult;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.adventure.ActivityRequirements;

/** 开箱记录快照，并按标签自动补货。 */
public final class ContainerAssistant {
	private static final int CLICK_REMEMBER_TICKS = 60;

	private final KitConfig config;
	private int currentContainerId = -1;
	private BlockPos openedPosition;
	private String openedDimension = "";
	private String lastFingerprint = "";
	private AbstractContainerMenu openedMenu;
	private String openedTitle = "";
	private boolean contentsSeen;
	private int ticksInContainer;
	private int takeCooldown;
	private boolean restockReported;
	private ActivityRequirements.Requirement pendingRequirement;
	private int pendingBeforeCount;
	private String pendingItemName = "";
	private BlockPos lastClickedStorage;
	private int lastClickedAge = 999;
	/** 按配置构造开箱助手。 */
	public ContainerAssistant(KitConfig config) {
		this.config = config;
	}

	/** 记下刚右键的存储方块。 */
	public void rememberClickedStorage(BlockPos pos) {
		if (pos == null) return;
		Minecraft client = Minecraft.getInstance();
		if (client.level == null || !StorageLabels.isStorageBlock(client.level, pos)) return;
		lastClickedStorage = pos.immutable();
		lastClickedAge = 0;
	}

	/** 开箱时快照并可自动补货。 */
	public void tick(Minecraft client) {
        StorageLifecycle.tick(client,config);
        if(dev.twob2tkit.automation.AutomationBridge.idleSupplyMenuPending())return;
		if (client.player == null || client.level == null) {
			resetOpenContainer();
			return;
		}
		if (!(client.gui.screen() instanceof AbstractContainerScreen<?> screen)) {
			resetOpenContainer();
			if (lastClickedAge < 1000) lastClickedAge++;
			return;
		}
		AbstractContainerMenu menu = screen.getMenu();
		if (!isSupported(menu)) {
			resetOpenContainer();
			return;
		}

		if (currentContainerId != menu.containerId) {
			currentContainerId = menu.containerId;
			openedPosition = resolveOpenedBlock(client);
			openedDimension = KitConfig.normalizeDimension(
				client.level.dimension().identifier().toString());
			lastFingerprint = "\u0000";
			openedMenu = menu;
			openedTitle = screen.getTitle().getString();
			contentsSeen = false;
			ticksInContainer = 0;
				takeCooldown = 0;
				restockReported = false;
				pendingRequirement = null;
				pendingItemName = "";
		}

		ticksInContainer++;
		if (takeCooldown > 0) takeCooldown--;
		// The menu opens empty; its slots are only real once the server's first contents packet arrives.
		boolean arrived = contentsSeen || contentsArrived(client, menu, ticksInContainer);
		if (openedPosition != null && arrived && (!contentsSeen || ticksInContainer % 10 == 0)) {
			recordSnapshot(client, openedTitle, menu);
		}
		contentsSeen = arrived;
		if (config.autoRestockFromOpenedContainers && takeCooldown == 0 && ticksInContainer >= 10
			&& (KitClient.borer() == null || !KitClient.borer().isManagingInventory())
			&& (KitClient.fisher() == null || !KitClient.fisher().isDepositing())) {
			attemptAutoRestock(client, menu);
		}
	}

	/** 是否支持的容器菜单。 */
	private boolean isSupported(AbstractContainerMenu menu) {
		return menu instanceof ChestMenu || menu instanceof ShulkerBoxMenu || menu instanceof HopperMenu;
	}

	/** 服务器首个内容包会把状态号推进到非零；兜底等 20 tick，真空箱也能记下。 */
	static boolean contentsArrived(Minecraft client, AbstractContainerMenu menu, int ticks) {
		if (menu.getStateId() != 0 || ticks >= 20) return true;
		for (Slot slot : menu.slots) {
			if (slot.container != client.player.getInventory() && slot.hasItem()) return true;
		}
		return false;
	}

	/** 解析当前打开的方块坐标。 */
	private BlockPos resolveOpenedBlock(Minecraft client) {
		if (lastClickedStorage != null && lastClickedAge <= CLICK_REMEMBER_TICKS
			&& StorageLabels.isStorageBlock(client.level, lastClickedStorage)) {
			return StorageLabels.canonicalPos(client.level, lastClickedStorage);
		}
		if (client.hitResult instanceof BlockHitResult hit
			&& StorageLabels.isStorageBlock(client.level, hit.getBlockPos())) {
			return StorageLabels.canonicalPos(client.level, hit.getBlockPos());
		}
		return null;
	}

	/** 把箱内物品记进仓库记录。 */
	private void recordSnapshot(Minecraft client, String title, AbstractContainerMenu menu) {
		Map<String, ItemTotal> totals = new LinkedHashMap<>();
		for (Slot slot : menu.slots) {
			if (slot.container == client.player.getInventory() || !slot.hasItem()) continue;
			ItemStack stack = slot.getItem();
			String id = BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
			ItemTotal total = totals.computeIfAbsent(id, ignored -> new ItemTotal(id, stack.getHoverName().getString()));
            var stored = stack.get(net.minecraft.core.component.DataComponents.STORED_ENCHANTMENTS);
            if (stored != null) for (var enchantment : stored.entrySet()) {
                total.searchTerms.add(net.minecraft.world.item.enchantment.Enchantment.getFullname(
                    enchantment.getKey(), enchantment.getIntValue()).getString());
                enchantment.getKey().unwrapKey().ifPresent(key -> total.searchTerms.add(key.identifier().getPath()));
            }
            total.count += stack.getCount();
		}

		List<ItemTotal> ordered = new ArrayList<>(totals.values());
		ordered.sort(Comparator.comparing(total -> total.id));
		StringBuilder fingerprint = new StringBuilder();
		for (ItemTotal total : ordered) fingerprint.append(total.id).append('/').append(total.name).append('=').append(total.count).append(total.searchTerms).append(';');
		if (fingerprint.toString().equals(lastFingerprint)) {
			KitConfig.StorageSnapshot labels = new KitConfig.StorageSnapshot();
			labels.dimension = openedDimension;
			labels.x = openedPosition.getX();
			labels.y = openedPosition.getY();
			labels.z = openedPosition.getZ();
			labels.title = title;
			labels.lastSeenEpochMillis = System.currentTimeMillis();
			StorageLabels.apply(client.level, openedPosition, labels);
            if(!StorageLifecycle.capture(client,openedPosition,labels))return;
			config.patchStorageLabels(labels);
			return;
		}
		lastFingerprint = fingerprint.toString();

		KitConfig.StorageSnapshot snapshot = new KitConfig.StorageSnapshot();
		snapshot.dimension = openedDimension;
		snapshot.x = openedPosition.getX();
		snapshot.y = openedPosition.getY();
		snapshot.z = openedPosition.getZ();
		snapshot.title = title;
		snapshot.lastSeenEpochMillis = System.currentTimeMillis();
		StorageLabels.apply(client.level, openedPosition, snapshot);
        if(!StorageLifecycle.capture(client,openedPosition,snapshot))return;
		for (ItemTotal total : ordered) {
			var item = new KitConfig.StoredItem(total.id, total.name, total.count);
            item.searchTerms = String.join(" ",total.searchTerms);
            snapshot.items.add(item);
		}
		config.upsertStorageSnapshot(snapshot);
	}

	/** 按标签从箱补到背包。 */
	private void attemptAutoRestock(Minecraft client, AbstractContainerMenu menu) {
		if (!ActivityRequirements.isActive(config)) return;
		if (pendingRequirement != null) {
			int after = ActivityRequirements.count(client.player, pendingRequirement);
			if (after > pendingBeforeCount) {
				client.gui.hud.setOverlayMessage(Component.literal("[自动补货] 已取出 " + pendingItemName).withColor(0x55FFFF), false);
				restockReported = false;
			} else {
				client.gui.hud.setOverlayMessage(Component.literal("[自动补货] 未能取出 " + pendingItemName + "，背包可能已满或服务器拒绝了操作").withColor(0xFF5555), false);
				takeCooldown = 20;
			}
			pendingRequirement = null;
			pendingItemName = "";
			return;
		}

		List<String> unavailable = new ArrayList<>();
		for (ActivityRequirements.Requirement requirement : ActivityRequirements.requirements(config)) {
			int current = ActivityRequirements.count(client.player, requirement);
			if (current >= requirement.target()) continue;
			Slot matchingSlot = findContainerSlot(client, menu, requirement);
			if (matchingSlot == null) {
				unavailable.add(requirement.label());
				continue;
			}

			pendingItemName = matchingSlot.getItem().getHoverName().getString();
			pendingRequirement = requirement;
			pendingBeforeCount = current;
			int menuSlotId = menu.slots.indexOf(matchingSlot);
			client.gameMode.handleContainerInput(menu.containerId, menuSlotId, 0, ContainerInput.QUICK_MOVE, client.player);
			takeCooldown = 10;
			return;
		}

		if (restockReported) return;
		restockReported = true;
		if (unavailable.isEmpty()) {
			client.player.sendSystemMessage(Component.literal("[自动补货] " + ActivityRequirements.selectedLabel(config) + "的物资已达到清单数量").withColor(0x55FF55));
		} else {
			client.player.sendSystemMessage(Component.literal("[自动补货] 当前箱子缺少：" + String.join("、", unavailable)).withColor(0xFFFF55));
		}
	}

	/** 找箱内匹配槽。 */
	private Slot findContainerSlot(Minecraft client, AbstractContainerMenu menu, ActivityRequirements.Requirement requirement) {
		for (Slot slot : menu.slots) {
			if (slot.container == client.player.getInventory() || !slot.hasItem()) continue;
			if (requirement.matches(slot.getItem())) return slot;
		}
		return null;
	}

	/** 清当前开箱跟踪。 */
	private void resetOpenContainer() {
		if (currentContainerId >= 0 && openedPosition != null) {
			// 快照每 10 tick 才记一次；关箱前最后几 tick 的取放在这里补记。
			Minecraft client = Minecraft.getInstance();
			if (contentsSeen && openedMenu != null && client.player != null && client.level != null) {
				recordSnapshot(client, openedTitle, openedMenu);
			}
			config.save();
		}
		openedMenu = null;
		openedTitle = "";
		contentsSeen = false;
		currentContainerId = -1;
		openedPosition = null;
		openedDimension = "";
		lastFingerprint = "";
		ticksInContainer = 0;
		takeCooldown = 0;
		restockReported = false;
		pendingRequirement = null;
		pendingBeforeCount = 0;
		pendingItemName = "";
	}

	private static final class ItemTotal {
		final String id;
		final String name;
        final java.util.Set<String> searchTerms = new java.util.TreeSet<>();
		int count;

		ItemTotal(String id, String name) {
			this.id = id;
			this.name = name;
		}
	}
}
