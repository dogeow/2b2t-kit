package dev.twob2tkit.adventure;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;

import java.util.LinkedHashMap;
import java.util.Map;
import dev.twob2tkit.KitConfig;

/** 按清单与配方提示发冒险提醒。 */
public final class AdventureMonitor {
	private final KitConfig config;
	private boolean wasDead;
	private int ticks;
	private String lastActivityMissing = "";
	private int lastActivityAlertTick = Integer.MIN_VALUE;

	/** 按配置构造冒险/清单提醒。 */
	public AdventureMonitor(KitConfig config) {
		this.config = config;
	}

	/** 检查活动清单与配方提示。 */
	public void tick(Minecraft client) {
		if (client.player == null || client.level == null) {
			wasDead = false;
			return;
		}

		LocalPlayer player = client.player;
		boolean dead = player.isDeadOrDying();
		wasDead = dead;

		if (++ticks % 20 != 0 || dead) return;
		checkActivity(client, player);
		checkRecipeHints(client, player);
	}

	/** 清单物品不足则提醒。 */
	private void checkActivity(Minecraft client, LocalPlayer player) {
		ActivityRequirements.ensureLists(config);
		if (!ActivityRequirements.isActive(config)) {
			lastActivityMissing = "";
			return;
		}
		if (ActivityRequirements.isNetherProfile(config) && client.level != null && !client.level.dimension().equals(Level.NETHER)) {
			return;
		}

		String missing = ActivityRequirements.missingSummary(player, config);
		if (missing.isEmpty()) {
			lastActivityMissing = "";
			return;
		}
		int cooldown = Math.max(5, config.survivalAlertCooldownSeconds) * 20;
		if (!missing.equals(lastActivityMissing) || ticks - lastActivityAlertTick >= cooldown) {
			alert(client, ActivityRequirements.selectedLabel(config) + "缺少：" + missing, 0xFFFF55);
			lastActivityMissing = missing;
			lastActivityAlertTick = ticks;
		}
	}

	/** 新材料提示可做配方。 */
	private void checkRecipeHints(Minecraft client, LocalPlayer player) {
		if (!config.localRecipeHints) return;
		Map<String, String> hints = new LinkedHashMap<>();
		if (contains(player, stack -> stack.typeHolder().is(ItemTags.LOGS))) {
			hints.put("logs", "获得原木：1 原木可合成 4 木板；4 木板可合成工作台");
		}
		if (contains(player, stack -> stack.is(Items.COBBLESTONE))) {
			hints.put("cobblestone", "获得圆石：8 圆石围一圈可合成熔炉");
		}
		if (contains(player, stack -> stack.is(Items.FURNACE))) {
			hints.put("furnace", "拥有熔炉：熔炉放中央、上下左右各放 1 原木可合成烟熏炉");
		}
		if (contains(player, stack -> stack.is(Items.COAL) || stack.is(Items.CHARCOAL))) {
			hints.put("coal", "获得煤炭：煤炭放在木棍上方可合成 4 火把");
		}
		if (contains(player, stack -> stack.is(Items.IRON_INGOT))) {
			hints.put("iron", "获得铁锭：3 铁锭可合成铁镐或铁桶；配方指南中可查看摆放方式");
		}

		for (Map.Entry<String, String> hint : hints.entrySet()) {
			if (!config.seenRecipeHints.add(hint.getKey())) continue;
			config.save();
			alert(client, "配方提示：" + hint.getValue(), 0x55FFFF);
			break;
		}
	}

	/** 背包是否含某物品 id。 */
	private boolean contains(LocalPlayer player, java.util.function.Predicate<ItemStack> matcher) {
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (!stack.isEmpty() && matcher.test(stack)) return true;
		}
		return false;
	}

	/** 发提醒消息。 */
	private void alert(Minecraft client, String message, int color) {
		Component text = Component.literal("[冒险助手] " + message).withColor(color);
		client.player.sendSystemMessage(text);
		client.gui.setOverlayMessage(text, false);
		client.player.playSound(SoundEvents.PLAYER_LEVELUP, 0.8F, 1.0F);
	}
}
