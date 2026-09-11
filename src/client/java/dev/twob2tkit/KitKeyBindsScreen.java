package dev.twob2tkit;

import com.mojang.blaze3d.platform.InputConstants;
import net.minecraft.ChatFormatting;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.network.chat.Component;
import org.jspecify.annotations.Nullable;

/** 按键绑定：点击捕获新键、单项/全部恢复默认。 */
final class KitKeyBindsScreen extends KitHudScreen {
	private static final int ROW_H = 24;

	private @Nullable KeyMapping selectedKey;
	private Button[] bindButtons;
	private Button[] resetButtons;
	private int listTop;
	private int listBottom;
	private int listScroll;
	private int listScrollMax;

	KitKeyBindsScreen(Screen parent) {
		super(Component.literal("twob2tkit 按键绑定"), parent);
	}

	/** 布置可滚动绑键列表与底栏按钮。 */
	@Override
	protected void init() {
		KitKeys.BindInfo[] infos = KitKeys.allInfos();
		var layout = UiPageLayout.of(width, height);
		int left = layout.left();
		listTop = 54;
		listBottom = footerNoticeY() - 8;
		int totalHeight = infos.length * ROW_H;
		int visibleHeight = Math.max(ROW_H, listBottom - listTop);
		listScrollMax = Math.max(0, totalHeight - visibleHeight);
		listScroll = Math.max(0, Math.min(listScroll, listScrollMax));

		bindButtons = new Button[infos.length];
		resetButtons = new Button[infos.length];
		for (int i = 0; i < infos.length; i++) {
			int y = listTop + i * ROW_H - listScroll;
			if (y < listTop || y + 20 > listBottom) continue;
			KeyMapping mapping = infos[i].mapping();
			bindButtons[i] = bindButton(left + layout.width() - 150, y, mapping);
			resetButtons[i] = addRenderableWidget(Button.builder(Component.literal("重置此项"),
				button -> reset(mapping))
				.bounds(left + layout.width() - 64, y, 64, 20).build());
		}
		addRenderableWidget(Button.builder(Component.literal("全部恢复默认"), button -> minecraft.setScreen(new KitConfirmScreen(this, "重置所有快捷键", "将所有工具箱快捷键恢复默认；其它模组的按键不变。", this::resetAll)))
			.bounds(layout.footerButtonX(0, 2), footerButtonY(), layout.footerButtonWidth(2), 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(layout.footerButtonX(1, 2), footerButtonY(), layout.footerButtonWidth(2), 20).build());
		refreshButtons();
	}

	/** 列表区内滚轮滚动绑键行。 */
	@Override
	public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
		if (mouseY >= listTop && mouseY < listBottom && listScrollMax > 0) {
			listScroll = Math.max(0, Math.min(listScrollMax, listScroll - (int)Math.round(scrollY * ROW_H)));
			rebuildWidgets();
			return true;
		}
		return super.mouseScrolled(mouseX, mouseY, scrollX, scrollY);
	}

	/** 画标题、说明与各行标签。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		var layout = UiPageLayout.of(width, height);
		int left = layout.left();
		int center = this.width / 2;
		KitKeys.BindInfo[] infos = KitKeys.allInfos();
		KitUi.centered(graphics, this.font, "按键绑定", center, 12, 0xFFFFFF);
		KitUi.centered(graphics, this.font, KitUi.fit(font, "点击按键后按新键；捕获时 Esc 解绑。同步到原版控制选项。", layout.width()), center, 34, 0xA0A0A0);
		for (int i = 0; i < infos.length; i++) {
			int y = listTop + i * ROW_H - listScroll;
			if (y < listTop || y + 20 > listBottom) continue;
			KitUi.text(graphics, this.font, KitUi.fit(font, infos[i].label(), layout.width() - 160), left, y + 5, 0xFFFFFF);
		}
		int hintY = footerNoticeY();
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, hintY - 12, noticeColor);
		KitUi.centered(graphics, this.font, KitUi.fit(font, "滚轮查看更多 · 菜单中保留紧急停止，功能启动使用明确按钮", layout.width()), center, hintY, 0xA0A0A0);
	}

	/** 捕获模式下写入新键或 Esc 解绑。 */
	@Override
	public boolean keyPressed(KeyEvent event) {
		if (selectedKey != null) {
			if (event.isEscape()) KitKeys.applyBinding(selectedKey, InputConstants.UNKNOWN, this.minecraft);
			else KitKeys.applyBinding(selectedKey, InputConstants.getKey(event), this.minecraft);
			selectedKey = null;
			KitKeys.suppressHotkeys = false;
			showNotice("按键已更新", 0x55FF55);
			refreshButtons();
			return true;
		}
		return super.keyPressed(event);
	}

