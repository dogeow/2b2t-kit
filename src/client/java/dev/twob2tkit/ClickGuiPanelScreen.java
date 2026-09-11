package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.CharacterEvent;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import org.lwjgl.glfw.GLFW;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BooleanSupplier;
import java.util.function.Consumer;
import java.util.function.DoubleConsumer;
import java.util.function.DoubleSupplier;
import java.util.function.IntConsumer;
import java.util.function.IntSupplier;
import java.util.function.Supplier;

/**
 * Meteor 风格设置窗：紫标题、密排开关/滑条/选项。游戏里画的，不是原版按钮。
 */
final class ClickGuiPanelScreen extends KitHudScreen {
	private static final Map<String, int[]> POS = new HashMap<>();
	private static final Map<String, Boolean> SECTION = new HashMap<>();

	private final String heading;
	private final String description;
	private final List<Row> rows = new ArrayList<>();
	private BooleanSupplier active = () -> false;
	private Runnable toggleActive;
	private int winX;
	private int winY;
	private int winW = ClickGuiStyle.PANEL_W;
	private int winH;
	private int scroll;
	private int contentH;
	private boolean draggingWin;
	private int dragOx;
	private int dragOy;
	private SliderRow sliding;
	private EditRow editing;
	private EditBox valueEditor;
	private String hoverTip = "";
	private boolean embedded;
	private Font uiFont;

	ClickGuiPanelScreen(Screen parent, String heading, String description) {
		super(Component.literal(heading), parent);
		this.heading = heading;
		this.description = description == null ? "" : description;
	}

	/** 设底部「运行中」开关。 */
	ClickGuiPanelScreen active(BooleanSupplier active, Runnable toggle) {
		this.active = active;
		this.toggleActive = () -> {
			boolean wasActive = active.getAsBoolean();
			toggle.run();
			if (!wasActive && active.getAsBoolean()) Minecraft.getInstance().setScreen(null);
		};
		return this;
	}

	/** 加可折叠分区标题。 */
	ClickGuiPanelScreen section(String title) {
		rows.add(new SectionRow(title));
		return this;
	}

	/** 加布尔开关行。 */
	ClickGuiPanelScreen bool(String label, String tip, BooleanSupplier get, Consumer<Boolean> set) {
		rows.add(new BoolRow(label, tip, get, set));
		return this;
	}

	/** 加整数滑条。 */
	ClickGuiPanelScreen slider(String label, String tip, int min, int max, IntSupplier get, IntConsumer set) {
		rows.add(new SliderRow(label, tip, min, max, 1.0, () -> get.getAsInt(), v -> set.accept((int)Math.round(v))));
		return this;
	}

	/** 加浮点滑条。 */
	ClickGuiPanelScreen slider(String label, String tip, double min, double max, double step, DoubleSupplier get, DoubleConsumer set) {
		rows.add(new SliderRow(label, tip, min, max, step, get, set));
		return this;
	}

	/** 加循环选项行。 */
	ClickGuiPanelScreen cycle(String label, String tip, String[] options, IntSupplier get, IntConsumer set) {
		rows.add(new CycleRow(label, tip, options, get, set));
		return this;
	}

	/** 加点击动作行。 */
	ClickGuiPanelScreen action(String label, String tip, Runnable run) {
		rows.add(new ActionRow(label, tip, run));
		return this;
	}

	/** 加可编辑文本行。 */
	ClickGuiPanelScreen edit(String label, String tip, Supplier<String> get, Consumer<String> set) {
		rows.add(new EditRow(label, tip, get, set));
		return this;
	}

	/** 加多选文字 chip 行。 */
	ClickGuiPanelScreen chips(String tip, List<Chip> chips) {
		rows.add(new ChipRow(tip, chips));
		return this;
	}

	/** 加图标勾选行（默认可见）。 */
	ClickGuiPanelScreen icons(String tip, List<IconChip> icons) {
		return icons(tip, icons, () -> true);
	}

	/** 加图标勾选行，可按条件隐藏。 */
	ClickGuiPanelScreen icons(String tip, List<IconChip> icons, BooleanSupplier visible) {
		rows.add(new IconRow(tip, icons, visible));
		return this;
	}

	/** 加灰色说明行。 */
	ClickGuiPanelScreen note(String text) {
		rows.add(new NoteRow(text));
		return this;
	}

	/** 恢复窗口位置并布局。 */
	@Override
	protected void init() {
		if (!embedded) {
			int[] saved = POS.get(heading);
			if (saved != null) {
				winX = saved[0];
				winY = saved[1];
			} else {
				winX = Math.max(8, (this.width - winW) / 2);
				winY = Math.max(8, (this.height - 220) / 2);
			}
		}
		layout();
	}

