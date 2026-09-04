package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.core.Holder;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.item.enchantment.Enchantment;
import net.minecraft.world.item.enchantment.Enchantments;
import net.minecraft.world.item.enchantment.ItemEnchantments;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** 封路方块与找矿时要丢掉的废石。 */
public final class BorerItems {
	/** 封水/岩浆、铺路时优先用的方块。 */
	public static final Item[] SEAL_ITEMS = {
		Items.COBBLED_DEEPSLATE, Items.COBBLESTONE, Items.DEEPSLATE, Items.STONE,
		Items.TUFF, Items.ANDESITE, Items.DIORITE, Items.GRANITE, Items.NETHERRACK, Items.DIRT
	};

	/** 找矿模式会丢掉的普通石头类物品。 */
	public static final Item[] JUNK_STONE_ITEMS = {
		Items.COBBLESTONE, Items.STONE, Items.DEEPSLATE, Items.COBBLED_DEEPSLATE,
		Items.ANDESITE, Items.DIORITE, Items.GRANITE, Items.TUFF, Items.CALCITE,
		Items.SMOOTH_BASALT, Items.BASALT, Items.BLACKSTONE, Items.DIRT, Items.GRAVEL
	};

	/** 封路用石头每种至少留多少个。 */
	public static final int SEAL_STONE_RESERVE = 16;
	/** 圆石留一整组，铺路和封岩浆够用。 */
	public static final int COBBLESTONE_RESERVE = 64;
	/** 主背包空格还多于这个数时不扔废石。 */
	public static final int EMPTY_SLOTS_BEFORE_DISCARD = 3;

	/** 镐/铲再低就挖不动，该停机下线。 */
	public static final int MIN_TOOL_REMAINING = 8;

	private BorerItems() {
	}

	/** 是否为找矿时该丢掉的废石。 */
	public static boolean isJunkStone(Item item) {
		for (Item junk : JUNK_STONE_ITEMS) {
			if (item == junk) return true;
		}
		return false;
	}

	/** 是否为封路可用的方块物品。 */
	public static boolean isSealItem(Item item) {
		for (Item seal : SEAL_ITEMS) {
			if (item == seal) return true;
		}
		return false;
	}

	/** 扔废石时这种封路方块至少留多少。只留一组圆石；深板岩和圆石差不多，不另留。 */
	public static int sealReserve(Item item) {
		if (item == Items.COBBLESTONE) return COBBLESTONE_RESERVE;
		if (item == Items.DEEPSLATE || item == Items.COBBLED_DEEPSLATE) return 0;
		return isSealItem(item) ? SEAL_STONE_RESERVE : 0;
	}

	/**
	 * 副手 + 主背包 36 格（含快捷栏）。
	 * 26 的 {@code getNonEquipmentItems()} 可能不含热键栏，圆石只在快捷栏时会误报没封堵方块。
	 */
	public static int countItem(LocalPlayer player, Item item) {
		if (player == null || item == null) return 0;
		int offhand = player.getOffhandItem().is(item) ? player.getOffhandItem().getCount() : 0;
		Inventory inventory = player.getInventory();
		int[] slots = new int[36];
		for (int slot = 0; slot < 36; slot++) {
			ItemStack stack = inventory.getItem(slot);
			if (stack.is(item)) slots[slot] = stack.getCount();
		}
		return countMatchingSlots(offhand, slots);
	}

	/** 匹配物品占用格数。 */
	public static int countMatchingSlots(int offhandCount, int[] slotCounts) {
		int total = Math.max(0, offhandCount);
		if (slotCounts == null) return total;
		for (int count : slotCounts) {
			if (count > 0) total += count;
		}
		return total;
	}

	/** 主背包 36 格里还空着几格。 */
	public static int emptySlots(Inventory inventory) {
		int empty = 0;
		for (int slot = 0; slot < 36; slot++) {
			if (inventory.getItem(slot).isEmpty()) empty++;
		}
		return empty;
	}

	/** 是否镐/铲等挖矿工具。 */
	public static boolean isMiningTool(ItemStack stack) {
		return !stack.isEmpty() && (stack.is(ItemTags.PICKAXES) || stack.is(ItemTags.SHOVELS)
			|| stack.is(ItemTags.AXES) || stack.is(ItemTags.HOES));
	}

	/** 剩余耐久。 */
	public static int remainingDurability(ItemStack stack) {
		if (stack.isEmpty() || !stack.isDamageableItem()) return Integer.MAX_VALUE;
		return Math.max(0, stack.getMaxDamage() - stack.getDamageValue());
	}

