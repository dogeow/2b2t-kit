package dev.twob2tkit.borer;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 巷道断面、朝向、前探与找矿半径。 */
public final class TunnelSetupScreen extends KitHudScreen {
	private final KitConfig config;
	private EditBox widthField;
	private EditBox heightField;
	private EditBox lookAhead;
	private EditBox oreRadius;
	private Button lookHeading;
	private Button northHeading;
	private Button southHeading;
	private Button eastHeading;
	private Button westHeading;
	private String draftWidth = "";
	private String draftHeight = "";
	private String draftLook = "";
	private String draftOre = "";

	public TunnelSetupScreen(Screen parent, KitConfig config) {
		super(Component.literal("巷道设置"), parent);
		this.config = config;
	}

	@Override
	/** 断面快捷按钮、朝向与前探/找矿半径。 */
	protected void init() {
		captureDrafts();
		int left = panelLeft(340);
		int y = bodyTop(36);
		addRenderableWidget(Button.builder(Component.literal("1×2"), b -> setSize(1, 2)).bounds(left, y, 44, 20).build());
		addRenderableWidget(Button.builder(Component.literal("2×2"), b -> setSize(2, 2)).bounds(left + 46, y, 44, 20).build());
		addRenderableWidget(Button.builder(Component.literal("3×3"), b -> setSize(3, 3)).bounds(left + 92, y, 44, 20).build());
		addRenderableWidget(Button.builder(Component.literal("4×4"), b -> setSize(4, 4)).bounds(left + 138, y, 44, 20).build());
		addRenderableWidget(Button.builder(Component.literal("3×5"), b -> setSize(3, 5)).bounds(left + 184, y, 44, 20).build());
		widthField = addRenderableWidget(KitUi.field(this.font, left + 232, y, 52, "宽度", draftOr(draftWidth, config.borerWidth), 2));
		heightField = addRenderableWidget(KitUi.field(this.font, left + 288, y, 52, "高度", draftOr(draftHeight, config.borerHeight), 2));
		y += 24;
		lookHeading = headingButton(left, y, 60, "准星", "LOOK");
		northHeading = headingButton(left + 68, y, 60, "北", Direction.NORTH.name());
		southHeading = headingButton(left + 136, y, 60, "南", Direction.SOUTH.name());
		westHeading = headingButton(left + 204, y, 60, "西", Direction.WEST.name());
		eastHeading = headingButton(left + 272, y, 68, "东", Direction.EAST.name());
		y += 24;
		lookAhead = addRenderableWidget(KitUi.field(this.font, left + 70, y, 70, "前探", draftOr(draftLook, Math.max(1, config.borerLookAhead)), 2));
		oreRadius = addRenderableWidget(KitUi.field(this.font, left + 250, y, 90, "找矿半径", draftOr(draftOre, config.borerOreRadius), 2));
		label(left, y + 6, 60, "前探格", 0xA0A0A0);
		label(left + 180, y + 6, 60, "扫描", 0xA0A0A0);
		y += 28;
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(this.width / 2 - 75, y, 150, 20).build());
		refreshHeadingButtons();
	}

	@Override
	/** 画标题与提示。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		KitUi.centered(graphics, this.font, "巷道与朝向", this.width / 2, 12, 0xFFFFFF);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, this.width / 2, 24, noticeColor);
	}

	@Override
	/** 关界面前保存字段。 */
	public void onClose() {
		saveFields();
		super.onClose();
	}

	/** 设置掘进朝向并存盘。 */
	private Button headingButton(int x, int y, int width, String label, String value) {
		return addRenderableWidget(Button.builder(Component.literal(label), button -> {
			config.borerHeading = value;
			config.save();
			/** 当前朝向按钮变灰。 */
			refreshHeadingButtons();
		}).bounds(x, y, width, 20).build());
	}

	/** 快捷写入宽高并刷新输入框。 */
	private void setSize(int width, int height) {
		config.borerWidth = width;
		config.borerHeight = height;
		config.save();
		if (widthField != null) widthField.setValue(Integer.toString(width));
		if (heightField != null) heightField.setValue(Integer.toString(height));
	}

	/** 重建控件前记下输入草稿。 */
	private void captureDrafts() {
		if (widthField != null) draftWidth = widthField.getValue();
		if (heightField != null) draftHeight = heightField.getValue();
		if (lookAhead != null) draftLook = lookAhead.getValue();
		if (oreRadius != null) draftOre = oreRadius.getValue();
	}

	/** 校验并写入宽度/高度/前探/找矿半径。 */
	private void saveFields() {
		try {
			if (widthField != null) config.borerWidth = KitUi.parseInt(widthField, "宽度", 1, 5);
			if (heightField != null) config.borerHeight = KitUi.parseInt(heightField, "高度", 1, 5);
			if (lookAhead != null) config.borerLookAhead = KitUi.parseInt(lookAhead, "前探格", 1, 5);
			if (oreRadius != null) config.borerOreRadius = KitUi.parseInt(oreRadius, "找矿半径", 8, 32);
			config.save();
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
		}
	}

	/** 当前朝向按钮变灰。 */
	private void refreshHeadingButtons() {
		String heading = config.borerHeading == null ? "LOOK" : config.borerHeading.toUpperCase();
		if (lookHeading != null) lookHeading.active = !heading.equals("LOOK");
		if (northHeading != null) northHeading.active = !heading.equals("NORTH");
		if (southHeading != null) southHeading.active = !heading.equals("SOUTH");
		if (westHeading != null) westHeading.active = !heading.equals("WEST");
		if (eastHeading != null) eastHeading.active = !heading.equals("EAST");
	}

	/** 草稿空则用回退值。 */
	private static String draftOr(String draft, int fallback) {
		return draft == null || draft.isBlank() ? Integer.toString(fallback) : draft;
	}
}
