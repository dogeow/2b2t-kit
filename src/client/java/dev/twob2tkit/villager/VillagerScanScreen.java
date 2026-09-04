package dev.twob2tkit.villager;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 村庄职业扫描开关与摘要。 */
public final class VillagerScanScreen extends KitHudScreen {
	private final KitConfig config;

	/** 打开村民扫描设置屏。 */
	public VillagerScanScreen(Screen parent, KitConfig config) {
		super(Component.literal("村庄职业"), parent);
		this.config = config;
	}

	@Override
	/** 开关与说明按钮。 */
	protected void init() {
		int left = panelLeft(320);
		int y = bodyTop(32);
		VillagerScanner scanner = KitClient.villagerScanner();
		boolean on = scanner != null && scanner.isEnabled();
		addRenderableWidget(Button.builder(Component.literal(on ? "扫描：开（点击关闭）" : "扫描：关（点击开启）"), button -> {
			KitClient.toggleVillagerScan(this.minecraft);
			rebuildWidgets();
		}).bounds(left, y, 320, 22)
			.tooltip(Tooltip.create(Component.literal("村民头顶标职业；屏幕上方列出还缺的职业和工作方块")))
			.build());
		y += 28;
		addRenderableWidget(Button.builder(Component.literal("扫描范围 -"), button -> {
			config.villagerScanRange = Math.max(16, config.villagerScanRange - 8);
			config.save();
			rebuildWidgets();
		}).bounds(left, y, 72, 20).build());
		addRenderableWidget(Button.builder(Component.literal(config.villagerScanRange + " 格"), button -> {})
			.bounds(left + 76, y, 168, 20).build()).active = false;
		addRenderableWidget(Button.builder(Component.literal("扫描范围 +"), button -> {
			config.villagerScanRange = Math.min(96, config.villagerScanRange + 8);
			config.save();
			rebuildWidgets();
		}).bounds(left + 248, y, 72, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left, footerButtonY(), 320, 20).build());
	}

	@Override
	/** 画扫描摘要。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		VillagerScanner scanner = KitClient.villagerScanner();
		if (scanner == null || !scanner.isEnabled()) return;
		int center = this.width / 2;
		int maxW = Math.max(160, this.width - 48);
		int lineY = bodyTop(96);
		lineY = KitUi.centeredWrapped(graphics, this.font,
			KitUi.fit(this.font, scanner.summary(), maxW), center, lineY, 0xAAFFAA, maxW);
		if (!scanner.missingPairsText().isBlank()) {
			lineY = KitUi.centeredWrapped(graphics, this.font,
				"还缺：" + scanner.missingPairsText(), center, lineY + 2, 0xFFFF55, maxW);
		}
		if (!scanner.unemployedHintText().isBlank()) {
			KitUi.centeredWrapped(graphics, this.font, scanner.unemployedHintText(), center, lineY + 2, 0xFFCC66, maxW);
		}
	}
}
