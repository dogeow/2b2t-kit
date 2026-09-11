package dev.twob2tkit.piglin;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 自动打猪人的射程、拉弓时长和低血量阈值。 */
public final class PiglinBrawlerScreen extends KitHudScreen {
	private static final int ROW_ONE = 40;
	private static final int ROW_STEP = 40;

	private final KitConfig config;
	private EditBox meleeReach;
	private EditBox fireballReach;
	private EditBox ghastRange;
	private EditBox crossbowRange;
	private EditBox bowCharge;
	private EditBox minHealth;
	private EditBox hoverHeight;
	private EditBox lookSpeed;

	/** 打开打猪人设置屏。 */
	public PiglinBrawlerScreen(Screen parent, KitConfig config) {
		super(Component.literal("打猪人设置"), parent);
		this.config = config;
	}

	@Override
	/** 近战交给 Meteor、射程等选项。 */
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("BRAWLER", parent)) return;
		int left = panelLeft(340);
		int right = left + 176;
		int y = bodyTop(ROW_ONE);
		meleeReach = addRenderableWidget(KitUi.field(this.font, left, y, 140,
			"近战距离", KitUi.formatNumber(config.brawlerMeleeReach), 8));
		fireballReach = addRenderableWidget(KitUi.field(this.font, right, y, 140,
			"火球反弹距离", KitUi.formatNumber(config.brawlerFireballReach), 8));
		y += ROW_STEP;
		ghastRange = addRenderableWidget(KitUi.field(this.font, left, y, 140,
			"恶魂弓射程", KitUi.formatNumber(config.brawlerGhastRange), 8));
		crossbowRange = addRenderableWidget(KitUi.field(this.font, right, y, 140,
			"弩猪弓射程", KitUi.formatNumber(config.brawlerCrossbowRange), 8));
		y += ROW_STEP;
		bowCharge = addRenderableWidget(KitUi.field(this.font, left, y, 140,
			"拉弓 tick", Integer.toString(config.brawlerBowChargeTicks), 8));
		minHealth = addRenderableWidget(KitUi.field(this.font, right, y, 140,
			"最低血量", KitUi.formatNumber(config.brawlerMinHealth), 8));
		y += ROW_STEP;
		hoverHeight = addRenderableWidget(KitUi.field(this.font, left, y, 140,
			"悬停高度", KitUi.formatNumber(config.brawlerHoverHeight), 8));
		lookSpeed = addRenderableWidget(KitUi.field(this.font, right, y, 140,
			"跟踪°/tick", KitUi.formatNumber(config.brawlerLookDegreesPerTick), 8));
		y += 30;

		addRenderableWidget(Button.builder(Component.literal(config.brawlerMeleeEnabled
			? "近战：本模块自己砍" : "近战：交给 Meteor，只防空"), button -> {
			config.brawlerMeleeEnabled = !config.brawlerMeleeEnabled;
			config.save();
			rebuildWidgets();
		}).bounds(left, y, 168, 20)
			.tooltip(Tooltip.create(Component.literal(
				"开了 Meteor KillAura 就选「交给 Meteor」：本模块不再挥剑、不抢视角，"
					+ "免得两边互相重置攻击充能条。只保留反弹火球、自动弓箭和飞行拉扯，这些 KillAura 不会做。")))
			.build());
		addRenderableWidget(Button.builder(Component.literal(config.brawlerDeflectFireball
			? "恶魂火球：反弹" : "恶魂火球：交给 Meteor"), button -> {
			config.brawlerDeflectFireball = !config.brawlerDeflectFireball;
			config.save();
			rebuildWidgets();
		}).bounds(left + 172, y, 168, 20)
			.tooltip(Tooltip.create(Component.literal(
				"躲和反弹互斥，只能二选一。选「反弹」就要去 Meteor 的 Arrow Dodge 里把 all-projectiles 关掉，"
					+ "否则它每 tick 把你推离火球路径，你永远进不了反弹距离；箭仍然会被它躲开。"
					+ "选「交给 Meteor 躲」就要把 all-projectiles 打开。")))
			.build());
		y += 26;
		addRenderableWidget(Button.builder(Component.literal(config.brawlerStrafeDodge
			? "飞行拉扯：自己躲" : "飞行拉扯：交给 Meteor"), button -> {
			config.brawlerStrafeDodge = !config.brawlerStrafeDodge;
			config.save();
			rebuildWidgets();
		}).bounds(left, y, 168, 20)
			.tooltip(Tooltip.create(Component.literal(
				"拉弓对射时飞行左右横移躲弩箭。开了 Meteor 的 Arrow Dodge 就关掉这个，"
					+ "免得两边同时推你、互相抵消。反弹火球时本模块任何情况下都不会横移。")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("保存"), button -> save())
			.bounds(left, footerButtonY(), 110, 20).build());
		addRenderableWidget(Button.builder(Component.literal("恢复默认"), button -> restoreDefaults())
			.bounds(left + 116, footerButtonY(), 108, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left + 230, footerButtonY(), 110, 20).build());
	}

	@Override
	/** 回车保存。 */
	protected boolean onEnterPressed() {
		save();
		return true;
	}

	@Override
	/** 画状态。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(340);
		int right = left + 176;
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, "打猪人设置", center, headerY(10), 0xFFFFFF);
		KitUi.centered(graphics, this.font, "距离单位是格，改完记得点保存", center, headerY(24), 0xA0A0A0);
		int label = bodyTop(ROW_ONE) - 10;
		KitUi.text(graphics, this.font, "近战距离（原版 3）", left, label, 0xFFFFFF);
		KitUi.text(graphics, this.font, "火球反弹距离", right, label, 0xFFFFFF);
		KitUi.text(graphics, this.font, "恶魂弓射程", left, label + ROW_STEP, 0xFFFFFF);
		KitUi.text(graphics, this.font, "弩猪弓射程", right, label + ROW_STEP, 0xFFFFFF);
		KitUi.text(graphics, this.font, "拉弓 tick（满弓 20）", left, label + ROW_STEP * 2, 0xFFFFFF);
		KitUi.text(graphics, this.font, "低于这个血量停手（0=不停）", right, label + ROW_STEP * 2, 0xFFFFFF);
		KitUi.text(graphics, this.font, "悬停高度（0=不管）", left, label + ROW_STEP * 3, 0xFFFFFF);
		KitUi.text(graphics, this.font, "跟踪角速度（越小越稳）", right, label + ROW_STEP * 3, 0xFFFFFF);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
	}

	/** 写回配置。 */
	private void save() {
		try {
			double melee = KitUi.parse(meleeReach, "近战距离", 1.0, 6.0);
			double fireball = KitUi.parse(fireballReach, "火球反弹距离", 1.0, 6.0);
			double ghast = KitUi.parse(ghastRange, "恶魂弓射程", 8.0, 96.0);
			double crossbow = KitUi.parse(crossbowRange, "弩猪弓射程", 8.0, 96.0);
			double charge = KitUi.parse(bowCharge, "拉弓 tick", 5.0, 60.0);
			double health = KitUi.parse(minHealth, "最低血量", 0.0, 20.0);
			double hover = KitUi.parse(hoverHeight, "悬停高度", 0.0, 16.0);
			double look = KitUi.parse(lookSpeed, "跟踪角速度", 2.0, 30.0);
			config.brawlerMeleeReach = melee;
			config.brawlerFireballReach = fireball;
			config.brawlerGhastRange = ghast;
			config.brawlerCrossbowRange = crossbow;
			config.brawlerBowChargeTicks = (int)Math.round(charge);
			config.brawlerMinHealth = health;
			config.brawlerHoverHeight = hover;
			config.brawlerLookDegreesPerTick = look;
			config.save();
			showNotice("已保存", 0x55FF55);
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
		}
	}

	/** 恢复默认。 */
	private void restoreDefaults() {
		KitConfig defaults = new KitConfig();
		config.ghastGuardEnabled = defaults.ghastGuardEnabled;
		config.brawlerDeflectFireball = defaults.brawlerDeflectFireball;
		config.brawlerStrafeDodge = defaults.brawlerStrafeDodge;
		config.brawlerMeleeReach = defaults.brawlerMeleeReach;
		config.brawlerFireballReach = defaults.brawlerFireballReach;
		config.brawlerGhastRange = defaults.brawlerGhastRange;
		config.brawlerCrossbowRange = defaults.brawlerCrossbowRange;
		config.brawlerBowChargeTicks = defaults.brawlerBowChargeTicks;
		config.brawlerMinHealth = defaults.brawlerMinHealth;
		config.brawlerHoverHeight = defaults.brawlerHoverHeight;
		config.brawlerLookDegreesPerTick = defaults.brawlerLookDegreesPerTick;
		config.save();
		showNotice("已恢复默认值", 0x55FFFF);
		rebuildWidgets();
	}
}
