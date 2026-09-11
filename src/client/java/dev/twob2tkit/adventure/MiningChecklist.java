package dev.twob2tkit.adventure;

import dev.twob2tkit.KitConfig;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;

/** Startup and changed-shortage reminders read the same editable MINING list as the activity guide. */
public final class MiningChecklist {
	private String previousMissing;
	private long lastReminder = Long.MIN_VALUE;
	private int checkTicks;
	public void beforeStart(Minecraft client, KitConfig config) {
		if (client.player == null || client.level == null) return;
		long now = client.level.getGameTime();
		if (lastReminder != Long.MIN_VALUE && now >= lastReminder && now - lastReminder < 60) return;
		ActivityRequirements.ensureLists(config);
		config.save();
		String missing = ActivityRequirements.miningMissingSummary(client.player, config);
		show(client, missing.isEmpty() ? "行动指南·出门挖矿：物资已齐。建议预留背包空位。"
			: "行动指南·出门挖矿，尚缺：" + missing + "。仅提醒，不阻止开挖；可在行动指南调整数量。");
		show(client, "水桶用于主世界应急；下界不能直接倒水。熔岩应急优先抗火药水；建议携带备用镐。区域挖会在井底暗处尝试补火把。" );
		if (config.borerAreaStoreDrops) show(client, "已开启区域自动存箱：请带普通箱子（建议至少 2 个）。箱子放在区域外侧；快满才卸货，箱满后另放备用箱。" );
		previousMissing = missing;
		lastReminder = now;
		checkTicks = 0;
	}
	public void tick(Minecraft client, KitConfig config, boolean active) {
		if (!active || client.player == null || client.level == null) { checkTicks = 0; return; }
		if (++checkTicks < 200) return;
		checkTicks = 0;
		String missing = ActivityRequirements.miningMissingSummary(client.player, config);
		if (!missing.equals(previousMissing)) {
			long now = client.level.getGameTime();
			if (!missing.isEmpty() && (lastReminder == Long.MIN_VALUE || now < lastReminder || now - lastReminder >= 1200)) {
				show(client, "挖矿物资变化，尚缺：" + missing);
				lastReminder = now;
				previousMissing = missing;
			} else if (missing.isEmpty()) previousMissing = missing;
		}
	}
	private static void show(Minecraft client, String message) {
		client.player.sendSystemMessage(Component.literal("[挖矿准备] " + message));
	}
}
