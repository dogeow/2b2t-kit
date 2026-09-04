package dev.twob2tkit;

import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.StringWidget;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.network.chat.Component;

/**
 * 2b2t-kit 界面基类：游戏内 HUD（不暂停）、热键、顶栏标签与底栏布局。
 */
public abstract class KitHudScreen extends Screen {
	/** 字段上方标签间距、行距、区块间距、状态行与底栏按钮间距。 */
	protected static final int LABEL_ABOVE_FIELD = 12;
	protected static final int CONTROL_ROW_STEP = 24;
	protected static final int SECTION_GAP = 10;
	protected static final int STATE_ABOVE_FOOTER = 14;
	protected static final int INLINE_LABEL_DY = 2;
	protected static final int FIELD_LABEL_X = 92;

	protected final Screen parent;
	protected String notice = "";
	protected int noticeColor = 0xA0A0A0;

	protected KitHudScreen(Component title, Screen parent) {
		super(title);
		this.parent = parent;
	}

	/** 不暂停游戏。 */
	@Override
	public boolean isPauseScreen() {
		return false;
	}

	/** 走游戏内 UI 层，原版 HUD 仍会画在最前。 */
	@Override
	public boolean isInGameUi() {
		return true;
	}

	/** 回到 parent；无 parent 则关屏。 */
	@Override
	public void onClose() {
		this.minecraft.setScreen(parent);
	}

