package dev.twob2tkit.structure;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.ContainerObjectSelectionList;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.List;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 管理「附近结构」里打过的去过/备注标记：逐个删除或者一次清空。 */
public final class StructureMarksScreen extends KitHudScreen {
	private final KitConfig config;
	private MarkList list;
	private boolean confirmClear;

	public StructureMarksScreen(Screen parent, KitConfig config) {
		super(Component.literal("结构标记"), parent);
		this.config = config;
	}

	@Override
	/** 列表、清空与「只看没去过」开关。 */
	protected void init() {
		int left = panelLeft(360);
		addRenderableWidget(Button.builder(Component.literal(confirmClear ? "再点一次确认清空" : "全部清空"), button -> {
			if (!confirmClear) {
				confirmClear = true;
				showNotice("会删掉全部标记和备注，确定就再点一次", 0xFFFF55);
				rebuildWidgets();
				return;
			}
			config.clearStructureMarks();
			confirmClear = false;
			showNotice("已清空全部标记", 0x55FF55);
			rebuildWidgets();
		}).bounds(left, bodyTop(30), 176, 20)
			.tooltip(Tooltip.create(Component.literal("清掉所有结构的「已去」和备注，不影响搜索结果本身。")))
			.build()).active = !config.structureMarks.isEmpty();
		addRenderableWidget(Button.builder(Component.literal(config.structureHideVisited ? "只看没去过 √" : "只看没去过"), button -> {
			config.structureHideVisited = !config.structureHideVisited;
			config.save();
			rebuildWidgets();
		}).bounds(left + 184, bodyTop(30), 176, 20)
			.tooltip(Tooltip.create(Component.literal("和结构列表里那个开关是同一个。")))
			.build());

		int listTop = bodyTop(72);
		int listHeight = Math.max(48, contentBottom() - 28 - listTop);
		list = addRenderableWidget(new MarkList(this.minecraft, this.width, listHeight, listTop));
		list.populate();

		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(this.width / 2 - 75, contentBottom(), 150, 20).build());
	}

	@Override
	/** 画标题与空列表提示。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, "结构标记 · 共 " + config.structureMarks.size() + " 条", center, headerY(10), 0xFFFFFF);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, bodyTop(58), noticeColor);
		else if (config.structureMarks.isEmpty()) {
			KitUi.centered(graphics, this.font, "还没有标记；在附近结构列表里点「已去」或写备注就会出现在这里", center, bodyTop(58), 0xA0A0A0);
		}
	}

	/** 复制传送命令到剪贴板。 */
	private void copy(KitConfig.StructureMark mark) {
		String command = "/tp " + mark.x + " ~ " + mark.z;
		if (this.minecraft.keyboardHandler != null) this.minecraft.keyboardHandler.setClipboard(command);
		showNotice("已复制 " + command, 0x55FF55);
	}

	/** 删一条标记并刷新列表。 */
	private void delete(KitConfig.StructureMark mark) {
		config.removeStructureMark(mark);
		showNotice("已删除 " + StructureLocator.labelForId(mark.kind) + " " + mark.x + " " + mark.z, 0xFFFF55);
		confirmClear = false;
		rebuildWidgets();
	}

	private final class MarkList extends ContainerObjectSelectionList<MarkList.Entry> {
		private MarkList(Minecraft minecraft, int width, int height, int y) {
			super(minecraft, width, height, y, 26);
			this.centerListVertically = false;
		}

		/** 按配置填充列表行。 */
		private void populate() {
			clearEntries();
			for (KitConfig.StructureMark mark : config.structureMarks) addEntry(new Entry(mark));
		}

		@Override
		/** 列表行宽。 */
		public int getRowWidth() {
			return Math.min(360, this.width - 24);
		}

		private final class Entry extends ContainerObjectSelectionList.Entry<Entry> {
			private final KitConfig.StructureMark mark;
			private final Button copy;
			private final Button remove;

			private Entry(KitConfig.StructureMark mark) {
				this.mark = mark;
				this.copy = Button.builder(Component.literal("复制"), button -> copy(mark)).bounds(0, 0, 40, 20).build();
				this.remove = Button.builder(Component.literal("删除"), button -> delete(mark)).bounds(0, 0, 40, 20).build();
			}

			@Override
			/** 画标记文案与复制/删除按钮。 */
			public void extractContent(GuiGraphicsExtractor graphics, int mouseX, int mouseY, boolean hovered, float delta) {
				String note = mark.note == null ? "" : mark.note.trim();
				String description = (mark.visited ? "√ " : "") + StructureLocator.labelForId(mark.kind)
					+ "  " + mark.x + " " + mark.z
					+ (note.isEmpty() ? "" : "  " + note);
				graphics.text(font, KitUi.fit(font, description, getContentRight() - getContentX() - 92),
					getContentX(), getContentYMiddle() - 4, KitUi.argb(hovered ? 0xFFFF55 : 0xFFFFFF));
				int buttonY = getContentY() - 2;
				remove.setPosition(getContentRight() - 42, buttonY);
				copy.setPosition(getContentRight() - 86, buttonY);
				copy.extractRenderState(graphics, mouseX, mouseY, delta);
				remove.extractRenderState(graphics, mouseX, mouseY, delta);
			}

			@Override
			public List<? extends GuiEventListener> children() {
				return List.of(copy, remove);
			}

			@Override
			public List<? extends NarratableEntry> narratables() {
				return List.of(copy, remove);
			}
		}
	}
}
