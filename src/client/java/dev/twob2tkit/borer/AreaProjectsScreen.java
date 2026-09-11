package dev.twob2tkit.borer;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.ContainerObjectSelectionList;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.List;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 区域挖工程：保存多个 A/B 区域，随时加载。 */
public final class AreaProjectsScreen extends KitHudScreen {
	private final KitConfig config;
	private EditBox projectName;
	private String draftName = "";
	private String draftDimension;
	private ProjectList list;

	public AreaProjectsScreen(Screen parent, KitConfig config) {
		super(Component.literal("区域挖工程"), parent);
		this.config = config;
	}

	@Override
	/** 工程名输入与工程列表。 */
	protected void init() {
        dev.twob2tkit.KitRecordPages.projects(parent, config);
        if (this.minecraft.screen != this) return;
		int left = panelLeft(360);
		if (projectName != null) draftName = projectName.getValue();
		if (draftDimension == null) draftDimension = BorerAreaProjects.currentDimension(this.minecraft);

		projectName = addRenderableWidget(KitUi.field(this.font, left, bodyTop(42), 168, "工程名称", draftName, 32));
		projectName.setHint(Component.literal("例如：主基地采石场"));
		addRenderableWidget(Button.builder(Component.literal("保存当前区域"), button -> saveProject())
			.bounds(left + 176, bodyTop(42), 104, 20)
			.tooltip(Tooltip.create(Component.literal("把现在的点 A/B 和条带断面存进列表。同名会覆盖。")))
			.build()).active = config.borerAreaASet && config.borerAreaBSet && !AreaDrafts.hasUnappliedCorners(config);
		addRenderableWidget(Button.builder(Component.literal("维度：" + KitConfig.dimensionLabel(draftDimension)), button -> {
			draftDimension = KitConfig.nextDimension(draftDimension);
			rebuildWidgets();
		}).bounds(left + 284, bodyTop(42), 76, 20)
			.tooltip(Tooltip.create(Component.literal("标注这个区域属于哪个维度。")))
			.build());

		int listTop = bodyTop(72);
		int listHeight = Math.max(48, contentBottom() - 28 - listTop);
		list = addRenderableWidget(new ProjectList(this.minecraft, this.width, listHeight, listTop));
		list.populate();

		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(this.width / 2 - 75, contentBottom(), 150, 20).build());
		setInitialFocus(projectName);
	}

	@Override
	/** 画当前区域摘要。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		int left = panelLeft(360);
		KitUi.centered(graphics, this.font, "区域挖工程 · 共 " + config.areaProjects.size() + " 个", center, headerY(10), 0xFFFFFF);
		String current = BorerAreaMarks.sizeLabel(config);
		String active = BorerAreaProjects.activeName(config);
		String subtitle = active.isEmpty() ? "当前区域：" + current : "当前区域：" + current + "  （工程：" + active + "）";
		KitUi.text(graphics, this.font, KitUi.fit(this.font, subtitle, 360), left, headerY(24), 0xA0A0A0);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, bodyTop(58), noticeColor);
		else if (AreaDrafts.hasUnappliedCorners(config)) {
			KitUi.centered(graphics, this.font, "标点草稿已保留，返回区域页继续；下方仅列完整工程", center, bodyTop(58), 0x77DDCC);
		} else if (config.areaProjects.isEmpty()) {
			KitUi.centered(graphics, this.font, "还没有工程；标好点 A/B 后填名称点「保存当前区域」", center, bodyTop(58), 0xA0A0A0);
		} else if (!config.borerAreaASet || !config.borerAreaBSet) {
			KitUi.centered(graphics, this.font, "当前未标完整区域，可从下面列表加载", center, bodyTop(58), 0xA0A0A0);
		}
	}

	@Override
	/** 回车保存工程。 */
	protected boolean onEnterPressed() {
		saveProject();
		return true;
	}

	/** 按名称 upsert 当前区域。 */
	private void saveProject() {
		if (AreaDrafts.hasUnappliedCorners(config)) {
			showNotice("请返回区域页补齐并保存，避免误存旧范围", 0xFFFF55);
			return;
		}
		String name = projectName.getValue().trim();
		if (name.isEmpty()) {
			showNotice("请先填写工程名称", 0xFF5555);
			return;
		}
		if (!config.borerAreaASet || !config.borerAreaBSet) {
			showNotice("先设好点 A 和点 B 再保存", 0xFF5555);
			return;
		}
		boolean added = config.upsertAreaProject(name, draftDimension);
		showNotice((added ? "已保存工程：" : "已更新工程：") + name + "  " + BorerAreaMarks.sizeLabel(config), 0x55FF55);
		list.populate();
		rebuildWidgets();
	}

	/** 加载工程到配置并提示。 */
	private void loadProject(KitConfig.AreaProject project) {
		config.loadAreaProject(project.id);
		projectName.setValue(project.name);
		draftDimension = KitConfig.normalizeDimension(project.dimension);
		if (draftDimension.isEmpty()) draftDimension = BorerAreaProjects.currentDimension(this.minecraft);
		showNotice("已加载「" + project.name + "」  " + BorerAreaProjects.summary(project), 0x55FFFF);
		rebuildWidgets();
	}

	/** 删除一条工程。 */
	private void delete(KitConfig.AreaProject project) {
		config.removeAreaProject(project.id);
		showNotice("已删除工程：" + project.name, 0xFFFF55);
		rebuildWidgets();
	}

	private final class ProjectList extends ContainerObjectSelectionList<ProjectList.Entry> {
		private ProjectList(Minecraft minecraft, int width, int height, int y) {
			super(minecraft, width, height, y, 26);
			this.centerListVertically = false;
		}

		/** 填充工程列表行。 */
		private void populate() {
			clearEntries();
			for (KitConfig.AreaProject project : config.areaProjects) {
				addEntry(new Row(project));
			}
		}

		@Override
		/** 列表行宽。 */
		public int getRowWidth() {
			return Math.min(360, this.width - 24);
		}

		private abstract class Entry extends ContainerObjectSelectionList.Entry<Entry> {
		}

		private final class Row extends Entry {
			private final KitConfig.AreaProject project;
			private final Button load;
			private final Button remove;

			private Row(KitConfig.AreaProject project) {
				this.project = project;
				this.load = Button.builder(Component.literal("加载"), button -> loadProject(project)).bounds(0, 0, 40, 20).build();
				this.remove = Button.builder(Component.literal("删除"), button -> delete(project)).bounds(0, 0, 40, 20).build();
			}

			@Override
			/** 画工程行与加载/删除按钮。 */
			public void extractContent(GuiGraphicsExtractor graphics, int mouseX, int mouseY, boolean hovered, float delta) {
				boolean active = project.id.equals(config.activeAreaProjectId);
				String title = BorerAreaProjects.listLine(project, active);
				graphics.text(font, KitUi.fit(font, title, getContentRight() - getContentX() - 92),
					getContentX(), getContentYMiddle() - 4, KitUi.argb(hovered || active ? 0xFFFF55 : 0xFFFFFF));
				int buttonY = getContentY() - 2;
				remove.setPosition(getContentRight() - 42, buttonY);
				load.setPosition(getContentRight() - 86, buttonY);
				load.extractRenderState(graphics, mouseX, mouseY, delta);
				remove.extractRenderState(graphics, mouseX, mouseY, delta);
			}

			@Override
			public List<? extends GuiEventListener> children() {
				return List.of(load, remove);
			}

			@Override
			public List<? extends NarratableEntry> narratables() {
				return List.of(load, remove);
			}
		}
	}
}