	/** 捕获模式下绑定鼠标键。 */
	@Override
	public boolean mouseClicked(MouseButtonEvent event, boolean doubleClick) {
		if (selectedKey != null) {
			KitKeys.applyBinding(selectedKey, InputConstants.Type.MOUSE.getOrCreate(event.button()), this.minecraft);
			selectedKey = null;
			KitKeys.suppressHotkeys = false;
			showNotice("已绑定鼠标按键", 0x55FF55);
			refreshButtons();
			return true;
		}
		return super.mouseClicked(event, doubleClick);
	}

	/** 创建「当前键位」按钮并进入捕获。 */
	private Button bindButton(int x, int y, KeyMapping mapping) {
		return addRenderableWidget(Button.builder(mapping.getTranslatedKeyMessage(), button -> beginCapture(mapping))
			.bounds(x, y, 78, 20)
			.tooltip(Tooltip.create(Component.literal("点击后按下新的键盘或鼠标按键")))
			.build());
	}

	/** 离开时解除热键抑制。 */
	@Override
	public void removed() {
		KitKeys.suppressHotkeys = false;
		super.removed();
	}

	/** 进入捕获：抑制热键并高亮该行。 */
	private void beginCapture(KeyMapping mapping) {
		selectedKey = mapping;
		KitKeys.suppressHotkeys = true;
		showNotice("请按下新的按键，Esc 取消绑定", 0xFFFF55);
		refreshButtons();
	}

	/** 恢复单项默认。 */
	private void reset(KeyMapping mapping) {
		KitKeys.resetBinding(mapping, this.minecraft);
		if (selectedKey == mapping) {
			selectedKey = null;
			KitKeys.suppressHotkeys = false;
		}
		showNotice("已恢复默认：" + mapping.getTranslatedKeyMessage().getString(), 0x55FFFF);
		refreshButtons();
	}

	/** 恢复全部默认。 */
	private void resetAll() {
		for (KeyMapping mapping : KitKeys.all()) KitKeys.resetBinding(mapping, this.minecraft);
		selectedKey = null;
		KitKeys.suppressHotkeys = false;
		showNotice("已恢复全部默认按键", 0x55FFFF);
		refreshButtons();
	}

	/** 按绑定状态刷新按钮文案。 */
	private void refreshButtons() {
		KitKeys.BindInfo[] infos = KitKeys.allInfos();
		if (bindButtons == null) return;
		for (int i = 0; i < infos.length; i++) {
			if (bindButtons[i] != null) refresh(bindButtons[i], infos[i].mapping());
		}
	}

	/** 刷新单个绑键按钮（含捕获高亮）。 */
	private void refresh(Button button, KeyMapping mapping) {
		if (button == null) return;
		Component label = mapping.isUnbound()
			? Component.literal("未绑定").withStyle(ChatFormatting.GRAY)
			: mapping.getTranslatedKeyMessage();
		if (selectedKey == mapping) {
			button.setMessage(Component.literal("> ").append(label.copy().withStyle(ChatFormatting.UNDERLINE)).append(" <").withStyle(ChatFormatting.YELLOW));
		} else {
			button.setMessage(label);
		}
	}
}
