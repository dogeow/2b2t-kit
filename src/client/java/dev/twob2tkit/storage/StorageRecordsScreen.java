package dev.twob2tkit.storage;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;

import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitTab;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.structure.StructureGuide;

/** 仓库记录列表与搜索。 */
public final class StorageRecordsScreen extends KitHudScreen {
	private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("MM-dd HH:mm").withZone(ZoneId.systemDefault());
	private static final int ROW_HEIGHT = 36;
	private static final int TEXT_RIGHT = 167;
	private static final int ICON_LEFT = 168;
	private static final int ICON_RIGHT = 228;
	private final KitConfig config;
	private EditBox search;
	private String draftQuery = "";
	private int page;
	private int pageSize;

	/** 打开仓库记录列表屏。 */
	public StorageRecordsScreen(Screen parent, KitConfig config) {
		super(Component.literal("twob2tkit 仓库记录"), parent);
		this.config = config;
	}

	@Override
	/** 助手相关标签。 */
	protected KitTab currentTab() {
		return parent == null ? KitTab.STORAGE : null;
	}

	@Override
	/** 搜索、列表与详情入口。 */
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("STORAGE", parent)) return;
		if (parent == null) addTabBar(KitTab.STORAGE);
		if (this.minecraft != null && this.minecraft.level != null) {
			int removed = config.pruneMissingStorage(
				this.minecraft.level, this.minecraft.level.dimension().identifier().toString());
			if (removed > 0) showNotice("已清掉 " + removed + " 个不在的箱子/潜影盒", 0xFFFF55);
		}
		int left = panelLeft(380);
		if (search != null) draftQuery = search.getValue();
		int searchY = parent == null ? contentTop() : bodyTop(36);
		int listY = searchY + 28;
		pageSize = Math.max(2, Math.min(6, (footerButtonY() - listY - 40) / ROW_HEIGHT));
		List<KitConfig.StorageSnapshot> visible = visibleSnapshots();
		page = Math.max(0, Math.min(page, maxPage(visible)));
		int start = page * pageSize;
		int end = Math.min(visible.size(), start + pageSize);
		for (int i = start; i < end; i++) {
			KitConfig.StorageSnapshot snapshot = visible.get(i);
			int y = listY + (i - start) * ROW_HEIGHT;
			String detail = detailLine(snapshot, draftQuery.trim());
			addRenderableWidget(Button.builder(Component.literal("查看"), button -> open(snapshot)).bounds(left + 232, y, 44, 20)
				.tooltip(Tooltip.create(Component.literal(detail)))
				.build());
			addRenderableWidget(Button.builder(Component.literal("指引"), button -> startGuide(snapshot)).bounds(left + 280, y, 44, 20)
				.tooltip(Tooltip.create(Component.literal("只指路，不飞、不挖。字幕和箭头显示方向、距离。")))
				.build())
				.active = sameDimension(snapshot);
			addRenderableWidget(Button.builder(Component.literal("删除"), button -> delete(snapshot)).bounds(left + 328, y, 44, 20).build());
		}

		search = addRenderableWidget(KitUi.field(this.font, left, searchY, 380, "搜索物品", draftQuery, 40));
		search.setHint(Component.literal("搜备注、颜色或物品，例如 线"));
		search.setResponder(query -> {
			if (query.equals(draftQuery)) return;
			draftQuery = query;
			page = 0;
			rebuildWidgets();
		});

		int bottomY = contentBottom();
		Button previous = addRenderableWidget(Button.builder(Component.literal("上一页"), button -> changePage(-1)).bounds(left, bottomY, 85, 20).build());
		previous.active = page > 0;
		Button next = addRenderableWidget(Button.builder(Component.literal("下一页"), button -> changePage(1)).bounds(left + 92, bottomY, 85, 20).build());
		next.active = page < maxPage(visible);
		StructureGuide guide = KitClient.structureGuide();
		if (guide != null && guide.isActive()) {
			addRenderableWidget(Button.builder(Component.literal("停指引"), button -> {
				guide.stop();
				showNotice("已关闭指引", 0xFFFF55);
			}).bounds(left + 185, bottomY, 90, 20).build());
			addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose()).bounds(left + 283, bottomY, 97, 20).build());
		} else {
			addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose()).bounds(left + 185, bottomY, 195, 20).build());
		}
		setInitialFocus(search);
	}

	@Override
	/** 画标题与摘要行。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(380);
		int center = this.width / 2;
		if (parent != null) {
			KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(8), 0xFFFFFF);
		}

		int searchY = parent == null ? contentTop() : bodyTop(36);
		int listY = searchY + 28;
		List<KitConfig.StorageSnapshot> visible = visibleSnapshots();
		int start = page * Math.max(1, pageSize);
		int end = Math.min(visible.size(), start + Math.max(1, pageSize));
		if (config.storageSnapshots.isEmpty()) {
			KitUi.centered(graphics, this.font, "还没有仓库记录；主动打开一次箱子后会出现在这里", center, listY + 28, 0xA0A0A0);
		} else if (start >= end) {
			KitUi.centered(graphics, this.font, "没有找到含「" + draftQuery.trim() + "」的箱子", center, listY + 28, 0xFFFF55);
		} else {
			String query = draftQuery.trim();
			for (int i = start; i < end; i++) {
				KitConfig.StorageSnapshot snapshot = visible.get(i);
				int y = listY + (i - start) * ROW_HEIGHT;
				int textX = drawColorSwatch(graphics, left, y + 4, snapshot);
				drawPreviewIcons(graphics, left + ICON_LEFT, y + 8, left + ICON_RIGHT, snapshot, query);
				String line = StorageLabels.headline(snapshot);
				int textWidth = left + TEXT_RIGHT - textX;
				KitUi.text(graphics, this.font, KitUi.fit(this.font, line, textWidth), textX, y + 2, 0xFFFFFF);
				String coordLine = dimensionLabel(snapshot.dimension) + "  "
					+ snapshot.x + ", " + snapshot.y + ", " + snapshot.z;
				KitUi.text(graphics, this.font, KitUi.fit(this.font, coordLine, textWidth), textX, y + 14, 0x55FFFF);
				String summary = detailLine(snapshot, query);
				if (!summary.isEmpty()) {
					KitUi.text(graphics, this.font, KitUi.fit(this.font, summary, textWidth), textX, y + 24, 0xA0A0A0);
				}
			}
		}
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, contentBottom() - 14, noticeColor);
		else KitUi.centered(graphics, this.font, "第 " + (page + 1) + " / " + (maxPage(visible) + 1) + " 页", center, contentBottom() - 14, 0xA0A0A0);
	}

	private static final int PREVIEW_ICON_STEP = 16;

	/** 列表行里画匹配搜索的物品图标预览。 */
	private static void drawPreviewIcons(GuiGraphicsExtractor graphics, int x, int y, int maxX,
		KitConfig.StorageSnapshot snapshot, String query) {
		int drawn = 0;
		for (KitConfig.StoredItem item : snapshot.items) {
			if (!query.isEmpty() && !contains(item.name, query) && !contains(item.id, query)) continue;
			ItemStack stack = StorageItems.stack(item);
			if (stack.isEmpty()) continue;
			int ix = x + drawn * PREVIEW_ICON_STEP;
			if (ix + 16 > maxX) break;
			graphics.item(stack, ix, y);
			drawn++;
		}
	}

	/** 画颜色色块。 */
	private static int drawColorSwatch(GuiGraphicsExtractor graphics, int left, int y, KitConfig.StorageSnapshot snapshot) {
		int rgb = StorageLabels.colorRgb(snapshot.colorId);
		if (rgb == 0) return left;
		graphics.fill(left, y, left + 8, y + 8, KitUi.argb(rgb));
		graphics.fill(left, y, left + 8, y + 1, 0xFF000000);
		graphics.fill(left, y + 7, left + 8, y + 8, 0xFF000000);
		graphics.fill(left, y, left + 1, y + 8, 0xFF000000);
		graphics.fill(left + 7, y, left + 8, y + 8, 0xFF000000);
		return left + 12;
	}

	/** 按搜索过滤后的快照。 */
	private List<KitConfig.StorageSnapshot> visibleSnapshots() {
		String query = draftQuery.trim();
		if (query.isEmpty()) return config.storageSnapshots;
		List<KitConfig.StorageSnapshot> matches = new ArrayList<>();
		for (KitConfig.StorageSnapshot snapshot : config.storageSnapshots) {
			if (matchesQuery(snapshot, query)) matches.add(snapshot);
		}
		return matches;
	}

	/** 快照是否匹配搜索词。 */
	private static boolean matchesQuery(KitConfig.StorageSnapshot snapshot, String query) {
		if (contains(StorageLabels.headline(snapshot), query)) return true;
		if (contains(snapshot.note, query) || contains(snapshot.colorId, query)) return true;
		if (contains(StorageLabels.colorLabel(snapshot.colorId), query)) return true;
		if (contains(snapshot.title, query)) return true;
		if (contains(dimensionLabel(snapshot.dimension), query)) return true;
		if (contains(snapshot.x + "," + snapshot.y + "," + snapshot.z, query)) return true;
		if (contains(snapshot.x + ", " + snapshot.y + ", " + snapshot.z, query)) return true;
		for (KitConfig.StoredItem item : snapshot.items) {
			if (contains(item.name, query) || contains(item.id, query)) return true;
		}
		return false;
	}

	/** 快照一行摘要。 */
	private static String detailLine(KitConfig.StorageSnapshot snapshot, String query) {
		int total = snapshot.items.stream().mapToInt(item -> item.count).sum();
		String time = TIME_FORMAT.format(Instant.ofEpochMilli(snapshot.lastSeenEpochMillis));
		if (query.isEmpty()) {
			return snapshot.items.size() + " 类 / " + total + " 件  |  " + time;
		}
		List<String> hits = new ArrayList<>();
		int matched = 0;
		for (KitConfig.StoredItem item : snapshot.items) {
			if (!contains(item.name, query) && !contains(item.id, query)) continue;
			matched += item.count;
			if (hits.size() < 3) hits.add(item.name + " × " + item.count);
		}
		if (hits.isEmpty()) {
			return snapshot.items.size() + " 类 / " + total + " 件  |  " + time;
		}
		return String.join("、", hits) + "  |  共 " + matched + " 件  |  " + time;
	}

	/** 快照是否含某物品。 */
	private static boolean contains(String text, String query) {
		if (text == null || text.isEmpty() || query == null || query.isEmpty()) return false;
		return text.toLowerCase(Locale.ROOT).contains(query.toLowerCase(Locale.ROOT));
	}

	/** 打开详情。 */
	private void open(KitConfig.StorageSnapshot snapshot) {
		this.minecraft.setScreen(new StorageDetailScreen(this, snapshot));
	}

	/** 开始走向该存储。 */
	private void startGuide(KitConfig.StorageSnapshot snapshot) {
		if (!sameDimension(snapshot)) {
			showNotice("当前维度不同，无法指引", 0xFFFF55);
			return;
		}
		StructureGuide guide = KitClient.structureGuide();
		if (guide == null) return;
		guide.start(StorageLabels.headline(snapshot), snapshot.x, snapshot.y, snapshot.z);
		this.minecraft.setScreen(null);
	}

	/** 删除记录。 */
	private void delete(KitConfig.StorageSnapshot snapshot) {
		config.storageSnapshots.removeIf(existing -> existing.key().equals(snapshot.key()));
		config.save();
		showNotice("已删除仓库记录", 0xFFFF55);
		page = Math.min(page, maxPage(visibleSnapshots()));
		rebuildWidgets();
	}

	/** 是否同一维度。 */
	private boolean sameDimension(KitConfig.StorageSnapshot snapshot) {
		return this.minecraft.level != null && this.minecraft.level.dimension().identifier().toString().equals(snapshot.dimension);
	}

	/** 翻页。 */
	private void changePage(int direction) {
		page = Math.max(0, Math.min(maxPage(visibleSnapshots()), page + direction));
		rebuildWidgets();
	}

	@Override
	/** 滚轮翻页。 */
	public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
		if (scrollY > 0) changePage(-1);
		else if (scrollY < 0) changePage(1);
		return true;
	}

	/** 最大页。 */
	private int maxPage(List<KitConfig.StorageSnapshot> visible) {
		if (pageSize <= 0 || visible.isEmpty()) return 0;
		return (visible.size() - 1) / pageSize;
	}

	/** 维度中文名。 */
	public static String dimensionLabel(String dimension) {
		return switch (dimension) {
			case "minecraft:overworld" -> "主世界";
			case "minecraft:the_nether" -> "下界";
			case "minecraft:the_end" -> "末地";
			default -> dimension;
		};
	}
}
