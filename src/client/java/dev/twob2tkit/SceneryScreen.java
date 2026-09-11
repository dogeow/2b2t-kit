package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Native Minecraft controls, kept separate from the saved point-to-point cruise destination. */
final class SceneryScreen extends KitHudScreen {
	private final KitConfig config;
	private EditBox radius;
	private Button start, resume, stop;
	SceneryScreen(Screen parent, KitConfig config) { super(Component.literal("风景预加载"), parent); this.config = config; }
	@Override protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("SCENERY", parent)) return;
		int width = Math.min(340, this.width - 24), left = panelLeft(width);
		String draft = radius == null ? Integer.toString(config.sceneryRadiusBlocks) : radius.getValue();
		label(left, 28, width, "以开始时的位置为圆心 · 半径单位：格", 0xFFFFFF);
		radius = addRenderableWidget(KitUi.field(font, left, 42, width, "半径", draft, 5));
		radius.setTooltip(Tooltip.create(Component.literal("16–4096 格。大半径耗时、磁盘占用更多；继续上次仍沿用原圆心和范围。")));
		int[] presets = {128, 256, 512, 1024}; int buttonW = (width - 18) / 4;
		for (int i = 0; i < presets.length; i++) {
			int value = presets[i];
			addRenderableWidget(Button.builder(Component.literal(value + " 格"), b -> radius.setValue(Integer.toString(value)))
				.bounds(left + i * (buttonW + 6), 68, buttonW, 20).build());
		}
		int row = footerButtonY() - 24, third = (width - 12) / 3;
		start = addRenderableWidget(Button.builder(Component.literal("当前位置新建"), b -> start(false)).bounds(left, row, third, 20)
			.tooltip(Tooltip.create(Component.literal("保存新圆心，替换上次风景任务；不改巡航坐标或挖矿工程。"))).build());
		resume = addRenderableWidget(Button.builder(Component.literal("继续上次"), b -> start(true)).bounds(left + third + 6, row, third, 20).build());
		stop = addRenderableWidget(Button.builder(Component.literal("停止并保留"), b -> {
			if (KitClient.borer() != null && KitClient.borer().isSceneryActive()) KitClient.borer().stop(minecraft, "手动暂停风景预加载，可继续上次");
		}).bounds(left + (third + 6) * 2, row, third, 20).build());
		addRenderableWidget(Button.builder(Component.literal(parent == null ? "关闭" : "返回"), b -> onClose()).bounds(left, footerButtonY(), width, 20).build());
		setInitialFocus(radius); tick();
	}
	@Override public void tick() {
		boolean active = KitClient.borer() != null && KitClient.borer().isSceneryActive();
		if (start != null) { start.active = !active; resume.active = !active; stop.active = active; }
	}
	private void start(boolean continuing) {
		int value = config.sceneryRadiusBlocks;
		if (!continuing) {
			try { value = Integer.parseInt(radius.getValue().trim()); }
			catch (NumberFormatException e) { showNotice("半径请输入 16–4096 的整数", 0xFF5555); return; }
			if (value < 16 || value > 4096) { showNotice("半径须为 16–4096 格", 0xFF5555); return; }
		}
		if (KitClient.startScenery(minecraft, value, continuing)) {
			if (!continuing) { config.sceneryRadiusBlocks = value; config.save(); }
			minecraft.setScreen(null);
		} else showNotice(KitClient.borer() == null ? "模块未就绪" : KitClient.borer().sceneryStatus(), 0xFF5555);
	}
	@Override protected boolean onEnterPressed() { if (KitClient.borer() != null && !KitClient.borer().isSceneryActive()) start(false); return true; }
	@Override public void extractRenderState(GuiGraphicsExtractor g, int mx, int my, float delta) {
		super.extractRenderState(g, mx, my, delta);
		KitUi.centered(g, font, "风景预加载 · 自动匹配缓存", this.width / 2, 12, 0xFFFFFF);
		int width = Math.min(340, this.width - 24), left = panelLeft(width);
		KitUi.text(g, font, "按服务端视距补漏 · 离地约 48 格 · 完成后返航", left, 94, 0xBBBBBB);
		String text = !notice.isEmpty() ? notice : KitClient.borer() == null ? "需要进入世界" : KitClient.borer().sceneryStatus();
		int y = Math.max(108, footerButtonY() - 50);
		for (String line : KitUi.wrap(font, text, width)) { if (y + 9 > footerButtonY() - 27) break; KitUi.text(g, font, line, left, y, notice.isEmpty() ? 0x55FFFF : noticeColor); y += 11; }
	}
}
