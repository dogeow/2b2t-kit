package dev.twob2tkit.borer;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 区域挖：标点 / 断面 / 工程入口。 */
public final class AreaSetupScreen extends KitHudScreen {
	/** 区域挖设置子页。 */
	public enum Tab {
		MARKS("标点"),
		SIZE("断面"),
		PROJECTS("工程");

		final String label;

		Tab(String label) {
			this.label = label;
		}
	}

	private final KitConfig config;
	private Tab tab = Tab.MARKS;
	private Button tabMarks;
	private Button tabSize;
	private Button tabProjects;
	private EditBox areaAField;
	private EditBox areaBField;
	private EditBox sliceField;
	private EditBox stripField;
	private String draftAreaA = "";
	private String draftAreaB = "";
	private String draftSlice = "";
	private String draftStrip = "";

	public AreaSetupScreen(Screen parent, KitConfig config) {
		super(Component.literal("区域设置"), parent);
		this.config = config;
	}

	@Override
	/** 标签栏与当前页控件。 */
	protected void init() {
		captureDrafts();
		int left = panelLeft(340);
		int y = bodyTop(36);
		tabMarks = tabButton(left, y, 108, Tab.MARKS);
		tabSize = tabButton(left + 112, y, 108, Tab.SIZE);
		tabProjects = tabButton(left + 224, y, 116, Tab.PROJECTS);
		y += 24;
		y = switch (tab) {
			case MARKS -> buildMarks(left, y);
			case SIZE -> buildSize(left, y);
			case PROJECTS -> buildProjects(left, y);
		};
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(this.width / 2 - 75, Math.min(y + 8, contentBottom()), 150, 20).build());
		refreshTabs();
	}

	@Override
	/** 画标题与提示。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, "区域设置  ·  " + BorerAreaMarks.sizeLabel(config), center, headerY(12), 0xFFFFFF);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, headerY(24), noticeColor);
	}

	@Override
	/** 关界面前安静保存。 */
	public void onClose() {
		saveFields();
		super.onClose();
	}

	/** 切换标点/断面/工程标签。 */
	private Button tabButton(int x, int y, int width, Tab value) {
		return addRenderableWidget(Button.builder(Component.literal(value.label), button -> {
			saveFieldsQuiet();
			tab = value;
			rebuildWidgets();
		}).bounds(x, y, width, 20).build());
	}

	/** 标点 A/B 与准星取点按钮。 */
	private int buildMarks(int left, int y) {
		areaAField = addRenderableWidget(KitUi.field(this.font, left, y, 340, "点A",
			draftOr(draftAreaA, BorerAreaMarks.format(config.borerAreaASet, config.borerAreaAx, config.borerAreaAy, config.borerAreaAz)), 48));
		y += 22;
		addRenderableWidget(Button.builder(Component.literal("准星A"), b -> pickCorner(1, false)).bounds(left, y, 108, 20).build());
		addRenderableWidget(Button.builder(Component.literal("左键A"), b -> pickCorner(1, true)).bounds(left + 116, y, 108, 20).build());
		addRenderableWidget(Button.builder(Component.literal("脚下A"), b -> {
			if (this.minecraft.player == null) return;
			BorerAreaMarks.setA(config, this.minecraft.player.blockPosition());
			rebuildWidgets();
		}).bounds(left + 232, y, 108, 20).build());
		y += 24;
		areaBField = addRenderableWidget(KitUi.field(this.font, left, y, 340, "点B",
			draftOr(draftAreaB, BorerAreaMarks.format(config.borerAreaBSet, config.borerAreaBx, config.borerAreaBy, config.borerAreaBz)), 48));
		y += 22;
		addRenderableWidget(Button.builder(Component.literal("准星B"), b -> pickCorner(2, false)).bounds(left, y, 108, 20).build());
		addRenderableWidget(Button.builder(Component.literal("左键B"), b -> pickCorner(2, true)).bounds(left + 116, y, 108, 20).build());
		addRenderableWidget(Button.builder(Component.literal("40×40"), b -> {
			if (this.minecraft.player == null) return;
			BorerAreaMarks.sizeFromFeet(config, this.minecraft.player.blockPosition(), this.minecraft.player.getDirection(), 40);
			config.borerLastMode = TunnelBorer.Mode.AREA.name();
			config.save();
			rebuildWidgets();
			showNotice("已标 " + BorerAreaMarks.sizeLabel(config), 0x55FF55);
		}).bounds(left + 232, y, 108, 20).build());
		y += 24;
		addRenderableWidget(Button.builder(Component.literal("清除区域"), b -> {
			draftAreaA = "";
			draftAreaB = "";
			areaAField = null;
			areaBField = null;
			BorerAreaMarks.clear(config);
			rebuildWidgets();
			showNotice("已清除区域", 0x55FF55);
		}).bounds(left, y, 108, 20).build());
		return y + 26;
	}

	/** 断面宽高输入。 */
	private int buildSize(int left, int y) {
		addRenderableWidget(Button.builder(Component.literal("1×2"), b -> setAreaSize(1, 2)).bounds(left, y, 80, 20).build());
		addRenderableWidget(Button.builder(Component.literal("2×2"), b -> setAreaSize(2, 2)).bounds(left + 86, y, 80, 20).build());
		addRenderableWidget(Button.builder(Component.literal("3×3"), b -> setAreaSize(3, 3)).bounds(left + 172, y, 80, 20).build());
		addRenderableWidget(Button.builder(Component.literal("4×4"), b -> setAreaSize(4, 4)).bounds(left + 258, y, 82, 20).build());
		y += 24;
		label(left, y + 6, 52, "条带宽", 0xA0A0A0);
		stripField = addRenderableWidget(KitUi.field(this.font, left + 56, y, 52, "宽",
			draftOr(draftStrip, Math.max(1, config.borerWidth)), 2));
		label(left + 120, y + 6, 52, "一次挖高", 0xA0A0A0);
		sliceField = addRenderableWidget(KitUi.field(this.font, left + 176, y, 52, "高",
			draftOr(draftSlice, Math.max(1, config.borerAreaSliceHeight)), 2));
		return y + 26;
	}

	/** 打开工程列表入口。 */
	private int buildProjects(int left, int y) {
		addRenderableWidget(Button.builder(Component.literal("保存当前"), b -> saveProject())
			.bounds(left, y, 164, 20).build()).active = config.borerAreaASet && config.borerAreaBSet;
		addRenderableWidget(Button.builder(Component.literal("工程管理"), b -> {
			saveFieldsQuiet();
			this.minecraft.setScreen(new AreaProjectsScreen(this, config));
		}).bounds(left + 176, y, 164, 20).build());
		return y + 26;
	}

	/** 用准星或左键命中设 A/B。 */
	private void pickCorner(int corner, boolean leftClickPick) {
		if (leftClickPick) {
			saveFieldsQuiet();
			this.minecraft.setScreen(null);
			KitClient.beginPickingArea(this.minecraft, corner);
			return;
		}
		var pos = BorerAreaMarks.lookBlock(this.minecraft);
		if (pos == null) {
			showNotice("准星没有方块", 0xFF5555);
			return;
		}
		if (corner == 2) BorerAreaMarks.setB(config, pos);
		else BorerAreaMarks.setA(config, pos);
		showNotice((corner == 2 ? "点B " : "点A ") + pos.getX() + " " + pos.getY() + " " + pos.getZ(), 0x55FFFF);
		rebuildWidgets();
	}

	/** 把当前区域存成工程。 */
	private void saveProject() {
		if (!saveFields()) return;
		if (!config.borerAreaASet || !config.borerAreaBSet) {
			showNotice("先设点A和点B", 0xFF5555);
			return;
		}
		String name = BorerAreaProjects.activeName(config);
		if (name.isEmpty()) name = BorerAreaProjects.defaultName(config);
		boolean added = config.upsertAreaProject(name, BorerAreaProjects.currentDimension(this.minecraft));
		showNotice((added ? "已保存工程：" : "已更新工程：") + name, 0x55FF55);
		rebuildWidgets();
	}

	/** 快捷写入断面尺寸。 */
	private void setAreaSize(int width, int height) {
		config.borerWidth = width;
		config.borerHeight = height;
		config.borerAreaSliceHeight = height;
		config.save();
		if (sliceField != null) sliceField.setValue(Integer.toString(height));
		if (stripField != null) stripField.setValue(Integer.toString(width));
	}

	/** 重建前记下输入草稿。 */
	private void captureDrafts() {
		if (areaAField != null) draftAreaA = areaAField.getValue();
		if (areaBField != null) draftAreaB = areaBField.getValue();
		if (sliceField != null) draftSlice = sliceField.getValue();
		if (stripField != null) draftStrip = stripField.getValue();
	}

	/** 尽量保存，失败静默。 */
	private void saveFieldsQuiet() {
		try {
			saveFields();
		} catch (RuntimeException ignored) {
		}
	}

	/** 校验并写入 A/B 与断面。 */
	private boolean saveFields() {
		try {
			if (sliceField != null) config.borerAreaSliceHeight = KitUi.parseInt(sliceField, "一次挖高", 1, 5);
			if (stripField != null) config.borerWidth = KitUi.parseInt(stripField, "条带宽", 1, 5);
			boolean aBlank = areaAField == null || areaAField.getValue().isBlank();
			boolean bBlank = areaBField == null || areaBField.getValue().isBlank();
			if (aBlank && bBlank) {
				if (config.borerAreaASet || config.borerAreaBSet) BorerAreaMarks.clear(config);
			} else {
				if (!aBlank) BorerAreaMarks.applyA(config, areaAField.getValue());
				if (!bBlank) BorerAreaMarks.applyB(config, areaBField.getValue());
			}
			config.save();
			return true;
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return false;
		}
	}

	/** 当前标签按钮变灰。 */
	private void refreshTabs() {
		if (tabMarks != null) tabMarks.active = tab != Tab.MARKS;
		if (tabSize != null) tabSize.active = tab != Tab.SIZE;
		if (tabProjects != null) tabProjects.active = tab != Tab.PROJECTS;
	}

	/** 草稿空则用回退值。 */
	private static String draftOr(String draft, int fallback) {
		return draft == null || draft.isBlank() ? Integer.toString(fallback) : draft;
	}

	/** 草稿空则用回退值。 */
	private static String draftOr(String draft, String fallback) {
		return draft == null || draft.isBlank() ? fallback : draft;
	}
}
