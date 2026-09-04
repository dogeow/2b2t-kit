package dev.twob2tkit.cruise;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 巡航到达、绕障等次要选项，不占首页。 */
public final class CruiseOptionsScreen extends KitHudScreen {
	private final KitConfig config;
	private EditBox arrivalRadius;
	private EditBox playerRadius;
	private EditBox minHealth;
	private EditBox stuckSeconds;
	private EditBox turnSpeed;
	private Checkbox disconnectOnArrival;
	private Checkbox obstacleAvoidance;
	private Checkbox clearCeiling;

	/** 打开巡航次要选项屏。 */
	public CruiseOptionsScreen(Screen parent, KitConfig config) {
		super(Component.literal("巡航选项"), parent);
		this.config = config;
	}

	@Override
	/** 到达半径、挂机保护、绕障与挖顶等控件。 */
	protected void init() {
		int left = panelLeft(340);
		int y = bodyTop(28);
		arrivalRadius = addRenderableWidget(KitUi.field(this.font, left, y, 78, "到达半径",
			KitUi.formatNumber(config.arrivalRadius), 8));
		playerRadius = addRenderableWidget(KitUi.field(this.font, left + 87, y, 78, "玩家警戒",
			KitUi.formatNumber(config.playerRadius), 8));
		minHealth = addRenderableWidget(KitUi.field(this.font, left + 174, y, 78, "最低心数",
			KitUi.formatNumber(config.minHealth / 2.0), 8));
		minHealth.setTooltip(Tooltip.create(Component.literal("按心填写。现在 4 就是半血。钓鱼/巡航等挂机时掉到这就下线。填 0 关闭。")));
		stuckSeconds = addRenderableWidget(KitUi.field(this.font, left + 261, y, 79, "卡住秒数",
			KitUi.formatNumber(config.stuckSeconds), 6));
		stuckSeconds.setTooltip(Tooltip.create(Component.literal(CruiseOptionTips.STUCK_SECONDS)));
		y += 28;
		turnSpeed = addRenderableWidget(KitUi.field(this.font, left, y, 78, "转向速度",
			KitUi.formatNumber(config.turnSpeed), 6));
		turnSpeed.setTooltip(Tooltip.create(Component.literal(CruiseOptionTips.TURN_SPEED)));
		arrivalRadius.setTooltip(Tooltip.create(Component.literal(CruiseOptionTips.ARRIVAL_RADIUS)));
		y += 28;
		disconnectOnArrival = addRenderableWidget(
			Checkbox.builder(Component.literal("到达后自动离线"), this.font)
				.pos(left, y)
				.selected(config.disconnectOnArrival)
				.build());
		obstacleAvoidance = addRenderableWidget(
			Checkbox.builder(Component.literal("前方障碍自动绕行"), this.font)
				.pos(left + 174, y)
				.selected(config.obstacleAvoidance)
				.build());
		obstacleAvoidance.setTooltip(Tooltip.create(Component.literal("贴身树叶或障碍先升高越过，远处再水平绕行。")));
		y += 22;
		clearCeiling = addRenderableWidget(
			Checkbox.builder(Component.literal("升空时挖掉头上方块"), this.font)
				.pos(left, y)
				.selected(config.clearCeiling)
				.build());
		clearCeiling.setTooltip(Tooltip.create(Component.literal("头顶挡住时垫脚挖开。基岩、箱子不挖。")));
		addRenderableWidget(Button.builder(Component.literal("保存"), button -> {
			if (save()) onClose();
		}).bounds(left, footerButtonY(), 166, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left + 174, footerButtonY(), 166, 20).build());
	}

	@Override
	/** 画分区标题与说明。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(340);
		KitUi.centered(graphics, this.font, "挂机保护（填 0 即关闭）", this.width / 2, headerY(12), 0x55FFFF);
		KitUi.text(graphics, this.font, "到达半径", left, bodyTop(18), 0xFFFFFF);
		KitUi.text(graphics, this.font, "玩家警戒", left + 87, bodyTop(18), 0xFFFFFF);
		KitUi.text(graphics, this.font, "最低心数", left + 174, bodyTop(18), 0xFFFFFF);
		KitUi.text(graphics, this.font, "卡住秒数", left + 261, bodyTop(18), 0xFFFFFF);
		if (!notice.isEmpty()) {
			KitUi.centered(graphics, this.font, notice, this.width / 2, footerNoticeY(), noticeColor);
		}
	}

	@Override
	/** 关屏前安静保存标志位。 */
	public void onClose() {
		saveQuietly();
		super.onClose();
	}

	/** 校验并保存全部字段；失败则提示。 */
	private boolean save() {
		try {
			config.arrivalRadius = KitUi.parse(arrivalRadius, "到达半径", 1.0, 128.0);
			config.playerRadius = KitUi.parse(playerRadius, "玩家警戒", 0.0, 256.0);
			config.minHealth = KitUi.parse(minHealth, "最低心数", 0.0, 10.0) * 2.0;
			config.stuckSeconds = (int)Math.round(KitUi.parse(stuckSeconds, "卡住秒数", 0.0, 600.0));
			config.turnSpeed = KitUi.parse(turnSpeed, "转向速度", 1.0, 120.0);
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return false;
		}
		saveFlags();
		config.save();
		showNotice("巡航选项已保存", 0x55FF55);
		return true;
	}

	/** 关屏时尽量保存，忽略非法数字。 */
	private void saveQuietly() {
		Double arrival = KitUi.tryParse(arrivalRadius, 1.0, 128.0);
		Double players = KitUi.tryParse(playerRadius, 0.0, 256.0);
		Double health = KitUi.tryParse(minHealth, 0.0, 10.0);
		Double stuck = KitUi.tryParse(stuckSeconds, 0.0, 600.0);
		if (arrival != null) config.arrivalRadius = arrival;
		if (players != null) config.playerRadius = players;
		if (health != null) config.minHealth = health * 2.0;
		if (stuck != null) config.stuckSeconds = (int)Math.round(stuck);
		Double turn = KitUi.tryParse(turnSpeed, 1.0, 120.0);
		if (turn != null) config.turnSpeed = turn;
		saveFlags();
		config.save();
	}

	/** 只写复选框类标志到配置。 */
	private void saveFlags() {
		config.disconnectOnArrival = disconnectOnArrival.selected();
		config.obstacleAvoidance = obstacleAvoidance.selected();
		config.clearCeiling = clearCeiling.selected();
	}
}
