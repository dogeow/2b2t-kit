package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.piglin.PiglinBrawler;
import dev.twob2tkit.piglin.PiglinBrawlerScreen;
import dev.twob2tkit.survival.SurvivalAlertsScreen;

/** 「保护」标签：自动保护、生存提醒、死亡点、白名单、打猪人与恶魂防护。 */
public final class GuardHomeScreen extends KitHudScreen {
	private final KitConfig config;
	private final KitController controller;
	/** 说明文字的起始 y，由 init 按最后一个按钮的底边算出，避免加按钮后压住按钮。 */
	private int infoY;

	GuardHomeScreen(KitConfig config, KitController controller) {
		super(Component.literal("保护"), null);
		this.config = config;
		this.controller = controller;
	}

	/** 固定为「保护」标签。 */
	@Override
	protected KitTab currentTab() {
		return KitTab.GUARD;
	}

	/** 布置保护相关开关与子页入口。 */
	@Override
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("GUARD", parent)) return;
		addTabBar(KitTab.GUARD);
		int left = panelLeft(320);
		int y = contentTop();
		addRenderableWidget(Button.builder(Component.literal(config.autoProtectOnHit
			? "自动保护：开" : "自动保护：关"), button -> {
			config.autoProtectOnHit = !config.autoProtectOnHit;
			config.save();
			rebuildWidgets();
		}).bounds(left, y, 320, 22)
			.tooltip(Tooltip.create(Component.literal(
				"遇怪或被打时打开 Meteor 杀戮光环和自动断开；盾构会开飞行飞到怪头顶再交给 KillAura。"
					+ "岩浆烫伤不算。不自己挥剑、不自己断线。")))
			.build());
		y += 28;
		addRenderableWidget(Button.builder(Component.literal("生存提醒"), button ->
			this.minecraft.setScreen(new SurvivalAlertsScreen(this, config)))
			.bounds(left, y, 155, 22).build());
		addRenderableWidget(Button.builder(Component.literal("最近死亡点"), button ->
			this.minecraft.setScreen(new DeathPointScreen(this, config, controller)))
			.bounds(left + 165, y, 155, 22).build());
		y += 28;
		addRenderableWidget(Button.builder(Component.literal("玩家白名单"), button ->
			this.minecraft.setScreen(new KitTrustedPlayersScreen(this, config)))
			.bounds(left, y, 320, 22).build());
		y += 28;
		PiglinBrawler brawler = KitClient.brawler();
		boolean brawling = brawler != null && brawler.isActive();
		addRenderableWidget(Button.builder(Component.literal(brawling ? "自动打猪人：开" : "自动打猪人：关"), button -> {
			PiglinBrawler current = KitClient.brawler();
			if (current == null) return;
			current.toggle(this.minecraft);
			if (current.isActive()) this.minecraft.setScreen(null);
			else rebuildWidgets();
		}).bounds(left, y, 155, 22)
			.tooltip(Tooltip.create(Component.literal(
				"下界刷经验用：近战砍够得着的猪人/僵尸猪人（拿弩的优先），恶魂火球自动瞄准反弹，"
					+ "背包有弓和箭会射远处的恶魂和弩猪人。不会自己跑动，只在飞行时左右拉扯躲弹。")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("打猪人设置"), button ->
			this.minecraft.setScreen(new PiglinBrawlerScreen(this, config)))
			.bounds(left + 165, y, 155, 22)
			.tooltip(Tooltip.create(Component.literal(
				"近战交给谁、各种射程、拉弓时长、低血量自动停手，都在这一页。")))
			.build());
		y += 28;
		addRenderableWidget(Button.builder(Component.literal(config.ghastGuardEnabled
			? "恶魂防护：开" : "恶魂防护：关"), button -> {
			config.ghastGuardEnabled = !config.ghastGuardEnabled;
			config.save();
			rebuildWidgets();
		}).bounds(left, y, 320, 22)
			.tooltip(Tooltip.create(Component.literal(
				"没开打猪人时也反弹来火球，空闲时拉弓射恶魂，不自己飞开。"
					+ "Meteor Arrow Dodge 勾了 all-projectiles 会把你推进柱子火里，想反弹就把那一项关掉。")))
			.build());
		y += 30;
		infoY = y;
		addRenderableWidget(Button.builder(Component.literal("关闭"), button -> this.minecraft.setScreen(null))
			.bounds(left, footerButtonY(), 320, 20).build());
	}

	/** 画挂机防护摘要与按键提示；矮窗则跳过以免压住关闭。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		int y = infoY;
		// 窗口太矮时宁可不画说明，也不要盖住底部的关闭按钮。
		if (y + 32 >= footerButtonY() - 4) return;
		KitUi.centered(graphics, this.font, "挂机防护、围箱和白名单", center, y, 0xA0A0A0);
		KitUi.centered(graphics, this.font,
			config.hasDeathPoint ? "已保存最近一次死亡坐标" : "还没有记录死亡坐标",
			center, y + 16, config.hasDeathPoint ? 0x55FF55 : 0xA0A0A0);
		KitUi.centered(graphics, this.font, KitKeys.hintEntry("围箱", KitKeys.TOGGLE_SURROUND)
			+ "  ·  " + KitKeys.hintEntry("紧急停止", KitKeys.EMERGENCY_STOP), center, y + 32, 0x55FFFF);
	}
}
