package dev.twob2tkit.structure;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.List;
import java.util.Locale;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitController;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.nether.NetherRoofAssist;

/**
 * 附近原版结构候选列表：可开 Chunkbase、指引、巡航，并管理去过/备注。
 */
public final class NearbyStructuresScreen extends KitHudScreen {
	private static final int RESULT_LIMIT = 500;
	private final KitConfig config;
	private final KitController controller;
	private final SeedScout scout;
	private EditBox seedBox;
	private EditBox radiusBox;
	private EditBox resultFilter;
	private StructureLocator.Dimension dimension = StructureLocator.Dimension.OVERWORLD;
	private StructureLocator.Kind kind = StructureLocator.Kind.VILLAGE;
	private boolean dimensionReady;
	private List<StructureLocator.Hit> found = List.of();
	private List<StructureLocator.Hit> hits = List.of();
	/** 上次搜索的「种子 + 维度 + 类型 + 区块 + 半径 + 方向」，没变就直接复用结果。 */
	private String foundKey;
	private int page;
	private int shownCount;
	private int shownPages = 1;
	private boolean truncated;
	/** 结构类型选择区是否展开（手风琴，默认收起）。 */
	private boolean kindsExpanded;
	private String resultFilterText = "";

	public NearbyStructuresScreen(Screen parent, KitConfig config, KitController controller, SeedScout scout) {
		super(Component.literal("附近结构"), parent);
		this.config = config;
		this.controller = controller;
		this.scout = scout;
	}