	/** 嵌入模块栏时注入字体与尺寸。 */
	void attach(Font font, int width, int height) {
		this.uiFont = font;
		this.width = width;
		this.height = height;
		init();
	}

	/** 嵌入用字体或默认 font。 */
	private Font ui() {
		return uiFont != null ? uiFont : font;
	}

	/** 嵌进主窗指定矩形，无标题栏拖动。 */
	void embedIn(int x, int y, int w, int h) {
		embedded = true;
		winX = x;
		winY = y;
		winW = Math.max(120, w);
		winH = Math.max(80, h);
		layout();
	}

	/** 面板标题。 */
	String heading() {
		return heading;
	}

	/** 当前悬停提示。 */
	String hoverTip() {
		return notice.isEmpty() ? hoverTip : notice;
	}
	boolean editingValue() { return valueEditor != null; }

	/** 提交未完成的数值编辑。 */
	boolean finishEdits() {
		return commitEdit();
	}

	/** 计算内容高度、窗口高与滚动上限。 */
	private void layout() {
		contentH = 0;
		boolean skip = false;
		for (Row row : rows) {
			if (row instanceof SectionRow section) {
				contentH += row.height(ui(), winW);
				skip = !section.open();
				continue;
			}
			if (skip) continue;
			contentH += row.height(ui(), winW);
		}
		if (!description.isEmpty()) contentH += 20;
		int footer = toggleActive == null ? 4 : ClickGuiStyle.ROW + 4;
		int head = embedded ? 0 : ClickGuiStyle.HEAD;
		if (!embedded) {
			int maxH = Math.max(80, this.height - 28);
			winH = Math.min(maxH, head + contentH + footer);
			winX = Math.max(0, Math.min(winX, Math.max(0, this.width - winW)));
			winY = Math.max(0, Math.min(winY, Math.max(0, this.height - ClickGuiStyle.HEAD)));
		}
		int maxScroll = Math.max(0, contentH - (winH - head - footer));
		scroll = Math.max(0, Math.min(scroll, maxScroll));
	}

	/** 不画原版半透明遮罩。 */
	@Override
	public void extractTransparentBackground(GuiGraphicsExtractor graphics) {
	}

