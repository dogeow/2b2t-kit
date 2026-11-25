package dev.twob2tkit;

import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.StringWidget;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.input.MouseButtonEvent;
import dev.twob2tkit.automation.AutomationBridge.TaskStartBlocked;
import net.minecraft.network.chat.Component;

/**
 * twob2tkit 界面基类：游戏内 HUD（不暂停）、热键、顶栏标签与底栏布局。
 */
public abstract class KitHudScreen extends Screen {
	@Override
	public void extractRenderState(net.minecraft.client.gui.GuiGraphicsExtractor g, int x, int y, float delta) {
		boolean compactColors = KitClient.config() != null && KitClient.config().clickGui;
		g.fill(0, 0, this.width, Math.max(0, this.height - 56), compactColors ? 0xEC192534 : 0xEC141D28);
		super.extractRenderState(g, x, y, delta);
	}
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
		this.minecraft.gui.setScreen(parent);
	}

    @Override
    public boolean mouseClicked(MouseButtonEvent event, boolean doubleClick) {
        try {
            return super.mouseClicked(event,doubleClick);
        } catch (TaskStartBlocked blocked) {
            showNotice(blocked.getMessage(),0xFF7777);
            return true;
        }
    }

	/** 处理紧急停止与功能热键；输入框聚焦时不关界面。 */
	@Override
	public boolean keyPressed(KeyEvent event) {
		if (KitKeys.matches(KitKeys.EMERGENCY_STOP, event)) {
			KitClient.emergencyStop("按下紧急停止键");
			this.minecraft.gui.setScreen(null);
			return true;
		}

		boolean typing = getFocused() instanceof EditBox box && box.canConsumeInput();
		if (!typing && KitKeys.matches(KitKeys.OPEN_GUI, event)) {
			this.minecraft.gui.setScreen(null);
			return true;
		}
		if (!typing) {
			for (net.minecraft.client.KeyMapping mapping : new net.minecraft.client.KeyMapping[]{
				KitKeys.START_STOP, KitKeys.TOGGLE_BORER, KitKeys.BORER_HOME, KitKeys.PORTAL_HOME,
				KitKeys.TOGGLE_SURROUND, KitKeys.TOGGLE_FEEDER, KitKeys.TOGGLE_PLANTER, KitKeys.TOGGLE_CHOPPER,
				KitKeys.TOGGLE_FISHER, KitKeys.TOGGLE_VILLAGER_SCAN}) {
				if (KitKeys.matches(mapping, event)) {
					showNotice("菜单内请用明确的操作按钮；返回游戏后快捷键照常", 0xFFFF55);
					return true;
				}
			}
		}
        try {
            if (!typing && event.isConfirmation() && onEnterPressed()) return true;
            return super.keyPressed(event);
        } catch (TaskStartBlocked blocked) {
            showNotice(blocked.getMessage(),0xFF7777);
            return true;
        }
	}

	/** 回车默认无操作；子类可覆盖做提交。 */
	protected boolean onEnterPressed() {
		return false;
	}

	/** 默认切换巡航；子类可覆盖。 */
	protected boolean onStartStopKey() {
		return false;
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

	/** A new explicit navigation/search action dismisses the previous contextual hint. */
	protected void clearNotice() { notice = ""; }

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

	/** 主内容区相对旧版统一下移，避免贴顶。 */
	private static final int CONTENT_DROP = 14;

	/** 子页内容区顶边。 */
	protected int bodyTop(int whenNested) {
		return whenNested + CONTENT_DROP;
	}

	/** 子页标题文字 Y。 */
	protected int headerY(int whenNested) {
		return whenNested + CONTENT_DROP;
	}

	/** 首行控件顶边。 */
	protected int contentTop() {
		return bodyTop(24);
	}
}
