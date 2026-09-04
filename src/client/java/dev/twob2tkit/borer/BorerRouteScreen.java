package dev.twob2tkit.borer;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 轴向瞄准与清空路点。 */
public final class BorerRouteScreen extends KitHudScreen {
	private final KitConfig config;
	private final TunnelBorer borer;
	private Button axisAimButton;
	private Button freeAimButton;

	public BorerRouteScreen(Screen parent, KitConfig config, TunnelBorer borer) {
		super(Component.literal("轴向瞄准"), parent);
		this.config = config;
		this.borer = borer;
	}

	@Override
	/** 清空路点与轴向/任意方向按钮。 */
	protected void init() {
		int left = panelLeft(340);
		int y = bodyTop(36);
		addRenderableWidget(Button.builder(Component.literal("清空路点"), button -> {
			if (borer == null) return;
			borer.clearTrailKeepPortal();
			showNotice("已清空回家路点", 0xFFFF55);
		}).bounds(left + 176, y, 164, 20).build());
		y += 28;
		axisAimButton = addRenderableWidget(Button.builder(Component.literal("轴向瞄准"), button -> {
			config.borerAxisAim = true;
			config.save();
			/** 当前瞄准模式对应按钮变灰。 */
			refreshAimButtons();
		}).bounds(left, y, 164, 20)
			.tooltip(Tooltip.create(Component.literal("只沿东西南北上下挖眼前 1×2。")))
			.build());
		freeAimButton = addRenderableWidget(Button.builder(Component.literal("任意方向"), button -> {
			config.borerAxisAim = false;
			config.save();
			/** 当前瞄准模式对应按钮变灰。 */
			refreshAimButtons();
		}).bounds(left + 176, y, 164, 20).build());
		refreshAimButtons();
		y += 28;
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(this.width / 2 - 75, y, 150, 20).build());
	}

	@Override
	/** 画标题与提示。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		KitUi.centered(graphics, this.font, "轴向瞄准", this.width / 2, headerY(12), 0xFFFFFF);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, this.width / 2, headerY(24), noticeColor);
	}

	/** 当前瞄准模式对应按钮变灰。 */
	private void refreshAimButtons() {
		if (axisAimButton != null) axisAimButton.active = !config.borerAxisAim;
		if (freeAimButton != null) freeAimButton.active = config.borerAxisAim;
	}
}