	/** 画独立设置窗内容与底栏运行开关。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		layout();
		int footer = toggleActive == null ? 4 : ClickGuiStyle.ROW + 4;
		int bodyTop = winY + ClickGuiStyle.HEAD;
		int bodyBot = winY + winH - footer;
		graphics.fill(winX, winY, winX + winW, winY + winH, ClickGuiStyle.COL_BG);
		graphics.fill(winX, winY, winX + winW, bodyTop, ClickGuiStyle.COL_HEADER);
		KitUi.centered(graphics, ui(), heading, winX + winW / 2, winY + 4, ClickGuiStyle.COL_TEXT);
		KitUi.text(graphics, ui(), "x", winX + winW - 10, winY + 4, ClickGuiStyle.COL_TEXT);

		hoverTip = "";
		int y = bodyTop - scroll;
		if (!description.isEmpty()) {
			if (y + 18 > bodyTop && y < bodyBot) {
				KitUi.text(graphics, ui(),
					KitUi.fit(ui(), description, winW - 10), winX + 5, y + 4, ClickGuiStyle.COL_MUTED);
			}
			y += 20;
		}
		boolean skip = false;
		for (Row row : rows) {
			if (row instanceof SectionRow section) {
				int h = row.height(ui(), winW);
				if (y + h > bodyTop && y < bodyBot) {
					row.render(graphics, ui(), winX, y, winW, mouseX, mouseY);
				}
				y += h;
				skip = !section.open();
				continue;
			}
			if (skip) continue;
			int h = row.height(ui(), winW);
			if (y + h > bodyTop && y < bodyBot) {
				row.render(graphics, ui(), winX, y, winW, mouseX, mouseY);
				if (mouseX >= winX && mouseX < winX + winW && mouseY >= Math.max(y, bodyTop) && mouseY < Math.min(y + h, bodyBot)) {
					String at = row.tipAt(mouseX, mouseY, winX, y, winW);
					if (!at.isEmpty()) hoverTip = at;
				}
			}
			y += h;
		}

		if (toggleActive != null) {
			int fy = winY + winH - footer;
			graphics.fill(winX, fy, winX + winW, winY + winH, ClickGuiStyle.COL_ROW);
			boolean on = active.getAsBoolean();
			KitUi.text(graphics, ui(), on ? "■ 停止此功能" : "▶ 开始此功能", winX + 6, fy + 6, ClickGuiStyle.COL_TEXT);
			drawCheck(graphics, winX + winW - 16, fy + 4, on);
		}
		renderValueEditor(graphics, mouseX, mouseY, delta);
		String hint = hoverTip.isEmpty() ? "Esc 返回模块栏  ·  拖标题栏  ·  点数值可输入" : hoverTip;
		int boxW = Math.min(this.width - 12, Math.max(200, ui().width(hint) + 12));
		graphics.fill((this.width - boxW) / 2, this.height - 16, (this.width + boxW) / 2, this.height, 0xC0000000);
		KitUi.centered(graphics, ui(), KitUi.fit(ui(), hint, boxW - 8), this.width / 2, this.height - 14, 0xDDDDDD);
		if (!notice.isEmpty()) {
			KitUi.centered(graphics, ui(), notice, this.width / 2, this.height - 28, noticeColor);
		}
	}

	/** 画嵌在模块栏内的内容（无外框标题）。 */
	void drawEmbedded(GuiGraphicsExtractor graphics, int mouseX, int mouseY) {
		layout();
		int footer = toggleActive == null ? 4 : ClickGuiStyle.ROW + 4;
		int bodyTop = winY;
		int bodyBot = winY + winH - footer;
		hoverTip = "";
		int y = bodyTop - scroll;
		if (!description.isEmpty()) {
			if (y + 18 > bodyTop && y < bodyBot) {
				KitUi.text(graphics, ui(),
					KitUi.fit(ui(), description, winW - 10), winX + 5, y + 4, ClickGuiStyle.COL_MUTED);
			}
			y += 20;
		}
		boolean skip = false;
		for (Row row : rows) {
			if (row instanceof SectionRow section) {
				int h = row.height(ui(), winW);
				if (y + h > bodyTop && y < bodyBot) {
					row.render(graphics, ui(), winX, y, winW, mouseX, mouseY);
				}
				y += h;
				skip = !section.open();
				continue;
			}
			if (skip) continue;
			int h = row.height(ui(), winW);
			if (y + h > bodyTop && y < bodyBot) {
				row.render(graphics, ui(), winX, y, winW, mouseX, mouseY);
				if (mouseX >= winX && mouseX < winX + winW && mouseY >= Math.max(y, bodyTop) && mouseY < Math.min(y + h, bodyBot)) {
					String at = row.tipAt(mouseX, mouseY, winX, y, winW);
					if (!at.isEmpty()) hoverTip = at;
				}
			}
			y += h;
		}
		if (toggleActive != null) {
			int fy = winY + winH - footer;
			graphics.fill(winX, fy, winX + winW, winY + winH, ClickGuiStyle.COL_ROW);
			boolean on = active.getAsBoolean();
			KitUi.text(graphics, ui(), on ? "■ 停止此功能" : "▶ 开始此功能", winX + 6, fy + 6, ClickGuiStyle.COL_TEXT);
			drawCheck(graphics, winX + winW - 16, fy + 4, on);
		}
		renderValueEditor(graphics, mouseX, mouseY, 0);
	}

	/** 嵌入模式下的点击。 */
	boolean mouseClickedEmbedded(MouseButtonEvent event) {
		int mx = (int)event.x();
		int my = (int)event.y();
		if (valueEditor != null && valueEditor.mouseClicked(event, false)) return true;
		if (!hitWindow(mx, my)) {
			if (editing != null && !commitEdit()) return true;
			return false;
		}
		int footer = toggleActive == null ? 4 : ClickGuiStyle.ROW + 4;
		if (toggleActive != null && my >= winY + winH - footer) {
			if (event.button() == 0 && commitEdit()) toggleActive.run();
			return true;
		}
		int bodyTop = winY;
		int y = bodyTop - scroll;
		if (!description.isEmpty()) y += 20;
		boolean skip = false;
		for (Row row : rows) {
			if (row instanceof SectionRow section) {
				int h = row.height(ui(), winW);
				if (my >= y && my < y + h && my >= bodyTop && my < winY + winH - footer) {
					if (editing != null) commitEdit();
					row.click(mx, my, event.button(), winX, y, winW, this);
					layout();
					return true;
				}
				y += h;
				skip = !section.open();
				continue;
			}
			if (skip) continue;
			int h = row.height(ui(), winW);
			if (my >= y && my < y + h && my >= bodyTop && my < winY + winH - footer) {
				if (editing != null && row != editing && !commitEdit()) return true;
				row.click(mx, my, event.button(), winX, y, winW, this);
				layout();
				return true;
			}
			y += h;
		}
		if (editing != null) commitEdit();
		return true;
	}

	/** 嵌入模式下拖滑条。 */
	boolean mouseDraggedEmbedded(MouseButtonEvent event) {
		if (sliding != null && event.button() == 0) {
			sliding.applyMouse((int)event.x(), winX, winW);
			return true;
		}
		return false;
	}

	/** 嵌入模式下松开滑条。 */
	void mouseReleasedEmbedded() {
		sliding = null;
	}

