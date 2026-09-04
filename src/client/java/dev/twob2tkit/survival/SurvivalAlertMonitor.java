package dev.twob2tkit.survival;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;

import java.util.EnumMap;
import java.util.Map;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.combat.HealingItems;

/** 生存库存提醒（食物、珍珠、金甲等）。 */
public final class SurvivalAlertMonitor {
	private enum AlertType {
		HEALING,
		NETHER_GOLD,
		TOTEM,
		ELYTRA
	}

	private final KitConfig config;
	private final Map<AlertType, AlertState> states = new EnumMap<>(AlertType.class);
	private int ticks;

	/** 按配置构造生存提醒监视。 */
	public SurvivalAlertMonitor(KitConfig config) {
		this.config = config;
		for (AlertType type : AlertType.values()) states.put(type, new AlertState());
	}

	/** 检查食物/珍珠等库存与金甲。 */
	public void tick(Minecraft client) {
		if (client.player == null || client.level == null) {
			reset();
			return;
		}
		if (++ticks % 20 != 0) return;

		LocalPlayer player = client.player;
		java.util.Set<String> selected = HealingItems.normalize(config.healingItemIds);
		int healingItems = HealingItems.count(player, selected);
		java.util.List<String> parts = HealingItems.breakdown(player, selected);
		String detail = parts.isEmpty() ? "未选择计入物品" : String.join(" ", parts);
		check(
			client,
			AlertType.HEALING,
			config.healingItemAlert && healingItems < config.minimumHealingItems,
			"回血不足：" + detail + "，合计 " + healingItems + " / 需要 " + config.minimumHealingItems
		);

		boolean inNetherWithoutGold = config.netherGoldArmorAlert
			&& client.level.dimension().equals(Level.NETHER)
			&& !hasGoldArmorEquipped(player);
		check(client, AlertType.NETHER_GOLD, inNetherWithoutGold, "你已进入下界，但没有穿戴任何金质护甲");

		int totems = countItem(player, Items.TOTEM_OF_UNDYING);
		check(
			client,
			AlertType.TOTEM,
			config.totemAlert && totems < config.minimumTotems,
			"不死图腾不足：当前 " + totems + "，建议至少携带 " + config.minimumTotems
		);

		ItemStack chest = player.getItemBySlot(EquipmentSlot.CHEST);
		int elytraRemaining = chest.is(Items.ELYTRA) ? chest.getMaxDamage() - chest.getDamageValue() : Integer.MAX_VALUE;
		check(
			client,
			AlertType.ELYTRA,
			config.elytraDurabilityAlert && chest.is(Items.ELYTRA) && elytraRemaining <= config.minimumElytraDurability,
			"鞘翅耐久过低：仅剩 " + elytraRemaining
		);
	}

	/** 单项不足则告警。 */
	private void check(Minecraft client, AlertType type, boolean triggered, String message) {
		AlertState state = states.get(type);
		if (!triggered) {
			state.active = false;
			state.lastAlertTick = Integer.MIN_VALUE;
			return;
		}

		int cooldownTicks = Math.max(5, config.survivalAlertCooldownSeconds) * 20;
		if (!state.active || ticks - state.lastAlertTick >= cooldownTicks) {
			alert(client, message);
			state.active = true;
			state.lastAlertTick = ticks;
		}
	}

	/** 统计背包某物品数量。 */
	private int countItem(LocalPlayer player, net.minecraft.world.item.Item item) {
		int count = 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (stack.is(item)) count += stack.getCount();
		}
		ItemStack offhand = player.getItemBySlot(EquipmentSlot.OFFHAND);
		if (offhand.is(item)) count += offhand.getCount();
		return count;
	}

	/** 是否穿了任意金质盔甲。 */
	private boolean hasGoldArmorEquipped(LocalPlayer player) {
		return player.getItemBySlot(EquipmentSlot.HEAD).is(Items.GOLDEN_HELMET)
			|| player.getItemBySlot(EquipmentSlot.CHEST).is(Items.GOLDEN_CHESTPLATE)
			|| player.getItemBySlot(EquipmentSlot.LEGS).is(Items.GOLDEN_LEGGINGS)
			|| player.getItemBySlot(EquipmentSlot.FEET).is(Items.GOLDEN_BOOTS);
	}

	/** 发冷却内不重复的提醒。 */
	private void alert(Minecraft client, String message) {
		Component text = Component.literal("[生存提醒] " + message).withColor(0xFF5555);
		client.player.sendSystemMessage(text);
		client.gui.setOverlayMessage(text, false);
		client.player.playSound(SoundEvents.PLAYER_LEVELUP, 0.8F, 1.0F);
	}

	/** 清告警冷却。 */
	private void reset() {
		ticks = 0;
		for (AlertState state : states.values()) {
			state.active = false;
			state.lastAlertTick = Integer.MIN_VALUE;
		}
	}

	private static final class AlertState {
		boolean active;
		int lastAlertTick = Integer.MIN_VALUE;
	}
}