	/** 处理紧急停止与功能热键；输入框聚焦时不关界面。 */
	@Override
	public boolean keyPressed(KeyEvent event) {
		if (KitKeys.matches(KitKeys.EMERGENCY_STOP, event)) {
			KitClient.emergencyStop("按下紧急停止键");
			this.minecraft.setScreen(null);
			return true;
		}

		boolean typing = getFocused() instanceof EditBox box && box.canConsumeInput();
		if (!typing && KitKeys.matches(KitKeys.OPEN_GUI, event)) {
			this.minecraft.setScreen(null);
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.START_STOP, event)) {
			return onStartStopKey();
		}
		if (!typing && KitKeys.matches(KitKeys.TOGGLE_BORER, event)) {
			KitClient.toggleBorer(this.minecraft);
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.BORER_HOME, event)) {
			KitClient.goBorerHome(this.minecraft);
			this.minecraft.setScreen(null);
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.PORTAL_HOME, event)) {
			KitClient.goNetherPortal(this.minecraft);
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.TOGGLE_SURROUND, event)) {
			KitClient.toggleSurround(this.minecraft);
			if (KitClient.surround() != null && KitClient.surround().isActive()) {
				this.minecraft.setScreen(null);
			}
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.TOGGLE_FEEDER, event)) {
			KitClient.toggleFeeder(this.minecraft);
			if (KitClient.feeder() != null && KitClient.feeder().isActive()) {
				this.minecraft.setScreen(null);
			}
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.TOGGLE_PLANTER, event)) {
			KitClient.togglePlanter(this.minecraft);
			if (KitClient.planter() != null && KitClient.planter().isActive()) {
				this.minecraft.setScreen(null);
			}
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.TOGGLE_CHOPPER, event)) {
			KitClient.toggleChopper(this.minecraft);
			if (KitClient.chopper() != null && KitClient.chopper().isActive()) {
				this.minecraft.setScreen(null);
			}
			return true;
		}
		if (!typing && KitKeys.matches(KitKeys.TOGGLE_FISHER, event)) {
			KitClient.toggleFisher(this.minecraft);
			if (KitClient.fisher() != null && KitClient.fisher().isActive()) {
				this.minecraft.setScreen(null);
			}
			return true;
		}
		if (!typing && event.isConfirmation() && onEnterPressed()) return true;
		return super.keyPressed(event);
	}

	/** 回车默认无操作；子类可覆盖做提交。 */
	protected boolean onEnterPressed() {
		return false;
	}

	/** 默认切换巡航；子类可覆盖。 */
	protected boolean onStartStopKey() {
		KitClient.toggleCruiseFromKey(this.minecraft);
		return true;
	}

	/** 加左对齐文字控件。 */
	protected StringWidget label(int x, int y, int width, String value, int color) {
		return addRenderableWidget(new StringWidget(x, y, width, 9, Component.literal(value).withColor(color), this.font));
	}

	/** 加水平居中文字控件。 */
	protected StringWidget centeredLabel(String value, int y, int color) {
		int textWidth = Math.max(1, this.font.width(value));
		return label(this.width / 2 - textWidth / 2, y, textWidth, value, color);
	}

	/** 设置底部提示文案与颜色。 */
	protected void showNotice(String text, int color) {
		notice = text;
		noticeColor = color;
	}

	/** 有 parent 时加「返回」。 */
	protected void addBackButton(int left, int y, int width) {
		if (parent == null) return;
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left, y, width, 20).build());
	}

	/** 给定面板宽时的左边缘（水平居中）。 */
	protected int panelLeft(int panelWidth) {
		return this.width / 2 - panelWidth / 2;
	}

	/** 内容区底边（底栏按钮之上）。 */
	protected int contentBottom() {
		return footerButtonY() - 4;
	}

	/**
	 * 本界面 {@link #isInGameUi()} 为真，原版血条/经验/快捷栏仍会画在最前。
	 * 快捷栏约在 height-22，血条约在 height-39；吸收心再高一排。
	 */
	protected int footerButtonY() {
		return this.height - 80;
	}

	/** 底栏提示文字 y。 */
	protected int footerNoticeY() {
		return footerButtonY() - 16;
	}

	/** 状态文字 baseline：底栏按钮顶边之上 {@link #STATE_ABOVE_FOOTER}，再留出 9px 字高。 */
	protected int stateRowAboveFooter() {
		return footerButtonY() - STATE_ABOVE_FOOTER - 9;
	}

	/** 由下方行推算带标签输入行的顶边。 */
	protected int labeledFieldRow(int rowBelow) {
		return rowBelow - LABEL_ABOVE_FIELD - CONTROL_ROW_STEP;
	}

	/** 当前顶栏标签；无标签的子页返回 null。 */
	protected KitTab currentTab() {
		return null;
	}

	/** 主内容区相对旧版统一下移，避免贴顶或与顶栏重叠。 */
	private static final int CONTENT_DROP = 14;

	/** 顶栏占位后的内容顶边。 */
	protected int tabContentTop() {
		int base = currentTab() == null ? 8 : (tabBarRows() > 1 ? 56 : 34);
		return base + CONTENT_DROP;
	}

	/** 有顶栏 tab 时内容区顶边；嵌套子页在 whenNested 上加 CONTENT_DROP。 */
	protected int bodyTop(int whenNested) {
		return currentTab() != null ? tabContentTop() + 8 : whenNested + CONTENT_DROP;
	}

	/** 标题文字 Y：有顶栏时紧贴内容区上方，嵌套子页用 whenNested。 */
	protected int headerY(int whenNested) {
		return currentTab() != null ? tabContentTop() + 2 : whenNested + CONTENT_DROP;
	}

	/** 首行控件顶边：顶栏页 tabContentTop+8，嵌套子页 bodyTop(24)。 */
	protected int contentTop() {
		return currentTab() != null ? tabContentTop() + 8 : bodyTop(24);
	}

	/** 标签过多时两行排布。 */
	protected int tabBarRows() {
		return KitTab.values().length > 7 ? 2 : 1;
	}

	/** 画顶栏标签按钮并切换页。 */
	protected void addTabBar(KitTab selected) {
		KitTab[] tabs = KitTab.values();
		int rows = tabBarRows();
		int cols = (tabs.length + rows - 1) / rows;
		int gap = 2;
		int avail = this.width - 12;
		int width = Math.max(40, Math.min(58, (avail - gap * (cols - 1)) / cols));
		int totalW = cols * width + (cols - 1) * gap;
		int x0 = panelLeft(totalW);
		for (int i = 0; i < tabs.length; i++) {
			KitTab tab = tabs[i];
			int row = i / cols;
			int col = i % cols;
			int x = x0 + col * (width + gap);
			int y = 8 + row * 22;
			Button button = addRenderableWidget(Button.builder(
				tab == selected
					? Component.literal("▸ ").withColor(0x55FF55).append(Component.literal(tab.label).withColor(0x55FF55))
					: Component.literal(tab.label),
				ignored -> {
					if (tab != selected) KitTab.open(this.minecraft, tab);
				}).bounds(x, y, width, 20).build());
			button.setTooltip(Tooltip.create(Component.literal(tab.tooltip())));
		}
	}
}