	/** 嵌入模式下滚动内容。 */
	boolean mouseScrolledEmbedded(double scrollY) {
		scroll -= (int)Math.round(scrollY * 14);
		layout();
		return true;
	}

	/** 嵌入模式下编辑框按键。 */
	boolean keyPressedEmbedded(KeyEvent event) {
		if (valueEditor != null) {
			if (event.key() == GLFW.GLFW_KEY_ESCAPE) {
				cancelEdit();
				return true;
			}
			if (event.isConfirmation()) {
				commitEdit();
				return true;
			}
			return valueEditor.keyPressed(event);
		}
		return false;
	}

	/** 嵌入模式下编辑框输入。 */
	boolean charTypedEmbedded(CharacterEvent event) {
		if (valueEditor != null) {
			return valueEditor.charTyped(event);
		}
		return false;
	}

	/** 独立窗：拖标题、关窗、点行。 */
	@Override
	public boolean mouseClicked(MouseButtonEvent event, boolean doubleClick) {
		int mx = (int)event.x();
		int my = (int)event.y();
		if (valueEditor != null && valueEditor.mouseClicked(event, doubleClick)) return true;
		if (editing != null && !hitWindow(mx, my)) {
			commitEdit();
		}
		if (!hitWindow(mx, my)) return super.mouseClicked(event, doubleClick);
		if (my < winY + ClickGuiStyle.HEAD) {
			if (mx >= winX + winW - 14) {
				onClose();
				return true;
			}
			if (event.button() == 0) {
				draggingWin = true;
				dragOx = mx - winX;
				dragOy = my - winY;
				setDragging(true);
			}
			return true;
		}
		int footer = toggleActive == null ? 4 : ClickGuiStyle.ROW + 4;
		if (toggleActive != null && my >= winY + winH - footer) {
			if (event.button() == 0 && commitEdit()) toggleActive.run();
			return true;
		}
		int bodyTop = winY + ClickGuiStyle.HEAD;
		int y = bodyTop - scroll;
		if (!description.isEmpty()) y += 20;
		boolean skip = false;
		for (Row row : rows) {
			if (row instanceof SectionRow section) {
				int h = row.height(ui(), winW);
				if (my >= y && my < y + h && my >= bodyTop && my < winY + winH - footer) {
					if (editing != null) commitEdit();
					row.click(mx, my, event.button(), winX, y, winW, this);
					layout();
					return true;
				}
				y += h;
				skip = !section.open();
				continue;
			}
			if (skip) {
				continue;
			}
			int h = row.height(ui(), winW);
			if (my >= y && my < y + h && my >= bodyTop && my < winY + winH - footer) {
				if (editing != null && row != editing) commitEdit();
				row.click(mx, my, event.button(), winX, y, winW, this);
				layout();
				return true;
			}
			y += h;
		}
		if (editing != null) commitEdit();
		return true;
	}

	/** 拖窗口或滑条。 */
	@Override
	public boolean mouseDragged(MouseButtonEvent event, double dx, double dy) {
		if (draggingWin && event.button() == 0) {
			winX = (int)event.x() - dragOx;
			winY = (int)event.y() - dragOy;
			layout();
			POS.put(heading, new int[]{winX, winY});
			return true;
		}
		if (sliding != null && event.button() == 0) {
			sliding.applyMouse((int)event.x(), winX, winW);
			return true;
		}
		return super.mouseDragged(event, dx, dy);
	}

	/** 结束拖窗/滑条并记住位置。 */
	@Override
	public boolean mouseReleased(MouseButtonEvent event) {
		if (event.button() == 0) {
			draggingWin = false;
			sliding = null;
			setDragging(false);
			POS.put(heading, new int[]{winX, winY});
		}
		return super.mouseReleased(event);
	}

	/** 窗内滚内容。 */
	@Override
	public boolean mouseScrolled(double x, double y, double scrollX, double scrollY) {
		if (hitWindow((int)x, (int)y)) {
			scroll -= (int)Math.round(scrollY * 14);
			layout();
			return true;
		}
		return super.mouseScrolled(x, y, scrollX, scrollY);
	}

	/** 编辑中 Esc 取消、回车提交。 */
	@Override
	public boolean keyPressed(KeyEvent event) {
		if (KitKeys.matches(KitKeys.EMERGENCY_STOP, event)) { cancelEdit(); return super.keyPressed(event); }
		if (valueEditor != null) {
			if (event.key() == GLFW.GLFW_KEY_ESCAPE) {
				cancelEdit();
				return true;
			}
			if (event.isConfirmation()) {
				commitEdit();
				return true;
			}
			return valueEditor.keyPressed(event);
		}
		return super.keyPressed(event);
	}

