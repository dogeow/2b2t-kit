package dev.twob2tkit.surround;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.util.Mth;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

import java.util.ArrayList;
import java.util.List;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitTab;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.ItemIconButton;

/**
 * 围箱设置界面：模式、每拍块数、继续补洞、方块目录与优先级排序。
 */
public final class SurroundScreen extends KitHudScreen {
	private static final int CATALOG_COLS = 4;
	private static final int ICON = 24;
	private static final int ICON_GAP = 2;
	private static final int ORDER_COLS = 2;
	private static final int ORDER_ROW_H = 18;
	private static final int ORDER_COL_W = 154;

	private final KitConfig config;
	private final AutoSurround surround;
	private EditBox extraId;
	private EditBox placesPerTick;
	private Checkbox keepRepair;
	private int pickTop;
	private int scrollTop;
	private int pickBottom;
	private int pickScroll;
	private int pickScrollMax;
	private int orderSectionTop;
	private int stateRow;
	private int extraRow;
	private int optionsRow;

	public SurroundScreen(Screen parent, KitConfig config, AutoSurround surround) {
		super(Component.literal("twob2tkit 自动围箱"), parent);
		this.config = config;
		this.surround = surround;
		config.surroundBlockIds = SurroundBlocks.normalize(config.surroundBlockIds);
	}

	/** 从主标签栏进入时高亮围箱标签。 */
	@Override
	protected KitTab currentTab() {
		return parent == null ? KitTab.SURROUND : null;
	}

