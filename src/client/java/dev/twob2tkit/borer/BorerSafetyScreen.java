package dev.twob2tkit.borer;

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

/** 盾构安全与回家选项，从主界面拆出以免和底栏重叠。 */
public final class BorerSafetyScreen extends KitHudScreen {
	private final KitConfig config;
	private final TunnelBorer borer;
	private EditBox mobRadius;
	private String draftMob = "";

	public BorerSafetyScreen(Screen parent, KitConfig config, TunnelBorer borer) {
		super(Component.literal("安全与回家"), parent);
		this.config = config;
		this.borer = borer;
	}

	@Override
	/** 经验/回家/封液/遇怪等安全开关。 */
	protected void init() {
		if (mobRadius != null) draftMob = mobRadius.getValue();
		int left = panelLeft(340);
		int y = bodyTop(36);

		checkbox(left, y, "煤经验", config.borerCoalXpMode, value -> config.borerCoalXpMode = value)
			.setTooltip(Tooltip.create(Component.literal("仍挖煤拿经验，但不捡煤。")));
		checkbox(left + 110, y, "石英经验", config.borerQuartzXpMode, value -> config.borerQuartzXpMode = value)
			.setTooltip(Tooltip.create(Component.literal("下界挖石英只拿经验不捡石英。")));
		checkbox(left + 230, y, "挖完回家", config.borerHomeOnDone, value -> config.borerHomeOnDone = value)
			.setTooltip(Tooltip.create(Component.literal("背包满或镐快坏时沿走过的路回家。")));
		y += 22;
		checkbox(left, y, "封水岩浆", config.borerSealLiquids, value -> config.borerSealLiquids = value);
		checkbox(left + 110, y, "遇岩浆拐弯", config.borerTurnAroundLava, value -> config.borerTurnAroundLava = value)
			.setTooltip(Tooltip.create(Component.literal("向前挖时提前看岩浆并左右转。关掉则走直线地铁。")));
		checkbox(left + 230, y, "遇怪躲开", config.borerPauseOnMob, value -> config.borerPauseOnMob = value);
		y += 22;
		checkbox(left, y, "副手举盾", config.borerShieldOnMob, value -> config.borerShieldOnMob = value);
		checkbox(left + 110, y, "苦力怕围箱", config.borerSurroundOnCreeper, value -> config.borerSurroundOnCreeper = value)
			.setTooltip(Tooltip.create(Component.literal("默认不围墙。勾选后苦力怕贴身才用围箱。")));
		mobRadius = addRenderableWidget(KitUi.field(this.font, left + 250, y, 90, "怪物距离",
			draftMob.isBlank() ? Integer.toString(config.borerMobRadius) : draftMob, 3));
		y += 28;

		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(this.width / 2 - 75, contentBottom(), 150, 20).build());
	}

	@Override
	/** 画标题与提示。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, "安全与回家", center, headerY(12), 0xFFFFFF);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, headerY(24), noticeColor);
	}

	@Override
	/** 关界面前保存字段。 */
	public void onClose() {
		saveFields();
		super.onClose();
	}

	/** 改勾选立即写入配置。 */
	private Checkbox checkbox(int x, int y, String text, boolean selected, java.util.function.Consumer<Boolean> setter) {
		return addRenderableWidget(Checkbox.builder(Component.literal(text), this.font)
			.pos(x, y)
			.selected(selected)
			.onValueChange((box, value) -> {
				setter.accept(value);
				config.save();
			})
			.build());
	}

	/** 保存怪物距离等输入框。 */
	private void saveFields() {
		try {
			if (mobRadius != null) config.borerMobRadius = KitUi.parseInt(mobRadius, "怪物距离", 2, 24);
			config.save();
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
		}
	}
}