	/** 把字符交给数值编辑框。 */
	@Override
	public boolean charTyped(CharacterEvent event) {
		if (valueEditor != null) {
			return valueEditor.charTyped(event);
		}
		return super.charTyped(event);
	}

	/** 点是否在窗矩形内。 */
	private boolean hitWindow(int mx, int my) {
		return mx >= winX && mx < winX + winW && my >= winY && my < winY + winH;
	}

	/** 提交数值编辑。 */
	private boolean commitEdit() {
		if (editing != null && valueEditor != null) {
			try { editing.commitValue(valueEditor.getValue()); }
			catch (IllegalArgumentException error) { showNotice(error instanceof NumberFormatException ? "请输入有效数字" : error.getMessage(), 0xFF7777); return false; }
		}
		closeEdit();
		notice = "";
		return true;
	}

	/** 取消数值编辑。 */
	private void cancelEdit() {
		notice = "";
		closeEdit();
	}
	@Override public void onClose() { if (commitEdit()) super.onClose(); }

	/** 关掉编辑框并恢复热键。 */
	private void closeEdit() {
		valueEditor = null;
		if (editing != null) {
			editing.unfocus();
			editing = null;
		}
		KitKeys.suppressHotkeys = false;
	}

	/** 开始编辑某一文本行。 */
	void beginValueEdit(EditRow row, int boxX, int rowY, int boxW) {
		if (!commitEdit()) return;
		editing = row;
		row.focused = true;
		String seed = row.readValue();
		valueEditor = new EditBox(ui(), boxX, rowY + 2, boxW, 16, Component.empty());
		valueEditor.setMaxLength(256);
		valueEditor.setValue(seed);
		valueEditor.setFocused(true);
		valueEditor.setBordered(false);
		valueEditor.setTextColor(ClickGuiStyle.COL_TEXT);
		KitKeys.suppressHotkeys = true;
		syncValueEditorPosition();
	}

	/** 滚动后同步编辑框位置。 */
	private void syncValueEditorPosition() {
		if (valueEditor == null || editing == null) return;
		int[] geom = findEditRowGeometry();
		if (geom == null) {
			commitEdit();
			return;
		}
		valueEditor.setX(geom[0]);
		valueEditor.setY(geom[1]);
		valueEditor.setWidth(geom[2]);
	}

	/** 找当前编辑行的输入框几何。 */
	private int[] findEditRowGeometry() {
		int footer = toggleActive == null ? 4 : ClickGuiStyle.ROW + 4;
		int bodyTop = embedded ? winY : winY + ClickGuiStyle.HEAD;
		int y = bodyTop - scroll;
		if (!description.isEmpty()) y += 20;
		boolean skip = false;
		for (Row row : rows) {
			if (row instanceof SectionRow section) {
				y += row.height(ui(), winW);
				skip = !section.open();
				continue;
			}
			if (skip) continue;
			int h = row.height(ui(), winW);
			if (row == editing) {
				return new int[]{winX + 78, y + 2, winW - 86};
			}
			y += h;
		}
		return null;
	}

	/** 画叠加的 EditBox。 */
	private void renderValueEditor(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		if (valueEditor == null) return;
		syncValueEditorPosition();
		valueEditor.extractWidgetRenderState(graphics, mouseX, mouseY, delta);
	}

	/** 画小方格勾选。 */
	static void drawCheck(GuiGraphicsExtractor graphics, int x, int y, boolean on) {
		graphics.fill(x, y, x + 8, y + 8, 0xFF000000);
		graphics.fill(x + 1, y + 1, x + 7, y + 7, on ? ClickGuiStyle.COL_ACCENT : ClickGuiStyle.COL_BOX);
	}

	/** 文字多选芯片。 */
	public record Chip(String label, BooleanSupplier on, Runnable toggle) {
	}

	/** 物品图标勾选。 */
	public record IconChip(ItemStack stack, String tip, BooleanSupplier on, Runnable toggle) {
	}

	/** 设置行：高度、绘制、点击。 */
	private interface Row {
		int height(Font font, int width);

		void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY);