	/** 布置模式按钮、选项、目录图标与优先级列表。 */
	@Override
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("SURROUND", parent)) return;
		if (parent == null) addTabBar(KitTab.SURROUND);
		int left = panelLeft(320);
		stateRow = stateRowAboveFooter();

		int modeRow = contentTop();
		addRenderableWidget(Button.builder(Component.literal("十格锁定（挂机）"), button -> start(AutoSurround.Mode.FULL))
			.bounds(left, modeRow, 155, 20)
			.tooltip(Tooltip.create(Component.literal("钉在按下时的位置：脚下1、四面脚边、四面头边、头顶1，共10块。地形已有的不补。")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("十格跟随"), button -> start(AutoSurround.Mode.PLUS))
			.bounds(left + 165, modeRow, 155, 20)
			.tooltip(Tooltip.create(Component.literal("跟着你走，同样只补这10格。和 Meteor Surround 类似，但多脚下和头顶。")))
			.build());

		optionsRow = modeRow + CONTROL_ROW_STEP;
		placesPerTick = addRenderableWidget(KitUi.field(this.font, left + 56, optionsRow, 36, "",
			Integer.toString(Math.max(1, config.surroundPlacesPerTick)), 2));
		keepRepair = addRenderableWidget(Checkbox.builder(Component.literal("围好后继续补洞"), this.font)
			.pos(left + 100, optionsRow)
			.selected(config.surroundKeepRepair)
			.onValueChange((box, value) -> {
				config.surroundKeepRepair = value;
				config.save();
			})
			.build());
		addRenderableWidget(Button.builder(Component.literal("常用一套"), button -> applyPreset(SurroundBlocks.DEFAULT_IDS))
			.bounds(left + 240, optionsRow, 80, 20)
			.tooltip(Tooltip.create(Component.literal("圆石、泥土、石头、木板、羊毛、黑曜石；没圆石时按顺序换用")))
			.build());

		extraRow = optionsRow + CONTROL_ROW_STEP;
		extraId = addRenderableWidget(KitUi.field(this.font, left + 56, extraRow, 118, "", "", 64));
		addRenderableWidget(Button.builder(Component.literal("加入"), button -> addExtra())
			.bounds(left + 180, extraRow, 70, 20)
			.tooltip(Tooltip.create(Component.literal("输入方块 ID，例如 minecraft:oak_planks，加入队尾")))
			.build());

		pickTop = extraRow + CONTROL_ROW_STEP + 4;
		scrollTop = pickTop + LABEL_ABOVE_FIELD;
		pickBottom = stateRow - STATE_ABOVE_FOOTER;

		List<SurroundBlocks.Choice> catalog = SurroundBlocks.CATALOG;
		int catalogRows = (catalog.size() + CATALOG_COLS - 1) / CATALOG_COLS;
		int catalogHeight = catalogRows * (ICON + ICON_GAP);
		orderSectionTop = catalogHeight + 6;
		List<String> ids = config.surroundBlockIds;
		int orderRows = Math.max(1, (ids.size() + ORDER_COLS - 1) / ORDER_COLS);
		int contentHeight = orderSectionTop + LABEL_ABOVE_FIELD + orderRows * ORDER_ROW_H;
		int visibleHeight = Math.max(0, pickBottom - scrollTop);
		pickScrollMax = Math.max(0, contentHeight - visibleHeight);
		pickScroll = Mth.clamp(pickScroll, 0, pickScrollMax);

		for (int i = 0; i < catalog.size(); i++) {
			SurroundBlocks.Choice choice = catalog.get(i);
			int col = i % CATALOG_COLS;
			int row = i / CATALOG_COLS;
			int bx = left + col * (ICON + ICON_GAP);
			int by = scrollTop + row * (ICON + ICON_GAP) - pickScroll;
			if (by + ICON <= scrollTop || by >= pickBottom) continue;
			boolean selected = ids.contains(choice.id());
			Item item = SurroundBlocks.itemOf(choice.id());
			ItemStack stack = iconStack(item);
			String tip = selected
				? choice.label() + "（已选，再点取消）"
				: choice.label() + "（点一下加入队尾）";
			ItemIconButton icon = addRenderableWidget(new ItemIconButton(bx, by, ICON, ICON, stack,
				Component.literal(tip), () -> toggleBlock(choice.id())));
			icon.setChosen(selected);
		}

		int orderBase = scrollTop + orderSectionTop + LABEL_ABOVE_FIELD - pickScroll;
		for (int i = 0; i < ids.size(); i++) {
			String id = ids.get(i);
			int col = i % ORDER_COLS;
			int row = i / ORDER_COLS;
			int ox = left + col * (ORDER_COL_W + 4);
			int oy = orderBase + row * ORDER_ROW_H;
			if (oy + ORDER_ROW_H <= scrollTop || oy >= pickBottom) continue;
			Button up = addPickButton(ox, oy, 16, ORDER_ROW_H - 2, Button.builder(Component.literal("▲"), button -> moveBlock(id, -1))
				.tooltip(Tooltip.create(Component.literal("上移，越上越先用"))));
			if (up != null) up.active = i > 0;
			Button down = addPickButton(ox + 18, oy, 16, ORDER_ROW_H - 2, Button.builder(Component.literal("▼"), button -> moveBlock(id, 1))
				.tooltip(Tooltip.create(Component.literal("下移"))));
			if (down != null) down.active = i < ids.size() - 1;
			Button label = addPickButton(ox + 38, oy, ORDER_COL_W - 40, ORDER_ROW_H - 2,
				Button.builder(Component.literal((i + 1) + ". " + SurroundBlocks.label(id)), button -> {}));
			if (label != null) label.active = false;
		}

		addRenderableWidget(Button.builder(Component.literal(surround.isActive() ? "停止围箱" : "按当前设置开始"), button -> {
			if (surround.isActive()) {
				saveFields();
				surround.stop(this.minecraft, "在界面中停止");
				showNotice(surround.status(), 0xFFFF55);
			} else {
				start(AutoSurround.Mode.fromConfig(config.surroundMode));
			}
		}).bounds(left, footerButtonY(), 155, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> {
			saveFields();
			onClose();
		}).bounds(left + 165, footerButtonY(), 155, 20).build());
	}

	/** 目录图标用物品堆；有货时显示数量上限 99。 */
	private ItemStack iconStack(Item item) {
		Item use = item == Items.AIR ? Items.COBBLESTONE : item;
		ItemStack stack = new ItemStack(use);
		if (this.minecraft != null && this.minecraft.player != null && use != Items.AIR) {
			int count = SurroundBlocks.count(this.minecraft.player, use);
			if (count > 0) stack.setCount(Math.min(count, 99));
		}
		return stack;
	}

	/** 仅在滚动可视区内添加优先级行按钮。 */
	private Button addPickButton(int x, int y, int width, int height, Button.Builder builder) {
		if (y + height <= scrollTop || y >= pickBottom) return null;
		return addRenderableWidget(builder.bounds(x, y, width, height).build());
	}

	/** 目录区内滚轮滚动优先级列表。 */
	@Override
	public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
		if (mouseY >= scrollTop && mouseY < pickBottom && pickScrollMax > 0) {
			pickScroll = Mth.clamp(pickScroll - (int)Math.round(scrollY * 14), 0, pickScrollMax);
			rebuildWidgets();
			return true;
		}
		return super.mouseScrolled(mouseX, mouseY, scrollX, scrollY);
	}

	/** 绘制标签、运行状态与底部提示。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(320);
		int center = this.width / 2;
		if (parent != null) {
			KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(8), 0xFFFFFF);
		}
		KitUi.text(graphics, this.font, "每拍块数", left, optionsRow + INLINE_LABEL_DY, 0xA0A0A0);
		KitUi.text(graphics, this.font, "追加 ID", left, extraRow + INLINE_LABEL_DY, 0xA0A0A0);
		KitUi.text(graphics, this.font, "点选方块", left, pickTop, 0xA0A0A0);
		String orderHeader = "优先顺序（上先用）";
		if (pickScrollMax > 0) {
			orderHeader += " · 滚轮 " + (pickScroll * 100 / Math.max(1, pickScrollMax)) + "%";
		}
		int orderLabelY = scrollTop + orderSectionTop - pickScroll;
		if (orderLabelY + 9 > scrollTop && orderLabelY < pickBottom) {
			KitUi.text(graphics, this.font, orderHeader, left, orderLabelY, 0xA0A0A0);
		}

		String state = surround.isActive() ? "运行中：" + surround.mode().label + "  " + surround.status() : "当前未启动";
		KitUi.centered(graphics, this.font, state, center, stateRow,
			surround.isActive() ? 0x55FF55 : 0xA0A0A0);

		if (pickBottom <= scrollTop) {
			KitUi.centered(graphics, this.font, "窗口过小，请调低 GUI 缩放", center, scrollTop + 4, 0xFFFF55);
		}
		if (!notice.isEmpty()) {
			KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
		}
	}

	/** 点选目录：加入队尾或取消；至少保留一种。 */
	private void toggleBlock(String id) {
		List<String> ids = new ArrayList<>(config.surroundBlockIds);
		if (ids.contains(id)) {
			if (ids.size() == 1) {
				showNotice("至少留一种围箱方块", 0xFF5555);
				return;
			}
			ids.remove(id);
		} else {
			ids.add(id);
		}
		config.surroundBlockIds = SurroundBlocks.normalize(ids);
		config.surroundBlockId = config.surroundBlockIds.getFirst();
		config.save();
		rebuildWidgets();
	}

	/** 调整勾选方块优先级；delta 为 -1 上移 / +1 下移。 */
	private void moveBlock(String id, int delta) {
		List<String> ids = new ArrayList<>(config.surroundBlockIds);
		int index = ids.indexOf(id);
		if (index < 0) return;
		int next = index + delta;
		if (next < 0 || next >= ids.size()) return;
		ids.remove(index);
		ids.add(next, id);
		config.surroundBlockIds = SurroundBlocks.normalize(ids);
		config.surroundBlockId = config.surroundBlockIds.getFirst();
		config.save();
		rebuildWidgets();
	}

	/** 把输入框里的方块 ID 追加到队尾。 */
	private void addExtra() {
		String id = SurroundBlocks.canonical(extraId.getValue());
		if (id == null) {
			showNotice("不是有效物品 ID", 0xFF5555);
			return;
		}
		Item item = SurroundBlocks.itemOf(id);
		if (!(item instanceof BlockItem) || item == Items.AIR) {
			showNotice("这不是可放置的方块", 0xFF5555);
			return;
		}
		List<String> ids = new ArrayList<>(config.surroundBlockIds);
		ids.remove(id);
		ids.add(id);
		config.surroundBlockIds = SurroundBlocks.normalize(ids);
		config.surroundBlockId = config.surroundBlockIds.getFirst();
		config.save();
		extraId.setValue("");
		showNotice("已加入队尾：" + SurroundBlocks.label(id), 0x55FF55);
		rebuildWidgets();
	}

	/** 套用预设 ID 列表并保存。 */
	private void applyPreset(List<String> ids) {
		config.surroundBlockIds = SurroundBlocks.normalize(ids);
		config.surroundBlockId = config.surroundBlockIds.getFirst();
		config.save();
		rebuildWidgets();
		showNotice("已换成常用一套：" + SurroundBlocks.summary(config.surroundBlockIds), 0x55FF55);
	}

	/** 保存字段后启动围箱并关界面。 */
	private void start(AutoSurround.Mode mode) {
		if (!saveFields()) return;
		config.surroundMode = mode.name();
		config.save();
		KitClient.startSurround(this.minecraft, mode);
		this.minecraft.setScreen(null);
	}

	/** 校验并写入每拍块数、补洞开关与方块列表。 */
	private boolean saveFields() {
		try {
			config.surroundPlacesPerTick = KitUi.parseInt(placesPerTick, "每拍块数", 1, 4);
			config.surroundKeepRepair = keepRepair.selected();
			config.surroundBlockIds = SurroundBlocks.normalize(config.surroundBlockIds);
			config.surroundBlockId = config.surroundBlockIds.getFirst();
			config.save();
			return true;
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return false;
		}
	}

	/** 关闭前落盘当前表单。 */
	@Override
	public void onClose() {
		saveFields();
		super.onClose();
	}
}