	@Override
	/** 种子/半径/类型与结果列表按钮。 */
	protected void init() {
		if (!dimensionReady) {
			dimension = currentDimension();
			kind = config.lastStructureKind(dimension);
			dimensionReady = true;
		}
		commitSearchOptions();
		if (seedBox != null && resultFilter != null) resultFilterText = resultFilter.getValue();
		int left = panelLeft(340);
		int top = contentTop();
		String seedText = scout != null && scout.store().crackedSeed != null
			? String.valueOf(scout.store().crackedSeed)
			: "";
		seedBox = addRenderableWidget(KitUi.field(this.font, left, top, 226, "世界种子", seedText, 24));
		seedBox.setHint(Component.literal("完整世界种子"));
		addRenderableWidget(Button.builder(Component.literal("查找"), button -> {
			commitSearchOptions();
			foundKey = null;
			rebuildWidgets();
		}).bounds(left + 232, top, 108, 20)
			.tooltip(Tooltip.create(Component.literal("改了种子、半径或者走远了点这里重搜。结果会缓存，翻页和打标记不会重复搜。")))
			.build());

		int y = top + 24;
		StructureLocator.Kind[] kinds = StructureLocator.Kind.forDimension(dimension);
		addRenderableWidget(Button.builder(
			Component.literal("结构：" + kind.label + (kindsExpanded ? " ▲ 收起" : " ▼ 展开")),
			button -> {
				kindsExpanded = !kindsExpanded;
				rebuildWidgets();
			}).bounds(left, y, 340, 20)
			.tooltip(Tooltip.create(Component.literal(kindsExpanded
				? "收起结构列表，把空间留给搜索结果"
				: "展开切换村庄、神殿、海底废墟等结构类型")))
			.build());
		y += 24;
		if (kindsExpanded) {
			for (int i = 0; i < kinds.length; i++) {
				StructureLocator.Kind next = kinds[i];
				int col = i % 4;
				int row = i / 4;
				Button button = addRenderableWidget(Button.builder(Component.literal(next.label), ignored -> {
					commitSearchOptions();
					kind = next;
					config.setLastStructureKind(next);
					config.save();
					page = 0;
					kindsExpanded = false;
					rebuildWidgets();
				}).bounds(left + col * 86, y + row * 22, 82, 20).build());
				button.active = next != kind;
			}
			y += ((kinds.length + 3) / 4) * 22 + 4;
		}
		y += 2;
		label(left, y + 6, 28, "半径", 0xA0A0A0);
		radiusBox = addRenderableWidget(KitUi.field(
			this.font, left + 28, y, 60, "搜索半径",
			String.valueOf(KitConfig.clampStructureRadius(config.structureSearchRadius)), 5));
		radiusBox.setHint(Component.literal("格"));
		radiusBox.setTooltip(Tooltip.create(Component.literal(
			"搜索半径，单位格。默认 4096。要塞建议 16000。范围 256–32768，太大第一次会卡一下。")));
		CompassDir dir = CompassDir.from(config.structureSearchDir);
		addRenderableWidget(Button.builder(Component.literal("方向：" + dir.label), button -> {
			commitSearchOptions();
			config.structureSearchDir = dir.next().id;
			config.save();
			page = 0;
			foundKey = null;
			rebuildWidgets();
		}).bounds(left + 92, y, 124, 20)
			.tooltip(Tooltip.create(Component.literal("只列出这个方向上的结构。点一下切换：全方向 → 北 → 东北 → 东…")))
			.build());
		String mapLabel = dimension == StructureLocator.Dimension.NETHER ? "打开下界地形图" : "打开 Chunkbase";
		addRenderableWidget(Button.builder(Component.literal(KitUi.fit(this.font, mapLabel, 112)), button -> openChunkbase())
			.bounds(left + 220, y, 120, 20)
			.tooltip(Tooltip.create(Component.literal("用当前种子、坐标和 Seedcracker 里的游戏版本打开 Chunkbase。地狱会切到下界图。")))
			.build());

		y += 24;
		addRenderableWidget(Button.builder(Component.literal("复制传送"), button -> copySelected())
			.bounds(left, y, 104, 20).build());
		addRenderableWidget(Button.builder(Component.literal(config.structureHideVisited ? "只看没去过 √" : "只看没去过"), button -> {
			config.structureHideVisited = !config.structureHideVisited;
			config.save();
			page = 0;
			rebuildWidgets();
		}).bounds(left + 108, y, 116, 20)
			.tooltip(Tooltip.create(Component.literal("打开后，标记过「已去」的结构不再出现在结果里。")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("标记"), button ->
			this.minecraft.setScreen(new StructureMarksScreen(this, config)))
			.bounds(left + 228, y, 112, 20)
			.tooltip(Tooltip.create(Component.literal("查看全部已标记的结构，可以逐个删除或者一次清空。")))
			.build());

		y += 24;
		resultFilter = addRenderableWidget(KitUi.field(this.font, left, y, 340, "过滤结果",
			resultFilterText, 48));
		resultFilter.setHint(Component.literal("名称 / 坐标 / 方位"));
		resultFilter.setResponder(text -> {
			resultFilterText = text;
			page = 0;
			rebuildWidgets();
		});

		refreshHits();
		int originX = this.minecraft.player == null ? 0 : this.minecraft.player.getBlockX();
		int originZ = this.minecraft.player == null ? 0 : this.minecraft.player.getBlockZ();
		int listTop = y + 24;
		int listBottom = footerButtonY() - CONTROL_ROW_STEP - 4;
		int pageSize = Math.max(3, (listBottom - listTop) / 22);
		int maxPage = hits.isEmpty() ? 0 : (hits.size() - 1) / pageSize;
		page = Math.max(0, Math.min(page, maxPage));
		shownCount = hits.size();
		shownPages = maxPage + 1;
		int start = page * pageSize;
		int end = Math.min(hits.size(), start + pageSize);
		int rowY = listTop;
		for (int i = start; i < end; i++) {
			StructureLocator.Hit hit = hits.get(i);
			KitConfig.StructureMark mark = config.structureMark(markKind(hit), hit.x(), hit.z());
			boolean visited = mark != null && mark.visited;
			String note = mark == null || mark.note == null ? "" : mark.note;
			String bearing = CompassDir.bearingLabel(originX, originZ, hit.x(), hit.z());
			String rowText = (visited ? "√" : "") + hit.label() + "  " + hit.distance() + "格 " + bearing + "  " + hit.x() + " " + hit.z();
			String rowTip = hit.label() + "  " + hit.distance() + "格  " + bearing + "  " + hit.x() + " " + hit.z()
				+ (note.isEmpty() ? "" : "\n备注：" + note)
				+ "\n" + hitHint(hit);
			addRenderableWidget(Button.builder(
				Component.literal(KitUi.fit(this.font, rowText, 150)),
				button -> copyHit(hit)
			).bounds(left, rowY, 158, 20)
				.tooltip(Tooltip.create(Component.literal(rowTip)))
				.build());
			addRenderableWidget(Button.builder(Component.literal(visited ? "已去" : "没去"), button -> {
				KitConfig.StructureMark toggled = config.ensureStructureMark(markKind(hit), hit.x(), hit.z());
				toggled.visited = !toggled.visited;
				config.saveStructureMarks();
				rebuildWidgets();
			}).bounds(left + 162, rowY, 34, 20)
				.tooltip(Tooltip.create(Component.literal("点一下切换去过/没去过。开了「只看没去过」时，已去的会被藏起来。")))
				.build());
			addRenderableWidget(Button.builder(Component.literal(note.isEmpty() ? "备注" : "备注*"), button ->
				this.minecraft.setScreen(new StructureNoteScreen(this, config, markKind(hit), hit))
			).bounds(left + 200, rowY, 38, 20)
				.tooltip(Tooltip.create(Component.literal(note.isEmpty() ? "给这个结构写备注" : "备注：" + note)))
				.build());
			addRenderableWidget(Button.builder(Component.literal("指引"), button -> startGuide(hit))
				.bounds(left + 242, rowY, 44, 20)
				.tooltip(Tooltip.create(Component.literal("不自动走。字幕显示方向、距离和该左转还是右转。")))
				.build());
			addRenderableWidget(Button.builder(Component.literal("跑路"), button -> cruiseTo(hit))
				.bounds(left + 290, rowY, 50, 20)
				.tooltip(Tooltip.create(Component.literal("按当前巡航高度自动飞过去。")))
				.build());
			rowY += 22;
		}

		int pageRowY = footerButtonY() - CONTROL_ROW_STEP;
		StructureGuide guide = KitClient.structureGuide();
		if (guide != null && guide.isActive()) {
			addRenderableWidget(Button.builder(Component.literal("上一页"), button -> {
				page--;
				rebuildWidgets();
			}).bounds(left, pageRowY, 108, 20).build()).active = page > 0;
			addRenderableWidget(Button.builder(Component.literal("下一页"), button -> {
				page++;
				rebuildWidgets();
			}).bounds(left + 114, pageRowY, 108, 20).build()).active = page < maxPage;
			addRenderableWidget(Button.builder(Component.literal("停指引"), button -> {
				guide.stop();
				showNotice("已关闭指引", 0xFFFF55);
			}).bounds(left + 228, pageRowY, 112, 20).build());
		} else {
			addRenderableWidget(Button.builder(Component.literal("上一页"), button -> {
				page--;
				rebuildWidgets();
			}).bounds(left, pageRowY, 166, 20).build()).active = page > 0;
			addRenderableWidget(Button.builder(Component.literal("下一页"), button -> {
				page++;
				rebuildWidgets();
			}).bounds(left + 174, pageRowY, 166, 20).build()).active = page < maxPage;
		}
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left, footerButtonY(), 340, 20).build());
	}

	@Override
	/** 底栏提示 Y。 */
	protected int footerNoticeY() {
		return footerButtonY() - CONTROL_ROW_STEP - 16;
	}

	@Override
	/** 画维度、数量与说明。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		int top = contentTop();
		String dim = switch (dimension) {
			case NETHER -> "下界";
			case END -> "末地";
			case OVERWORLD -> "主世界";
		};
		String count = truncated ? "共" + shownCount + "个(上限)" : "共" + shownCount + "个";
		KitUi.centered(graphics, this.font,
			dim + " · " + kind.label + " · " + count + " · 第" + (page + 1) + "/" + shownPages + "页",
			center, top - 14, 0xFFFFFF);
		if (!notice.isEmpty()) {
			KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
		}
	}

	@Override
	/** 关界面前提交搜索选项。 */
	public void onClose() {
		commitSearchOptions();
		super.onClose();
	}

	@Override
	/** 结果区滚轮翻页。 */
	public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
		if (scrollY > 0) page = Math.max(0, page - 1);
		else if (scrollY < 0) page++;
		init();
		return true;
	}

	/** init 是唯一的搜索入口。过滤每次都重算（很便宜），真正的搜索只在 key 变化时跑。 */
	private void refreshHits() {
		Long seed = currentSeed();
		if (seed == null || this.minecraft.player == null) {
			found = List.of();
			hits = List.of();
			foundKey = null;
			truncated = false;
			return;
		}
		int originX = this.minecraft.player.getBlockX();
		int originY = this.minecraft.player.getBlockY();
		int originZ = this.minecraft.player.getBlockZ();
		int radius = currentRadius();
		CompassDir dir = CompassDir.from(config.structureSearchDir);
		String key = seed + "|" + dimension + "|" + kind + "|" + (originX >> 4) + "|" + (originY >> 4) + "|" + (originZ >> 4)
			+ "|" + radius + "|" + dir.id;
		if (!key.equals(foundKey)) {
			found = StructureLocator.nearby(
				seed, this.minecraft.level, originX, originY, originZ, kind, radius, RESULT_LIMIT,
				(x, z) -> dir.matches(originX, originZ, x, z));
			if (this.minecraft.level != null) {
				found = StructureLocator.rejectLoadedMisses(this.minecraft.level, found);
			}
			foundKey = key;
			truncated = found.size() >= RESULT_LIMIT;
		}
		hits = config.structureHideVisited
			? found.stream().filter(hit -> {
				KitConfig.StructureMark mark = config.structureMark(markKind(hit), hit.x(), hit.z());
				return mark == null || !mark.visited;
			}).toList()
			: found;
		String q = resultFilterText == null ? "" : resultFilterText.trim().toLowerCase(Locale.ROOT);
		if (!q.isEmpty()) {
			hits = hits.stream().filter(hit -> matchesResultFilter(hit, q, originX, originZ)).toList();
		}
	}

	/** 结果是否匹配过滤框。 */
	private static boolean matchesResultFilter(StructureLocator.Hit hit, String q, int originX, int originZ) {
		if (hit.label().toLowerCase(Locale.ROOT).contains(q)) return true;
		if (Integer.toString(hit.x()).contains(q) || Integer.toString(hit.z()).contains(q)) return true;
		if (Integer.toString(hit.distance()).contains(q)) return true;
		String bearing = CompassDir.bearingLabel(originX, originZ, hit.x(), hit.z());
		return bearing.toLowerCase(Locale.ROOT).contains(q);
	}

	/** 把种子半径等写回配置。 */
	private void commitSearchOptions() {
		boolean dirty = false;
		int radius = currentRadius();
		if (radius != config.structureSearchRadius) {
			config.structureSearchRadius = radius;
			dirty = true;
		}
		if (kind != null && config.lastStructureKind(kind.dimension) != kind) {
			config.setLastStructureKind(kind);
			dirty = true;
		}
		if (dirty) config.save();
	}

	/** 解析半径输入。 */
	private int currentRadius() {
		if (radiusBox != null) {
			try {
				return KitConfig.clampStructureRadius(Integer.parseInt(radiusBox.getValue().trim()));
			} catch (NumberFormatException ignored) {
			}
		}
		return KitConfig.clampStructureRadius(config.structureSearchRadius);
	}

	/** 去过/备注按坐标记，带船和普通末地城算同一座城。 */
	public static String markKind(StructureLocator.Hit hit) {
		return hit.kind().stableId();
	}

	/** 当前可用世界种子。 */
	private Long currentSeed() {
		if (seedBox != null) {
			Long typed = SeedScout.parseSeed(seedBox.getValue());
			if (typed != null) return typed;
		}
		if (scout != null && scout.store().crackedSeed != null) return scout.store().crackedSeed;
		return null;
	}

	/** 打开 Chunkbase 或下界地形图。 */
	private void openChunkbase() {
		Long seed = currentSeed();
		if (seed == null) {
			showNotice("先填完整世界种子。只有哈希种子打不开 Chunkbase 地图", 0xFF5555);
			return;
		}
		if (scout != null && scout.store().crackedSeed == null) {
			scout.tryFullSeed(Long.toString(seed));
		}
		showNotice(ChunkbaseMap.open(this.minecraft, seed), 0x55FFFF);
	}

	/** 复制当前页可见结果。 */
	private void copySelected() {
		if (hits.isEmpty()) {
			showNotice("还没有结果", 0xFF5555);
			return;
		}
		copyHit(hits.getFirst());
	}

	/** 复制单条坐标到剪贴板。 */
	private void copyHit(StructureLocator.Hit hit) {
		String command = "/tp " + hit.x() + " ~ " + hit.z();
		if (this.minecraft.keyboardHandler != null) this.minecraft.keyboardHandler.setClipboard(command);
		showNotice("已复制 " + command, 0x55FF55);
	}

	/** 对命中开 StructureGuide。 */
	private void startGuide(StructureLocator.Hit hit) {
		StructureGuide guide = KitClient.structureGuide();
		if (guide == null) return;
		guide.start(hit.label(), hit.x(), hit.z());
		this.minecraft.setScreen(null);
		showNotice("已开始指引 " + hit.label() + "，字幕会显示方向和距离", 0x55FFFF);
	}

	/** 对命中开高空巡航。 */
	private void cruiseTo(StructureLocator.Hit hit) {
		StructureGuide guide = KitClient.structureGuide();
		if (guide != null) guide.stop();
		controller.start(this.minecraft, hit.x() + 0.5, hit.z() + 0.5, cruiseYForDimension());
		this.minecraft.setScreen(null);
	}

	/** 巡航高度按维度。 */
	private double cruiseYForDimension() {
		if (this.minecraft.player == null) return config.cruiseY;
		if (dimension == StructureLocator.Dimension.NETHER) {
			if (NetherRoofAssist.onRoof(this.minecraft.player)) return NetherRoofAssist.roofCruiseY();
			return this.minecraft.player.getY();
		}
		return config.cruiseY;
	}

	/** 悬停补充说明。 */
	private static String hitHint(StructureLocator.Hit hit) {
		if (hit.kind() == StructureLocator.Kind.END_CITY || hit.kind() == StructureLocator.Kind.END_CITY_SHIP) {
			return "已按末地高地和地面高度过滤（矮岛没有城）。带船按原版城部件推算。点击复制 /tp。";
		}
		if (hit.kind() == StructureLocator.Kind.OUTPOST) {
			return "身边已加载的空点会丢掉；没加载的远点只按种子估，到了可能没有塔。点击复制 /tp。";
		}
		if (hit.kind().isNetherBiome()) {
			return "按种子估下界群系。坐标是离你最近的一块，同一片不会重复列。点击复制 /tp。";
		}
		return "点击复制 /tp。左边指引只指路，右边才自动跑。未加载区块未核对群系。";
	}

	/** 按玩家所在世界选维度。 */
	private StructureLocator.Dimension currentDimension() {
		if (this.minecraft == null || this.minecraft.level == null) return StructureLocator.Dimension.OVERWORLD;
		String path = this.minecraft.level.dimension().identifier().getPath();
		if (path.contains("nether")) return StructureLocator.Dimension.NETHER;
		if (path.contains("end")) return StructureLocator.Dimension.END;
		return StructureLocator.Dimension.OVERWORLD;
	}

	/** 结果筛选的八方向；ALL 表示不限。 */
	public enum CompassDir {
		ALL("ALL", "全方向"),
		N("N", "北"),
		NE("NE", "东北"),
		E("E", "东"),
		SE("SE", "东南"),
		S("S", "南"),
		SW("SW", "西南"),
		W("W", "西"),
		NW("NW", "西北");

		final String id;
		final String label;

		CompassDir(String id, String label) {
			this.id = id;
			this.label = label;
		}

		/** 下一个方向（循环）。 */
		CompassDir next() {
			CompassDir[] values = values();
			return values[(ordinal() + 1) % values.length];
		}

		/** 从配置 id 解析；非法则 ALL。 */
		static CompassDir from(String id) {
			if (id == null || id.isBlank()) return ALL;
			String normalized = id.trim().toUpperCase(Locale.ROOT);
			for (CompassDir dir : values()) {
				if (dir.id.equals(normalized)) return dir;
			}
			return ALL;
		}

		/** 目标相对原点是否落在本扇区。 */
		boolean matches(int originX, int originZ, int x, int z) {
			if (this == ALL) return true;
			int dx = x - originX;
			int dz = z - originZ;
			if (dx == 0 && dz == 0) return true;
			return fromDelta(dx, dz) == this;
		}

		/** 相对原点的方位中文（脚下/北/东北…）。 */
		static String bearingLabel(int originX, int originZ, int x, int z) {
			int dx = x - originX;
			int dz = z - originZ;
			if (dx == 0 && dz == 0) return "脚下";
			return fromDelta(dx, dz).label;
		}

		/** 0° 正北，90° 正东；按 45° 扇区取最近的八向。 */
		private static CompassDir fromDelta(int dx, int dz) {
			double angle = Math.toDegrees(Math.atan2(dx, -dz));
			if (angle < 0) angle += 360;
			int sector = ((int)Math.round(angle / 45.0)) & 7;
			return switch (sector) {
				case 0 -> N;
				case 1 -> NE;
				case 2 -> E;
				case 3 -> SE;
				case 4 -> S;
				case 5 -> SW;
				case 6 -> W;
				default -> NW;
			};
		}
	}

}