		void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen);

		default String tip() {
			return "";
		}

		default String tipAt(int mx, int my, int x, int y, int w) {
			return tip();
		}
	}

	/** 可折叠分区头。 */
	private final class SectionRow implements Row {
		private final String title;

		SectionRow(String title) {
			this.title = title;
		}

		boolean open() {
			return SECTION.getOrDefault(heading + "/" + title, true);
		}

		@Override
		public int height(Font font, int width) {
			return ClickGuiStyle.ROW;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			boolean over = mouseX >= x && mouseX < x + w && mouseY >= y && mouseY < y + ClickGuiStyle.ROW;
			graphics.fill(x, y, x + w, y + ClickGuiStyle.ROW, over ? ClickGuiStyle.COL_HOVER : 0xE0241828);
			KitUi.text(graphics, font, (open() ? "▼ " : "▶ ") + title, x + 4, y + 4, ClickGuiStyle.COL_TEXT);
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			SECTION.put(heading + "/" + title, !open());
		}
	}

	/** 布尔开关行。 */
	private final class BoolRow implements Row {
		private final String label;
		private final String tip;
		private final BooleanSupplier get;
		private final Consumer<Boolean> set;

		BoolRow(String label, String tip, BooleanSupplier get, Consumer<Boolean> set) {
			this.label = label;
			this.tip = tip;
			this.get = get;
			this.set = set;
		}

		@Override
		public int height(Font font, int width) {
			return ClickGuiStyle.ROW;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			boolean over = mouseX >= x && mouseX < x + w && mouseY >= y && mouseY < y + ClickGuiStyle.ROW;
			boolean on = get.getAsBoolean();
			graphics.fill(x, y, x + w, y + ClickGuiStyle.ROW, over ? ClickGuiStyle.COL_HOVER : ClickGuiStyle.COL_ROW);
			KitUi.text(graphics, font, KitUi.fit(font, label, w - 24), x + 5, y + 4, ClickGuiStyle.COL_TEXT);
			drawCheck(graphics, x + w - 16, y + 4, on);
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			if (button != 0) return;
			set.accept(!get.getAsBoolean());
		}

		@Override
		public String tip() {
			return tip;
		}
	}

	/** 滑条行。 */
	private final class SliderRow implements Row {
		private final String label;
		private final String tip;
		private final double min;
		private final double max;
		private final double step;
		private final DoubleSupplier get;
		private final DoubleConsumer set;

		SliderRow(String label, String tip, double min, double max, double step, DoubleSupplier get, DoubleConsumer set) {
			this.label = label;
			this.tip = tip;
			this.min = min;
			this.max = max;
			this.step = step <= 0 ? 1 : step;
			this.get = get;
			this.set = set;
		}

		@Override
		public int height(Font font, int width) {
			return ClickGuiStyle.ROW;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			boolean over = mouseX >= x && mouseX < x + w && mouseY >= y && mouseY < y + ClickGuiStyle.ROW;
			graphics.fill(x, y, x + w, y + ClickGuiStyle.ROW, over ? ClickGuiStyle.COL_HOVER : ClickGuiStyle.COL_ROW);
			double value = get.getAsDouble();
			String shown = format(value);
			KitUi.text(graphics, font, KitUi.fit(font, label, w - 100), x + 5, y + 4, ClickGuiStyle.COL_TEXT);
			int barX = x + w - 92;
			int barY = y + 6;
			int barW = 70;
			graphics.fill(barX, barY, barX + barW, barY + 4, ClickGuiStyle.COL_SLIDER);
			double t = (value - min) / (max - min);
			int fill = (int)Math.round(Math.max(0, Math.min(1, t)) * barW);
			graphics.fill(barX, barY, barX + fill, barY + 4, ClickGuiStyle.COL_ACCENT);
			KitUi.text(graphics, font, shown, barX + barW - font.width(shown), y + 4, ClickGuiStyle.COL_MUTED);
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			screen.sliding = this;
			screen.setDragging(true);
			applyMouse(mx, x, w);
		}

		void applyMouse(int mx, int x, int w) {
			int barX = x + w - 92;
			int barW = 70;
			double t = (mx - barX) / (double)barW;
			double raw = min + Math.max(0, Math.min(1, t)) * (max - min);
			double snapped = Math.round(raw / step) * step;
			set.accept(Math.max(min, Math.min(max, snapped)));
		}

		private String format(double value) {
			if (step >= 1 && value == Math.rint(value)) return Integer.toString((int)Math.round(value));
			return KitUi.formatNumber(value);
		}

		@Override
		public String tip() {
			return tip;
		}
	}

	/** 循环选项行。 */
	private final class CycleRow implements Row {
		private final String label;
		private final String tip;
		private final String[] options;
		private final IntSupplier get;
		private final IntConsumer set;

		CycleRow(String label, String tip, String[] options, IntSupplier get, IntConsumer set) {
			this.label = label;
			this.tip = tip;
			this.options = options;
			this.get = get;
			this.set = set;
		}

		@Override
		public int height(Font font, int width) {
			return ClickGuiStyle.ROW;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			boolean over = mouseX >= x && mouseX < x + w && mouseY >= y && mouseY < y + ClickGuiStyle.ROW;
			graphics.fill(x, y, x + w, y + ClickGuiStyle.ROW, over ? ClickGuiStyle.COL_HOVER : ClickGuiStyle.COL_ROW);
			int index = Math.floorMod(get.getAsInt(), options.length);
			KitUi.text(graphics, font, KitUi.fit(font, label, w / 2), x + 5, y + 4, ClickGuiStyle.COL_TEXT);
			String value = options[index];
			KitUi.text(graphics, font, value, x + w - font.width(value) - 6, y + 4, ClickGuiStyle.COL_ACCENT);
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			int index = Math.floorMod(get.getAsInt(), options.length);
			int next = button == 1 ? index - 1 : index + 1;
			set.accept(Math.floorMod(next, options.length));
		}

		@Override
		public String tip() {
			return tip;
		}
	}

	/** 动作按钮行。 */
	private final class ActionRow implements Row {
		private final String label;
		private final String tip;
		private final Runnable run;

		ActionRow(String label, String tip, Runnable run) {
			this.label = label;
			this.tip = tip;
			this.run = run;
		}

		@Override
		public int height(Font font, int width) {
			return ClickGuiStyle.ROW;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			boolean over = mouseX >= x && mouseX < x + w && mouseY >= y && mouseY < y + ClickGuiStyle.ROW;
			graphics.fill(x, y, x + w, y + ClickGuiStyle.ROW, over ? ClickGuiStyle.COL_HOVER : ClickGuiStyle.COL_ROW);
			KitUi.centered(graphics, font, label, x + w / 2, y + 4, ClickGuiStyle.COL_TEXT);
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			if (!screen.finishEdits()) return;
			try { run.run(); } catch (IllegalArgumentException error) { screen.showNotice(error.getMessage(), 0xFF7777); }
		}

		@Override
		public String tip() {
			return tip;
		}
	}

	/** 可编辑文本行。 */
	private final class EditRow implements Row {
		private final String label;
		private final String tip;
		private final Supplier<String> get;
		private final Consumer<String> set;
		private boolean focused;

		EditRow(String label, String tip, Supplier<String> get, Consumer<String> set) {
			this.label = label;
			this.tip = tip;
			this.get = get;
			this.set = set;
		}

		String readValue() {
			String value = get.get();
			return value == null ? "" : value;
		}

		void commitValue(String value) {
			set.accept(value == null ? "" : value);
		}

		void unfocus() {
			focused = false;
		}

		@Override
		public int height(Font font, int width) {
			return ClickGuiStyle.ROW;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			boolean over = mouseX >= x && mouseX < x + w && mouseY >= y && mouseY < y + ClickGuiStyle.ROW;
			graphics.fill(x, y, x + w, y + ClickGuiStyle.ROW, over ? ClickGuiStyle.COL_HOVER : ClickGuiStyle.COL_ROW);
			KitUi.text(graphics, font, KitUi.fit(font, label, 70), x + 5, y + 4, ClickGuiStyle.COL_TEXT);
			int boxX = x + 78;
			boolean active = focused && valueEditor != null;
			graphics.fill(boxX, y + 2, x + w - 4, y + ClickGuiStyle.ROW - 2, active ? 0xFF2A1A33 : ClickGuiStyle.COL_BOX);
			if (!active) {
				String text = readValue();
				String shown = KitUi.fit(font, text, w - 88);
				KitUi.text(graphics, font, shown, boxX + 3, y + 4, ClickGuiStyle.COL_TEXT);
			}
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			if (button != 0) return;
			screen.beginValueEdit(this, x + 78, y, w - 86);
		}

		@Override
		public String tip() {
			return tip;
		}
	}

	/** 多选 chip 行。 */
	private final class ChipRow implements Row {
		private final String tip;
		private final List<Chip> chips;

		ChipRow(String tip, List<Chip> chips) {
			this.tip = tip;
			this.chips = chips;
		}

		@Override
		public int height(Font font, int width) {
			return rows(font, width) * 14;
		}

		private int rows(Font font, int width) {
			int x = 4;
			int row = 1;
			int max = width - 8;
			for (Chip chip : chips) {
				int cw = font.width(chip.label) + 10;
				if (x + cw > max && x > 4) {
					row++;
					x = 4;
				}
				x += cw + 3;
			}
			return row;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			int cx = x + 4;
			int cy = y + 1;
			int max = x + w - 4;
			for (Chip chip : chips) {
				int cw = font.width(chip.label) + 10;
				if (cx + cw > max && cx > x + 4) {
					cx = x + 4;
					cy += 14;
				}
				boolean on = chip.on.getAsBoolean();
				boolean over = mouseX >= cx && mouseX < cx + cw && mouseY >= cy && mouseY < cy + 12;
				graphics.fill(cx, cy, cx + cw, cy + 12, on ? ClickGuiStyle.COL_ON : (over ? ClickGuiStyle.COL_HOVER : ClickGuiStyle.COL_BOX));
				KitUi.text(graphics, font, chip.label, cx + 5, cy + 2, on ? ClickGuiStyle.COL_TEXT : ClickGuiStyle.COL_MUTED);
				cx += cw + 3;
			}
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			int cx = x + 4;
			int cy = y + 1;
			int max = x + w - 4;
			for (Chip chip : chips) {
				int cw = screen.font.width(chip.label) + 10;
				if (cx + cw > max && cx > x + 4) {
					cx = x + 4;
					cy += 14;
				}
				if (mx >= cx && mx < cx + cw && my >= cy && my < cy + 12) {
					chip.toggle.run();
					return;
				}
				cx += cw + 3;
			}
		}

		@Override
		public String tip() {
			return tip;
		}
	}

	/** 图标勾选行。 */
	private final class IconRow implements Row {
		private static final int GAP = 3;
		private static final int MIN = 20;
		private static final int MAX = 28;
		private final String tip;
		private final List<IconChip> icons;
		private final BooleanSupplier visible;

		IconRow(String tip, List<IconChip> icons, BooleanSupplier visible) {
			this.tip = tip;
			this.icons = icons;
			this.visible = visible;
		}

		private boolean shown() {
			return visible.getAsBoolean();
		}

		private int iconSize(int width) {
			int n = Math.max(1, icons.size());
			int available = Math.max(MIN, width - 8);
			int size = (available - (n - 1) * GAP) / n;
			return Math.max(MIN, Math.min(MAX, size));
		}

		private int perRow(int width, int icon) {
			return Math.max(1, (width - 8 + GAP) / (icon + GAP));
		}

		@Override
		public int height(Font font, int width) {
			if (!shown()) return 0;
			int icon = iconSize(width);
			int cols = perRow(width, icon);
			int rows = (icons.size() + cols - 1) / cols;
			return rows * (icon + GAP) + 2;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			if (!shown()) return;
			int icon = iconSize(w);
			int cols = perRow(w, icon);
			for (int i = 0; i < icons.size(); i++) {
				IconChip chip = icons.get(i);
				int ix = x + 4 + (i % cols) * (icon + GAP);
				int iy = y + 1 + (i / cols) * (icon + GAP);
				boolean on = chip.on.getAsBoolean();
				boolean over = mouseX >= ix && mouseX < ix + icon && mouseY >= iy && mouseY < iy + icon;
				graphics.fill(ix, iy, ix + icon, iy + icon, over ? 0xFF4A4A4A : 0xFF2A2A2A);
				if (on) {
					graphics.fill(ix + 1, iy + 1, ix + icon - 1, iy + icon - 1, 0x8844DDFF);
					graphics.fill(ix, iy, ix + icon, iy + 1, 0xFFFFFFFF);
					graphics.fill(ix, iy + icon - 1, ix + icon, iy + icon, 0xFFFFFFFF);
					graphics.fill(ix, iy, ix + 1, iy + icon, 0xFFFFFFFF);
					graphics.fill(ix + icon - 1, iy, ix + icon, iy + icon, 0xFFFFFFFF);
				}
				graphics.item(chip.stack, ix + (icon - 16) / 2, iy + (icon - 16) / 2);
			}
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
			if (!shown() || button != 0) return;
			int icon = iconSize(w);
			int cols = perRow(w, icon);
			for (int i = 0; i < icons.size(); i++) {
				int ix = x + 4 + (i % cols) * (icon + GAP);
				int iy = y + 1 + (i / cols) * (icon + GAP);
				if (mx >= ix && mx < ix + icon && my >= iy && my < iy + icon) {
					icons.get(i).toggle.run();
					return;
				}
			}
		}

		@Override
		public String tip() {
			return tip;
		}

		@Override
		public String tipAt(int mx, int my, int x, int y, int w) {
			if (!shown()) return "";
			int icon = iconSize(w);
			int cols = perRow(w, icon);
			for (int i = 0; i < icons.size(); i++) {
				int ix = x + 4 + (i % cols) * (icon + GAP);
				int iy = y + 1 + (i / cols) * (icon + GAP);
				if (mx >= ix && mx < ix + icon && my >= iy && my < iy + icon) {
					return icons.get(i).tip;
				}
			}
			return tip;
		}
	}

	/** 说明文字行。 */
	private final class NoteRow implements Row {
		private final String text;

		NoteRow(String text) {
			this.text = text;
		}

		@Override
		public int height(Font font, int width) {
			return 12;
		}

		@Override
		public void render(GuiGraphicsExtractor graphics, Font font, int x, int y, int w, int mouseX, int mouseY) {
			KitUi.text(graphics, font, KitUi.fit(font, text, w - 8), x + 5, y + 2, ClickGuiStyle.COL_MUTED);
		}

		@Override
		public void click(int mx, int my, int button, int x, int y, int w, ClickGuiPanelScreen screen) {
		}
	}
}
