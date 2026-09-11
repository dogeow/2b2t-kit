package dev.twob2tkit;

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
import java.util.Locale;
import dev.twob2tkit.structure.StructureGuide;

/** 地点收藏：按维度筛选、搜索、飞往或开指引。 */
final class KitSavedPlacesScreen extends KitHudScreen {
	private static final String FILTER_ALL = "ALL";

	private final KitConfig config;
	private final KitController controller;
	private EditBox placeName;
	private EditBox targetX;
	private EditBox targetZ;
	private EditBox cruiseY;
	private EditBox listSearch;
	private PlaceList list;
	private String draftName = "";
	private String draftX;
	private String draftZ;
	private String draftY;
	private String draftDimension;
	private String listFilter;
	private String listSearchText = "";
	private boolean editorOpen;
	private double listScroll;
	private SavedPlacesLayout layout;

	KitSavedPlacesScreen(Screen parent, KitConfig config, KitController controller) {
		super(Component.literal("twob2tkit 已存地点"), parent);
		this.config = config;
		this.controller = controller;
	}

	/** 布置编辑区、维度过滤、列表与返回。 */
	@Override
	protected void init() {
        if (UiFeature.redirect("PLACES", parent)) return;
		if (placeName != null) {
			draftName = placeName.getValue();
			draftX = targetX.getValue();
			draftZ = targetZ.getValue();
			draftY = cruiseY.getValue();
		}
		if (listSearch != null) listSearchText = listSearch.getValue();
		if (list != null && list.visible) listScroll = list.scrollAmount();
		if (draftDimension == null) draftDimension = currentDimensionId();
		if (listFilter == null) listFilter = FILTER_ALL;
		layout = SavedPlacesLayout.of(this.width, this.height, editorOpen);
		int left = layout.left();
		placeName = targetX = targetZ = cruiseY = null;

		if (editorOpen) buildEditor(left);

		addRenderableWidget(Button.builder(Component.literal(editorOpen ? "收起编辑" : "新增 / 编辑"), button -> {
			editorOpen = !editorOpen; rebuildWidgets();
		}).bounds(left, layout.toolbarY(), 92, 20)
			.tooltip(Tooltip.create(Component.literal("展开名称和坐标表单；收起后列表能显示更多地点，未保存的输入仍保留。"))).build());
		int filterY = layout.filterY();
		addFilterButton(layout.buttonX(0), filterY, layout.buttonWidth(), KitConfig.DIM_OVERWORLD);
		addFilterButton(layout.buttonX(1), filterY, layout.buttonWidth(), KitConfig.DIM_NETHER);
		addFilterButton(layout.buttonX(2), filterY, layout.buttonWidth(), KitConfig.DIM_END);
		addFilterButton(layout.buttonX(3), filterY, layout.buttonWidth(), FILTER_ALL);

		listSearch = addRenderableWidget(KitUi.field(this.font, left + 100, layout.toolbarY(), layout.width() - 100, "搜索名称",
			listSearchText, 32));
		listSearch.setHint(Component.literal("按名称过滤列表"));
		listSearch.setResponder(text -> {
			listSearchText = text;
			listScroll = 0;
			if (list != null) { list.populate(); list.setScrollAmount(0); }
		});

		list = addRenderableWidget(new PlaceList(this.minecraft, layout.width(), Math.max(1, layout.listHeight()), layout.listTop()));
		list.setX(left);
		list.visible = list.active = layout.listVisible();
		list.populate();
		list.setScrollAmount(listScroll);

		StructureGuide guide = KitClient.structureGuide();
		if (guide != null && guide.isActive()) {
			addRenderableWidget(Button.builder(Component.literal("停指引"), button -> {
				guide.stop();
				showNotice("已关闭指引", 0xFFFF55);
				rebuildWidgets();
			}).bounds(this.width / 2 - 119, layout.footerY(), 80, 20).build());
			addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
				.bounds(this.width / 2 - 31, layout.footerY(), 150, 20).build());
		} else {
			addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
				.bounds(this.width / 2 - 75, layout.footerY(), 150, 20).build());
		}
		setInitialFocus(editorOpen ? placeName : listSearch);
	}

	private void buildEditor(int left) {
		placeName = addRenderableWidget(KitUi.field(this.font, left, 46, layout.nameWidth(), "地点名称", draftName, 32));
		targetX = addRenderableWidget(KitUi.field(this.font, layout.fieldX(1), 46, layout.coordinateWidth(), "目标 X",
			draftX != null ? draftX : KitUi.formatNumber(config.targetX), 24));
		targetZ = addRenderableWidget(KitUi.field(this.font, layout.fieldX(2), 46, layout.coordinateWidth(), "目标 Z",
			draftZ != null ? draftZ : KitUi.formatNumber(config.targetZ), 24));
		cruiseY = addRenderableWidget(KitUi.field(this.font, layout.fieldX(3), 46, layout.coordinateWidth(), "巡航 Y",
			draftY != null ? draftY : KitUi.formatNumber(config.cruiseY), 16));
		placeName.setHint(Component.literal("地点名称"));
		addRenderableWidget(Button.builder(Component.literal("新增 / 更新"), button -> savePlace())
			.bounds(layout.buttonX(0), 70, layout.buttonWidth(), 20)
			.tooltip(Tooltip.create(Component.literal("同名地点会覆盖坐标；回车也可保存"))).build());
		addRenderableWidget(Button.builder(Component.literal("填入当前位置"), button -> useCurrentPosition())
			.bounds(layout.buttonX(1), 70, layout.buttonWidth(), 20).build());
		addRenderableWidget(Button.builder(Component.literal("设为当前目标"), button -> applyAsTarget())
			.bounds(layout.buttonX(2), 70, layout.buttonWidth(), 20)
			.tooltip(Tooltip.create(Component.literal("只保存到主界面目标，不立刻起飞"))).build());
		addRenderableWidget(Button.builder(Component.literal("维度：" + KitConfig.dimensionLabel(draftDimension)), button -> {
			draftDimension = KitConfig.nextDimension(draftDimension);
			rebuildWidgets();
		}).bounds(layout.buttonX(3), 70, layout.buttonWidth(), 20)
			.tooltip(Tooltip.create(Component.literal("这个地点属于哪个维度。填入当前位置会改成你现在所在的维度。"))).build());
	}

	/** 加维度/全部过滤按钮。 */
	private void addFilterButton(int x, int y, int width, String filter) {
		String label = FILTER_ALL.equals(filter) ? "全部" : KitConfig.dimensionLabel(filter);
		int count = countPlaces(filter);
		Button button = addRenderableWidget(Button.builder(Component.literal(label + " " + count), ignored -> {
			listFilter = filter;
			listScroll = 0; if (list != null) list.setScrollAmount(0);
			rebuildWidgets();
		}).bounds(x, y, width, 20).build());
		button.active = !filter.equals(listFilter);
	}

	/** 当前过滤与搜索下的地点数。 */
	private int countPlaces(String filter) {
		String q = listSearchText == null ? "" : listSearchText.trim().toLowerCase(Locale.ROOT);
		if (FILTER_ALL.equals(filter)) {
			if (q.isEmpty()) return config.savedPlaces.size();
			int count = 0;
			for (KitConfig.SavedPlace place : config.savedPlaces) {
				if (place.name.toLowerCase(Locale.ROOT).contains(q)) count++;
			}
			return count;
		}
		int count = 0;
		for (KitConfig.SavedPlace place : config.savedPlaces) {
			if (!KitConfig.normalizeDimension(place.dimension).equals(filter)) continue;
			if (!q.isEmpty() && !place.name.toLowerCase(Locale.ROOT).contains(q)) continue;
			count++;
		}
		return count;
	}

	/** 画标题、列标签与空列表提示。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = layout.left();
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, this.title.getString(), center, 8, 0xFFFFFF);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, KitUi.fit(font, notice, layout.width()), center, 20, noticeColor);
		if (editorOpen) {
			KitUi.text(graphics, this.font, "名称", left, 34, 0xFFFFFF);
			KitUi.text(graphics, this.font, "X", layout.fieldX(1), 34, 0xFFFFFF);
			KitUi.text(graphics, this.font, "Z", layout.fieldX(2), 34, 0xFFFFFF);
			KitUi.text(graphics, this.font, "巡航 Y", layout.fieldX(3), 34, 0xFFFFFF);
		}
		if (!layout.listVisible()) {
			KitUi.centered(graphics, font, "收起编辑即可查看更多地点", center, layout.listTop() + 2, 0xA0A0A0);
			return;
		}
		if (config.savedPlaces.isEmpty()) {
			KitUi.centered(graphics, this.font, "还没有地点，点「新增 / 编辑」添加", center, layout.listTop() + 8, 0xA0A0A0);
		} else if (countPlaces(listFilter) == 0 && !FILTER_ALL.equals(listFilter)) {
			KitUi.centered(graphics, this.font,
				KitConfig.dimensionLabel(listFilter) + "没有匹配地点，可切到「全部」", center, layout.listTop() + 8, 0xA0A0A0);
		} else if (countPlaces(listFilter) == 0) {
			KitUi.centered(graphics, font, "没有匹配地点，可清空名称搜索", center, layout.listTop() + 8, 0xA0A0A0);
		}
	}

	/** 回车保存地点。 */
	@Override
	protected boolean onEnterPressed() {
		if (!editorOpen) return false;
		savePlace();
		return true;
	}

	/** 新增或覆盖同名地点。 */
	private void savePlace() {
		String name = placeName.getValue().trim();
		if (name.isEmpty()) {
			showNotice("请先填写地点名称", 0xFF5555);
			return;
		}
		try {
			double x = KitUi.parse(targetX, "目标 X", -30_000_000.0, 30_000_000.0);
			double z = KitUi.parse(targetZ, "目标 Z", -30_000_000.0, 30_000_000.0);
			double y = KitUi.parse(cruiseY, "巡航 Y", -64.0, 2048.0);
			boolean added = config.upsertPlace(name, x, z, y, draftDimension);
			showNotice((added ? "已保存地点：" : "已更新地点：") + name
				+ "（" + KitConfig.dimensionLabel(draftDimension) + "）", 0x55FF55);
			editorOpen = false;
			rebuildWidgets();
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
		}
	}

	/** 用当前位置填坐标与维度。 */
	private void useCurrentPosition() {
		if (this.minecraft.player == null) return;
		targetX.setValue(KitUi.formatNumber(this.minecraft.player.getX()));
		targetZ.setValue(KitUi.formatNumber(this.minecraft.player.getZ()));
		cruiseY.setValue(KitUi.formatNumber(this.minecraft.player.getY()));
		draftDimension = currentDimensionId();
		showNotice("已填入当前位置（" + KitConfig.dimensionLabel(draftDimension) + "）", 0x55FFFF);
		rebuildWidgets();
	}

	/** 把表单写入巡航目标，不起飞。 */
	private void applyAsTarget() {
		try {
			config.targetX = KitUi.parse(targetX, "目标 X", -30_000_000.0, 30_000_000.0);
			config.targetZ = KitUi.parse(targetZ, "目标 Z", -30_000_000.0, 30_000_000.0);
			config.cruiseY = KitUi.parse(cruiseY, "巡航 Y", -64.0, 2048.0);
			config.hasTarget = true;
			config.save();
			showNotice("已设为主界面当前目标，返回后可直接开始", 0x55FF55);
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
		}
	}

	/** 把已存地点填回表单。 */
	private void loadPlace(KitConfig.SavedPlace place) {
		draftName = place.name;
		draftX = KitUi.formatNumber(place.x); draftZ = KitUi.formatNumber(place.z); draftY = KitUi.formatNumber(place.cruiseY);
		placeName = targetX = targetZ = cruiseY = null; // Do not overwrite the selected row with old editor drafts during init().
		editorOpen = true;
		draftDimension = KitConfig.normalizeDimension(place.dimension);
		if (draftDimension.isEmpty()) draftDimension = currentDimensionId();
		showNotice("已载入「" + place.name + "」（" + KitConfig.dimensionLabel(place.dimension) + "）", 0x55FFFF);
		rebuildWidgets();
		setInitialFocus(placeName);
	}

	/** 飞往该地点。 */
	private void travel(KitConfig.SavedPlace place) {
		if (wrongDimension(place)) return;
		StructureGuide guide = KitClient.structureGuide();
		if (guide != null) guide.stop();
		config.targetX = place.x;
		config.targetZ = place.z;
		config.cruiseY = place.cruiseY;
		config.hasTarget = true;
		config.save();
		controller.start(this.minecraft, place.x, place.z, place.cruiseY);
		this.minecraft.setScreen(null);
	}

	/** 对地点开结构指引箭头。 */
	private void startGuide(KitConfig.SavedPlace place) {
		if (wrongDimension(place)) return;
		StructureGuide guide = KitClient.structureGuide();
		if (guide == null) return;
		guide.start(place.name, (int)Math.round(place.x), (int)Math.round(place.z));
		this.minecraft.setScreen(null);
	}

	/** 地点维度与当前世界是否不符。 */
	private boolean wrongDimension(KitConfig.SavedPlace place) {
		String dest = KitConfig.normalizeDimension(place.dimension);
		String here = currentDimensionId();
		if (dest.isEmpty() || here.isEmpty() || dest.equals(here)) return false;
		showNotice("「" + place.name + "」在" + KitConfig.dimensionLabel(dest)
			+ "，你现在在" + KitConfig.dimensionLabel(here), 0xFF5555);
		return true;
	}

	/** 删除地点。 */
	private void delete(KitConfig.SavedPlace place) {
		config.removePlace(place.name);
		showNotice("已删除：" + place.name, 0xFFFF55);
		rebuildWidgets();
	}

	/** 当前世界维度 id。 */
	private String currentDimensionId() {
		if (this.minecraft == null || this.minecraft.level == null) return "";
		return KitConfig.normalizeDimension(this.minecraft.level.dimension().identifier().toString());
	}

	/** 地点可滚动列表。 */
	private final class PlaceList extends ContainerObjectSelectionList<PlaceList.Row> {
		private PlaceList(Minecraft minecraft, int width, int height, int y) {
			super(minecraft, width, height, y, SavedPlacesLayout.ROW_HEIGHT);
			this.centerListVertically = false;
		}

		/** 按过滤与搜索重建行。 */
		private void populate() {
			clearEntries();
			String lastHeader = null;
			boolean grouped = FILTER_ALL.equals(listFilter);
			String q = listSearchText == null ? "" : listSearchText.trim().toLowerCase(Locale.ROOT);
			for (KitConfig.SavedPlace place : config.savedPlaces) {
				String dim = KitConfig.normalizeDimension(place.dimension);
				if (!FILTER_ALL.equals(listFilter) && !dim.equals(listFilter)) continue;
				if (!q.isEmpty() && !place.name.toLowerCase(Locale.ROOT).contains(q)) continue;
				if (grouped) {
					String header = KitConfig.dimensionLabel(dim);
					if (!header.equals(lastHeader)) {
						addEntry(new Header(header));
						lastHeader = header;
					}
				}
				addEntry(new PlaceRow(place));
			}
		}

		/** 列表行最大宽度。 */
		@Override
		public int getRowWidth() {
			return Math.max(1, this.width - 16);
		}

		/** 列表行基类。 */
		private abstract class Row extends ContainerObjectSelectionList.Entry<Row> {
		}

		/** 分组标题行。 */
		private final class Header extends Row {
			private final String title;

			private Header(String title) {
				this.title = title;
			}

			/** 画维度分组标题。 */
			@Override
			public void extractContent(GuiGraphicsExtractor graphics, int mouseX, int mouseY, boolean hovered, float delta) {
				graphics.text(font, title, getContentX(), getContentYMiddle() - 4, KitUi.argb(0xFFFFCC33));
			}

			/** 分组行无子控件。 */
			@Override
			public List<? extends GuiEventListener> children() {
				return List.of();
			}

			/** 分组行无旁白控件。 */
			@Override
			public List<? extends NarratableEntry> narratables() {
				return List.of();
			}
		}

		/** 地点行：指引/编辑/飞往/删除。 */
		private final class PlaceRow extends Row {
			private final KitConfig.SavedPlace place;
			private final Button guide;
			private final Button edit;
			private final Button go;
			private final Button remove;

			private PlaceRow(KitConfig.SavedPlace place) {
				this.place = place;
				this.guide = Button.builder(Component.literal("指引"), button -> startGuide(place))
					.bounds(0, 0, 36, 20)
					.tooltip(Tooltip.create(Component.literal("不自动走。字幕和箭头显示方向、距离。")))
					.build();
				this.edit = Button.builder(Component.literal("编辑"), button -> loadPlace(place)).bounds(0, 0, 36, 20)
					.tooltip(Tooltip.create(Component.literal(place.name + "\nX " + KitUi.formatNumber(place.x) + "  Z " + KitUi.formatNumber(place.z)
						+ "  Y " + KitUi.formatNumber(place.cruiseY) + "\n" + KitConfig.dimensionLabel(place.dimension)))).build();
				this.go = Button.builder(Component.literal("前往"), button -> travel(place))
					.bounds(0, 0, 36, 20)
					.tooltip(Tooltip.create(Component.literal("按收藏的巡航高度自动飞过去。")))
					.build();
				this.remove = Button.builder(Component.literal("删除"), button -> delete(place)).bounds(0, 0, 36, 20).build();
			}

			/** 画地点摘要与右侧按钮。 */
			@Override
			public void extractContent(GuiGraphicsExtractor graphics, int mouseX, int mouseY, boolean hovered, float delta) {
				String description = String.format(Locale.ROOT, "%s  X %.0f  Z %.0f  Y %.0f",
					place.name, place.x, place.z, place.cruiseY);
				graphics.text(font, KitUi.fit(font, description, SavedPlacesLayout.textWidth(getContentRight() - getContentX())),
					getContentX(), getContentYMiddle() - 4, KitUi.argb(hovered ? 0xFFFF55 : 0xFFFFFF));
				int buttonY = getContentYMiddle() - 10;
				remove.setPosition(getContentRight() - 38, buttonY);
				go.setPosition(getContentRight() - 78, buttonY);
				edit.setPosition(getContentRight() - 118, buttonY);
				guide.setPosition(getContentRight() - 158, buttonY);
				guide.extractRenderState(graphics, mouseX, mouseY, delta);
				edit.extractRenderState(graphics, mouseX, mouseY, delta);
				go.extractRenderState(graphics, mouseX, mouseY, delta);
				remove.extractRenderState(graphics, mouseX, mouseY, delta);
			}

			/** 行内指引/编辑/前往/删除按钮。 */
			@Override
			public List<? extends GuiEventListener> children() {
				return List.of(guide, edit, go, remove);
			}

			/** 旁白包含行内按钮。 */
			@Override
			public List<? extends NarratableEntry> narratables() {
				return List.of(guide, edit, go, remove);
			}
		}
	}
}