	/** 是否快坏该换/停。 */
	public static boolean isTooWorn(ItemStack stack) {
		return !stack.isEmpty() && stack.isDamageableItem() && remainingDurability(stack) <= MIN_TOOL_REMAINING;
	}

	/** 附魔签名，用来区分同一把镐的效率/水下速掘等。 */
	public static String enchantSignature(ItemStack stack) {
		if (stack == null || stack.isEmpty()) return "";
		ItemEnchantments enchants = stack.getEnchantments();
		if (enchants.isEmpty()) return "";
		List<String> parts = new ArrayList<>();
		for (Holder<Enchantment> holder : enchants.keySet()) {
			int level = enchants.getLevel(holder);
			if (level <= 0) continue;
			String name = holder.unwrapKey().map(key -> key.identifier().getPath()).orElse("unknown");
			parts.add(name + ":" + level);
		}
		Collections.sort(parts);
		return String.join(",", parts);
	}

	/** 急迫等级。 */
	public static int hasteLevel(LocalPlayer player) {
		if (player == null) return 0;
		MobEffectInstance haste = player.getEffect(MobEffects.HASTE);
		return haste == null ? 0 : haste.getAmplifier() + 1;
	}

	/** 潮涌能量等级。 */
	public static int conduitLevel(LocalPlayer player) {
		if (player == null) return 0;
		MobEffectInstance conduit = player.getEffect(MobEffects.CONDUIT_POWER);
		return conduit == null ? 0 : conduit.getAmplifier() + 1;
	}

	/** 时运等级。没有该附魔则 0。无状态，热加载后两份类各算各的也没关系。 */
	public static int fortuneLevel(ItemStack stack) {
		if (stack.isEmpty()) return 0;
		ItemEnchantments enchants = stack.getEnchantments();
		for (Holder<Enchantment> holder : enchants.keySet()) {
			if (holder.is(Enchantments.FORTUNE)) return enchants.getLevel(holder);
		}
		return 0;
	}

	/** 被怪打时把最好的剑切到主手；主手已是剑就不动。true 表示主手现在有剑。 */
	public static boolean selectWeapon(Minecraft client, LocalPlayer player) {
		if (player == null || client.gameMode == null) return false;
		if (isSword(player.getMainHandItem())) return true;
		Inventory inventory = player.getInventory();
		int bestSlot = -1;
		int bestScore = 0;
		for (int slot = 0; slot < 36; slot++) {
			int score = swordScore(inventory.getItem(slot));
			if (score > bestScore) {
				bestScore = score;
				bestSlot = slot;
			}
		}
		if (bestSlot < 0) return false;
		if (bestSlot < 9) {
			inventory.setSelectedSlot(bestSlot);
			return true;
		}
		int dest = hotbarSlotForWeapon(inventory);
		inventory.setSelectedSlot(dest);
		client.gameMode.handleContainerInput(player.containerMenu.containerId, bestSlot, dest, ContainerInput.SWAP, player);
		return true;
	}

	/** 物品是否为剑。 */
	public static boolean isSword(ItemStack stack) {
		return !stack.isEmpty() && stack.is(ItemTags.SWORDS) && !isTooWorn(stack);
	}

	/** 剑品质分。 */
	private static int swordScore(ItemStack stack) {
		if (!isSword(stack)) return 0;
		Item item = stack.getItem();
		if (item == Items.NETHERITE_SWORD) return 6;
		if (item == Items.DIAMOND_SWORD) return 5;
		if (item == Items.IRON_SWORD) return 4;
		if (item == Items.STONE_SWORD) return 3;
		if (item == Items.GOLDEN_SWORD) return 2;
		return 1;
	}

	/** 从背包换剑出来时避开镐/铲所在格，优先用空格。 */
	private static int hotbarSlotForWeapon(Inventory inventory) {
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).isEmpty()) return slot;
		}
		for (int slot = 8; slot >= 0; slot--) {
			if (!isMiningTool(inventory.getItem(slot))) return slot;
		}
		return 8;
	}

	/** 包里有镐/铲，但全都快坏了。 */
	public static boolean allMiningToolsWorn(LocalPlayer player) {
		if (player == null) return false;
		boolean haveTool = false;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 36; slot++) {
			ItemStack stack = inventory.getItem(slot);
			if (!isMiningTool(stack)) continue;
			haveTool = true;
			if (!isTooWorn(stack)) return false;
		}
		if (isMiningTool(player.getOffhandItem())) {
			haveTool = true;
			if (!isTooWorn(player.getOffhandItem())) return false;
		}
		return haveTool;
	}
}
