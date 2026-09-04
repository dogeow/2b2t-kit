package dev.twob2tkit.structure;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 给附近结构列表里的一个结构写备注。 */
public final class StructureNoteScreen extends KitHudScreen {
	private final KitConfig config;
	private final String markKind;
	private final StructureLocator.Hit hit;
	private EditBox noteBox;

	public StructureNoteScreen(Screen parent, KitConfig config, String markKind, StructureLocator.Hit hit) {
		super(Component.literal("结构备注"), parent);
		this.config = config;
		this.markKind = markKind;
		this.hit = hit;
	}

	@Override
	/** 备注输入框与保存/返回。 */
	protected void init() {
		int left = panelLeft(340);
		KitConfig.StructureMark mark = config.structureMark(markKind, hit.x(), hit.z());
		String note = mark == null || mark.note == null ? "" : mark.note;
		noteBox = addRenderableWidget(KitUi.field(this.font, left, bodyTop(58), 340, "备注", note, 120));
		noteBox.setHint(Component.literal("比如：箱子搬空了、有刷怪笼没拆"));
		addRenderableWidget(Button.builder(Component.literal("保存"), button -> save())
			.bounds(left, bodyTop(86), 166, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left + 174, bodyTop(86), 166, 20).build());
		setInitialFocus(noteBox);
	}

	@Override
	/** 回车保存。 */
	protected boolean onEnterPressed() {
		save();
		return true;
	}

	/** 写入标记备注并关界面。 */
	private void save() {
		KitConfig.StructureMark mark = config.ensureStructureMark(markKind, hit.x(), hit.z());
		mark.note = noteBox.getValue().trim();
		config.saveStructureMarks();
		onClose();
	}

	@Override
	/** 画标题与说明。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, "备注 · " + hit.label() + "  " + hit.x() + " " + hit.z(), center, headerY(10), 0xFFFFFF);
		KitUi.centered(graphics, this.font, "保存后悬停列表里的「备注*」可以看到内容", center, headerY(38), 0xA0A0A0);
	}
}
