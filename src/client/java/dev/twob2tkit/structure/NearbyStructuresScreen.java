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
		openUnifiedSearch();
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
	private boolean openUnifiedSearch() {
		dimension = currentDimension(); kind = config.lastStructureKind(dimension);
		String[] seed = {scout != null && scout.store().crackedSeed != null ? scout.store().crackedSeed.toString() : ""};
		var kinds = StructureLocator.Kind.forDimension(dimension);
		var page = new dev.twob2tkit.KitFormScreen(parent, "附近结构 · 搜索", "种子推算的是候选位置；未加载区块可能与服务器实际地形不同。")
			.bind(config).recordDraft().id("structure-search:" + dimension);
		page.edit("完整世界种子", "请输入完整整数种子，不是种子哈希。", () -> seed[0], value -> {
			if (SeedScout.parseSeed(value) == null) throw new IllegalArgumentException("请输入有效的完整世界种子");
		}, value -> seed[0] = value.trim());
		page.choiceInput("结构类型", "按当前维度列出可选结构。", java.util.Arrays.stream(kinds).map(k -> k.label).toArray(String[]::new),
			() -> kind.label, value -> kind = java.util.Arrays.stream(kinds).filter(k -> k.label.equals(value)).findFirst().orElse(kind));
		page.slider("搜索半径（格）", "256–32768。扩大范围可能增加计算时间。", 256, 32768, () -> config.structureSearchRadius, value -> config.structureSearchRadius = value);
		page.choiceInput("方向", "以搜索时人物的位置判断方向。", java.util.Arrays.stream(CompassDir.values()).map(d -> d.label).toArray(String[]::new),
			() -> CompassDir.from(config.structureSearchDir).label, value -> config.structureSearchDir = java.util.Arrays.stream(CompassDir.values()).filter(d -> d.label.equals(value)).findFirst().orElse(CompassDir.ALL).id);
		page.bool("只看没去过的", "与结构标记里的访问状态共用。", () -> config.structureHideVisited, value -> config.structureHideVisited = value);
		page.bool("采集已加载结构线索", "默认关闭。仅在此侦察页或结构指引期间缓慢采集；已有完整种子时停止。",
			() -> config.seedScoutEnabled, value -> config.seedScoutEnabled = value);
		if(scout!=null) scout.requestScanningFor(page);
		page.submit("查找结构", () -> {
			if (minecraft.player == null || minecraft.level == null || currentDimension() != dimension) { page.message("请进入对应维度后重新打开搜索", 0xFF7777); return; }
			seedBox = KitUi.field(font, 0, 0, 100, "种子", seed[0], 24);
			radiusBox = KitUi.field(font, 0, 0, 100, "半径", Integer.toString(config.structureSearchRadius), 8);
			config.setLastStructureKind(kind); config.save(); foundKey = null; resultFilterText = ""; refreshHits();
			showUnifiedResults(page);
		});
		page.action("结构标记", "查看已去过的位置和备注。", () -> dev.twob2tkit.UiFeature.STRUCTURE_MARKS.open(page));
		minecraft.gui.setScreen(page); return true;
	}
    private List<StructureLocator.Hit> visibleCandidates() {
        return found.stream().filter(hit -> {
            var mark = config.structureMark(markKind(hit),hit.x(),hit.z());
            return !config.structureHideVisited || mark == null || !mark.visited;
        }).toList();
    }

	private void showUnifiedResults(Screen searchPage) {
		var list = new dev.twob2tkit.KitCollectionScreen<StructureLocator.Hit>(searchPage, config, "structure-results:" + kind,
			kind.label + " · 候选结果", truncated ? "最多显示 500 项，可缩小范围" : "打开详情不会自动前往",
			this::visibleCandidates,
			hit -> (StructureLocator.isEndCity(hit.kind()) ? "待核实 · " : "") + hit.label() + "  " + hit.x() + " " + hit.z() + " · " + hit.distance() + " 格", NearbyStructuresScreen::hitHint,
			hit -> hit.label() + " " + hit.x() + " " + hit.z() + " " + hit.distance()
				+ " " + (minecraft.player == null ? "" : CompassDir.bearingLabel(minecraft.player.getBlockX(), minecraft.player.getBlockZ(), hit.x(), hit.z())));
		list.onOpen(hit -> {
			var detail = new dev.twob2tkit.KitFormScreen(list, hit.label(), "结构候选详情，不保证服务器未加载地形与种子推算一致。")
				.bind(config).id("structure-detail:" + markKind(hit) + ":" + hit.x() + ":" + hit.z());
			detail.note("X " + hit.x() + "  Z " + hit.z() + " · 搜索时距离 " + hit.distance() + " 格"); detail.note(hitHint(hit));
			var savedMark = config.structureMark(markKind(hit), hit.x(), hit.z());
			if (savedMark != null) detail.note((savedMark.visited ? "已去过" : "尚未标记去过") + "；备注：" + (savedMark.note == null ? "" : savedMark.note));
			detail.action("编辑备注", "保存本地备注。", () -> minecraft.gui.setScreen(new StructureNoteScreen(list, config, markKind(hit), hit)));
			detail.action("复制坐标", "只复制，不发送命令。", () -> { copyHit(hit); detail.message("已复制坐标", 0x77DDCC); });
			minecraft.gui.setScreen(detail);
		});
		list.action("指引", "只显示方向和距离。", this::startGuide, hit -> currentDimension() == dimension);
		list.action("前往", StructureLocator.isEndCity(kind)
            ? "依序巡航并核查候选。发现活潜影贝后停留。"
            : "按当前维度巡航高度前往。", this::cruiseTo, hit -> currentDimension() == dimension);
		list.action("已去", "切换去过状态。", hit -> { var mark = config.ensureStructureMark(markKind(hit), hit.x(), hit.z()); mark.visited = !mark.visited; config.saveStructureMarks(); list.refresh(); }, hit -> true);
		list.add("搜索设置", () -> minecraft.gui.setScreen(searchPage));
		list.footer("Chunkbase", this::openChunkbase);
		list.footer("停止指引", () -> { if (KitClient.structureGuide() != null) KitClient.structureGuide().stop(); list.message("已停止指引"); });
		minecraft.gui.setScreen(list);
	}

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
        if (rejectEndCityMiss(hit)) return;
		StructureGuide guide = KitClient.structureGuide();
		if (guide == null) return;
		guide.start(hit.label(), hit.x(), hit.z());
		this.minecraft.gui.setScreen(null);
		showNotice("已开始指引 " + hit.label() + "，字幕会显示方向和距离", 0x55FFFF);
	}

	/** 对命中开高空巡航。 */
	private void cruiseTo(StructureLocator.Hit hit) {
        if (StructureLocator.isEndCity(hit.kind())) {
            var candidates = visibleCandidates();
            int selected = candidates.indexOf(hit);
            if (selected < 0) return;
            controller.startEndCitySearch(minecraft,candidates.subList(selected,candidates.size()),
                Math.max(cruiseYForDimension(),minecraft.player.getY()));
        } else {
            controller.start(minecraft,hit.x()+.5,hit.z()+.5,cruiseYForDimension());
        }
		StructureGuide guide = KitClient.structureGuide();
		if (guide != null) guide.stop();
		this.minecraft.gui.setScreen(null);
	}

    private boolean rejectEndCityMiss(StructureLocator.Hit hit) {
        if (minecraft.level == null || !StructureLocator.isEndCity(hit.kind())
                || StructureLocator.keepLoadedHit(minecraft.level,hit)) return false;
        var text = net.minecraft.network.chat.Component.literal("附近区块已核对，未发现末地城建筑，请重新搜索");
        minecraft.gui.hud.setOverlayMessage(text,false);
        if (minecraft.player != null) minecraft.player.sendSystemMessage(text);
        return true;
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
			return "按种子推算城和船。已加载且没有末地城建筑的候选会被移除。点击复制坐标。";
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
