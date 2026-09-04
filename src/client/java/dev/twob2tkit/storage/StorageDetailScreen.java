package dev.twob2tkit.storage;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.ItemIconButton;

/** 仓库快照详情：9 列格子展示，类似箱子界面。 */
public final class StorageDetailScreen extends KitHudScreen {
	private static final int COLS = 9;
	private static final int CELL = 22;
	private static final int SLOT = 20;
	private static final int GRID_TOP = 44;

	/** 物品网格起始 Y。 */
	private int gridTop() {
		return bodyTop(GRID_TOP);
	}

	private final KitConfig.StorageSnapshot snapshot;
	private int page;
	private int pageSize;
	private int gridLeft;

	/** 打开某条仓库记录详情。 */
	public StorageDetailScreen(Screen parent, KitConfig.StorageSnapshot snapshot) {
		super(Component.literal("twob2tkit 仓库内容"), parent);
		this.snapshot = snapshot;
	}

	@Override
	/** 分页与返回。 */
	protected void init() {
		int rows = gridRows();
		pageSize = COLS * rows;
		page = Math.max(0, Math.min(page, maxPage()));
		gridLeft = this.width / 2 - (COLS * CELL) / 2;

		int start = page * pageSize;
		for (int slot = 0; slot < pageSize; slot++) {
			int index = start + slot;
			int col = slot % COLS;
			int row = slot / COLS;
			int x = gridLeft + col * CELL;
			int y = gridTop() + row * CELL;
			if (index >= snapshot.items.size()) continue;
			KitConfig.StoredItem item = snapshot.items.get(index);
			ItemStack stack = StorageItems.stack(item);
			if (stack.isEmpty()) continue;
			String label = item.name == null || item.name.isBlank() ? item.id : item.name;
			addRenderableWidget(new ItemIconButton(
				x, y, SLOT, SLOT, stack,
				Component.literal(label + "\n× " + item.count),
				() -> {}));
		}

		int footerY = footerButtonY();
		int footerLeft = this.width / 2 - 120;
		Button previous = addRenderableWidget(Button.builder(Component.literal("上一页"), button -> changePage(-1))
			.bounds(footerLeft, footerY, 76, 20).build());
		previous.active = page > 0;
		Button next = addRenderableWidget(Button.builder(Component.literal("下一页"), button -> changePage(1))
			.bounds(footerLeft + 82, footerY, 76, 20).build());
		next.active = page < maxPage();
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(footerLeft + 164, footerY, 76, 20).build());
	}

	@Override
	/** 画标题、页码与物品格。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, StorageLabels.headline(snapshot), center, headerY(12), 0xFFFFFF);
		KitUi.centered(graphics, this.font,
			StorageRecordsScreen.dimensionLabel(snapshot.dimension) + "  X " + snapshot.x + "  Y " + snapshot.y + "  Z " + snapshot.z,
			center, headerY(27), 0x55FFFF);

		if (snapshot.items.isEmpty()) {
			KitUi.centered(graphics, this.font, "记录时容器是空的", center, gridTop() + 24, 0xA0A0A0);
		} else {
			for (int slot = 0; slot < pageSize; slot++) {
				int col = slot % COLS;
				int row = slot / COLS;
				int x = gridLeft + col * CELL;
				int y = gridTop() + row * CELL;
				drawSlotBackground(graphics, x, y);
			}
		}

		super.extractRenderState(graphics, mouseX, mouseY, delta);

		String pageText = "第 " + (page + 1) + " / " + (maxPage() + 1) + " 页";
		if (!notice.isEmpty()) pageText += "  " + notice;
		KitUi.centered(graphics, this.font, pageText, center, footerButtonY() - 22,
			notice.isEmpty() ? 0xA0A0A0 : noticeColor);
	}

	/** 画物品格底。 */
	private static void drawSlotBackground(GuiGraphicsExtractor graphics, int x, int y) {
		graphics.fill(x, y, x + SLOT, y + SLOT, 0xFF2A2A2A);
		graphics.fill(x + 1, y + 1, x + SLOT - 1, y + SLOT - 1, 0xFF1A1A1A);
	}

	/** 当前页网格行数。 */
	private int gridRows() {
		return Math.max(3, Math.min(6, (footerButtonY() - GRID_TOP - 32) / CELL));
	}

	/** 翻页。 */
	private void changePage(int direction) {
		page = Math.max(0, Math.min(maxPage(), page + direction));
		rebuildWidgets();
	}

	/** 最大页码。 */
	private int maxPage() {
		if (pageSize <= 0 || snapshot.items.isEmpty()) return 0;
		return (snapshot.items.size() - 1) / pageSize;
	}
}
