package dev.twob2tkit.adventure;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.ContainerObjectSelectionList;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;

import java.util.ArrayList;
import java.util.List;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitTab;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.ItemIconButton;

/** 活动材料清单编辑界面。 */
public final class ActivityChecklistScreen extends KitHudScreen {
	private static final int CELL = 20;
	private static final int MAX_INV_ROWS = 3;
	private static final int ROW_STEP = 22;

	private final KitConfig config;
	private Checkbox autoRestock;
	private EditBox newListName;
	private EditBox addCount;
	private NeedList list;
	private String draftName = "";
	private String draftCount = "1";
	private int profilesBottom = 88;

	private int invTop;
	private int invRows;
	private int listTop;
	private int listHeight;
	private int restockRow;

	/** 打开活动材料清单屏。 */
	public ActivityChecklistScreen(Screen parent, KitConfig config) {
		super(Component.literal("twob2tkit 行动清单"), parent);
		this.config = config;
		ActivityRequirements.ensureLists(config);
	}

	@Override
	/** 助手相关标签。 */
	protected KitTab currentTab() {
		return parent == null ? KitTab.CHECKLIST : null;
	}

	@Override
	/** 清单列表、条目与编辑按钮。 */
	protected void init() {
		if (parent == null) addTabBar(KitTab.CHECKLIST);
		int left = panelLeft(360);
		if (newListName != null) draftName = newListName.getValue();
		if (addCount != null) draftCount = addCount.getValue();

		List<KitConfig.ActivityList> lists = ActivityRequirements.lists(config);
		int columns = 3;
		int buttonWidth = 112;
		int gap = 12;
		int startY = contentTop();
		addRenderableWidget(Button.builder(Component.literal(labelFor("NONE", "不启用")), button -> select("NONE"))
			.bounds(left, startY, buttonWidth, 20).build());
		for (int i = 0; i < lists.size(); i++) {
			KitConfig.ActivityList activity = lists.get(i);
			int index = i + 1;
			int column = index % columns;
			int row = index / columns;
			String id = activity.id;
			addRenderableWidget(Button.builder(Component.literal(labelFor(id, activity.label)), button -> select(id))
				.bounds(left + column * (buttonWidth + gap), startY + row * ROW_STEP, buttonWidth, 20).build());
		}
		int rows = (lists.size() + 1 + columns - 1) / columns;
		profilesBottom = startY + rows * ROW_STEP;

		int y = profilesBottom + 6;
		newListName = addRenderableWidget(KitUi.field(this.font, left, y, 160, "新行动名称", draftName, 24));
		newListName.setHint(Component.literal("新行动名称"));
		addRenderableWidget(Button.builder(Component.literal("新建行动"), button -> createList())
			.bounds(left + 168, y, 88, 20)
			.tooltip(Tooltip.create(Component.literal("新建一份空白清单，可自己加物品和数量")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("删除行动"), button -> deleteList())
			.bounds(left + 264, y, 96, 20)
			.tooltip(Tooltip.create(Component.literal("只能删除自己建的行动。内置三项可恢复默认")))
			.build());

		y += ROW_STEP;
		addCount = addRenderableWidget(KitUi.field(this.font, left, y, 48, "数量", draftCount, 4));
		addRenderableWidget(Button.builder(Component.literal("加入主手"), button -> addHeld())
			.bounds(left + 56, y, 72, 20)
			.tooltip(Tooltip.create(Component.literal("把主手（或副手）物品加进当前清单")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("恢复默认"), button -> resetSelected())
			.bounds(left + 136, y, 88, 20).build());
		addRenderableWidget(Button.builder(Component.literal("检查背包"), button -> checkNow())
			.bounds(left + 232, y, 88, 20).build());

		restockRow = y + ROW_STEP;
		autoRestock = addRenderableWidget(Checkbox.builder(Component.literal("打开箱子后按清单自动补货"), this.font)
			.pos(left, restockRow)
			.selected(config.autoRestockFromOpenedContainers)
			.onValueChange((box, value) -> {
				config.autoRestockFromOpenedContainers = value;
				config.save();
			})
			.build());

		int footerTop = footerButtonY();
		int contentBottom = footerTop - 28;
		int controlsBottom = restockRow + 20;
		invTop = controlsBottom + LABEL_ABOVE_FIELD;
		int space = contentBottom - invTop;
		int sectionGap = 6;
		int minList = 48;
		invRows = MAX_INV_ROWS;
		int invHeight = invRows * CELL;
		while (invRows > 1 && invHeight + sectionGap + minList > space) {
			invRows--;
			invHeight = invRows * CELL;
		}
		if (space < invHeight + sectionGap + 24) {
			invRows = Math.max(1, Math.min(MAX_INV_ROWS, Math.max(1, (space - sectionGap - 24) / CELL)));
			invHeight = invRows * CELL;
		}
		listTop = invTop + invHeight + sectionGap;
		listHeight = Math.max(0, contentBottom - listTop);
		addInventoryPicker(left, invTop, invRows);
		list = null;
		if (listHeight >= 24) {
			list = addRenderableWidget(new NeedList(this.minecraft, this.width, listHeight, listTop));
			list.populate();
		}

		addRenderableWidget(Button.builder(Component.literal("保存并返回"), button -> onClose())
			.bounds(this.width / 2 - 100, footerButtonY(), 200, 20).build());
	}

	@Override
	/** 画标题与进度。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		int left = panelLeft(360);
		int hintY = headerY(0);
		if (parent != null) {
			KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(8), 0xFFFFFF);
		}
		if (notice.isEmpty()) {
			KitUi.centered(graphics, this.font, "点下方背包格子加入；数量取左边输入框", center, hintY, 0xA0A0A0);
		} else {
			KitUi.centered(graphics, this.font, notice, center, hintY, noticeColor);
		}
		if (invTop > 0) {
			KitUi.text(graphics, this.font, "背包（点图标加入；快捷栏用「加入主手」）", left, invTop - LABEL_ABOVE_FIELD, 0xA0A0A0);
		}

		KitConfig.ActivityList selected = ActivityRequirements.selectedList(config);
		if (selected == null && list != null && listHeight > 28) {
			KitUi.centered(graphics, this.font, "先选一个行动，或点「新建行动」",
				center, listTop + listHeight / 2 - 4, 0xA0A0A0);
		} else if (selected != null && list == null) {
			KitUi.centered(graphics, this.font, "界面高度不够显示清单，请调低 GUI 缩放", center, footerNoticeY() - 28, 0xFFFF55);
		}
	}

	@Override
	/** 回车确认编辑。 */
	protected boolean onEnterPressed() {
		if (getFocused() == newListName) {
			createList();
			return true;
		}
		addHeld();
		return true;
	}

	/** 清单显示名。 */
	private String labelFor(String id, String label) {
		return id.equals(config.activityProfile) || ("NONE".equals(id) && !ActivityRequirements.isActive(config))
			? "✓ " + label
			: label;
	}

	/** 选中清单并刷新。 */
	private void select(String id) {
		saveOptions();
		config.activityProfile = id;
		config.save();
		KitConfig.ActivityList selected = ActivityRequirements.selectedList(config);
		notice = selected == null ? "已关闭行动检查" : "已选择：" + selected.label;
		noticeColor = 0x55FFFF;
		rebuildWidgets();
	}

	/** 新建清单。 */
	private void createList() {
		String name = newListName.getValue().trim();
		if (name.isEmpty()) {
			showNotice("请先填写新行动名称", 0xFF5555);
			return;
		}
		if (name.length() > 16) {
			showNotice("行动名称最多 16 字", 0xFF5555);
			return;
		}
		KitConfig.ActivityList created = new KitConfig.ActivityList();
		created.id = ActivityRequirements.newListId();
		created.label = name;
		created.needs = new ArrayList<>();
		ActivityRequirements.lists(config).add(created);
		config.activityProfile = created.id;
		config.save();
		draftName = "";
		showNotice("已新建行动：" + name + "，点背包格子或主手加入物品", 0x55FF55);
		rebuildWidgets();
	}

	/** 删除当前清单。 */
	private void deleteList() {
		KitConfig.ActivityList selected = ActivityRequirements.selectedList(config);
		if (selected == null) {
			showNotice("请先选择要删除的行动", 0xFF5555);
			return;
		}
		if (ActivityRequirements.isBuiltin(selected)) {
			showNotice("内置行动不能删，可改条目或点「恢复默认」", 0xFFFF55);
			return;
		}
		config.activityLists.remove(selected);
		config.activityProfile = "NONE";
		config.save();
		showNotice("已删除行动：" + selected.label, 0x55FFFF);
		rebuildWidgets();
	}

	/** 把手上物品加入需求。 */
	private void addHeld() {
		if (this.minecraft.player == null) {
			showNotice("当前不在游戏中", 0xFF5555);
			return;
		}
		ItemStack held = this.minecraft.player.getMainHandItem();
		if (held.isEmpty()) held = this.minecraft.player.getOffhandItem();
		addStack(held);
	}

	/** 画背包物品点选区。 */
	private void addInventoryPicker(int left, int top, int rows) {
		LocalPlayer player = this.minecraft.player;
		if (player == null) return;
		for (int row = 0; row < rows; row++) {
			for (int col = 0; col < 9; col++) {
				int slot = 9 + row * 9 + col;
				addInventorySlot(left + col * CELL, top + row * CELL, player.getInventory().getItem(slot));
			}
		}
	}

	/** 一个背包格按钮。 */
	private void addInventorySlot(int x, int y, ItemStack stack) {
		if (stack.isEmpty()) return;
		ItemStack copy = stack.copy();
		Component tip = Component.literal(stack.getHoverName().getString()
			+ " ×" + stack.getCount() + "\n点一下加入清单");
		addRenderableWidget(new ItemIconButton(x, y, 20, 20, copy, tip, () -> addStack(stack)));
	}

	/** 把堆叠加入当前清单。 */
	private void addStack(ItemStack stack) {
		KitConfig.ActivityList selected = ActivityRequirements.selectedList(config);
		if (selected == null) {
			showNotice("请先选择或新建一个行动", 0xFF5555);
			return;
		}
		if (stack == null || stack.isEmpty()) {
			showNotice("该格没有物品", 0xFF5555);
			return;
		}
		int target;
		try {
			target = KitUi.parseInt(addCount, "数量", 1, 9999);
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return;
		}
		KitConfig.ActivityNeed added = ActivityRequirements.fromHeld(stack, target);
		if (added == null) {
			showNotice("无法识别该物品", 0xFF5555);
			return;
		}
		for (KitConfig.ActivityNeed existing : selected.needs) {
			if (added.match.equals(existing.match)) {
				existing.target = target;
				if (existing.label == null || existing.label.isBlank()) existing.label = added.label;
				config.save();
				if (list != null) list.populate();
				showNotice("已更新「" + existing.label + "」数量为 " + target, 0x55FFFF);
				return;
			}
		}
		selected.needs.add(added);
		config.save();
		if (list != null) list.populate();
		showNotice("已加入「" + added.label + "」×" + target, 0x55FF55);
	}

	/** 重置选中清单为默认。 */
	private void resetSelected() {
		KitConfig.ActivityList selected = ActivityRequirements.selectedList(config);
		if (selected == null) {
			showNotice("请先选择一个行动", 0xFF5555);
			return;
		}
		ActivityRequirements.Profile profile = ActivityRequirements.Profile.fromConfig(selected.id);
		if (!ActivityRequirements.isBuiltin(selected)) {
			selected.needs.clear();
			config.save();
			if (list != null) list.populate();
			showNotice("已清空「" + selected.label + "」", 0x55FFFF);
			return;
		}
		selected.needs = new ArrayList<>(ActivityRequirements.defaultNeeds(profile));
		selected.label = profile.label;
		config.save();
		if (list != null) list.populate();
		showNotice("已恢复「" + selected.label + "」默认清单", 0x55FF55);
	}

	/** 移除一条需求。 */
	private void removeNeed(KitConfig.ActivityNeed need) {
		KitConfig.ActivityList selected = ActivityRequirements.selectedList(config);
		if (selected == null) return;
		selected.needs.remove(need);
		config.save();
		if (list != null) list.populate();
		showNotice("已移除「" + need.label + "」", 0x55FFFF);
	}

	/** 保存需求数量输入。 */
	private void saveNeedCount(KitConfig.ActivityNeed need, String text) {
		try {
			int value = Integer.parseInt(text.trim());
			if (value < 1 || value > 9999) return;
			if (need.target == value) return;
			need.target = value;
			config.save();
		} catch (NumberFormatException ignored) {
		}
	}

	/** 立刻检查缺料并提示。 */
	private void checkNow() {
		saveOptions();
		if (!ActivityRequirements.isActive(config)) {
			showNotice("请先选择一个行动", 0xFF5555);
		} else if (this.minecraft.player == null) {
			showNotice("当前不在游戏中", 0xFF5555);
		} else {
			String missing = ActivityRequirements.missingSummary(this.minecraft.player, config);
			showNotice(missing.isEmpty() ? "清单物资已齐全" : "仍缺少：" + missing, missing.isEmpty() ? 0x55FF55 : 0xFFFF55);
		}
	}

	/** 保存界面选项。 */
	private void saveOptions() {
		if (autoRestock != null) config.autoRestockFromOpenedContainers = autoRestock.selected();
		config.save();
	}

	@Override
	/** 关屏前保存。 */
	public void onClose() {
		saveOptions();
		super.onClose();
	}

	private final class NeedList extends ContainerObjectSelectionList<NeedList.Entry> {
		/** 需求列表控件。 */
		private NeedList(Minecraft minecraft, int width, int height, int y) {
			super(minecraft, width, height, y, 24);
			this.centerListVertically = false;
		}

		/** 填充行。 */
		private void populate() {
			clearEntries();
			KitConfig.ActivityList selected = ActivityRequirements.selectedList(config);
			if (selected == null) return;
			for (KitConfig.ActivityNeed need : selected.needs) addEntry(new Entry(need));
		}

		@Override
		/** 行宽。 */
		public int getRowWidth() {
			return Math.min(360, this.width - 24);
		}

		private final class Entry extends ContainerObjectSelectionList.Entry<Entry> {
			private final KitConfig.ActivityNeed need;
			private final EditBox count;
			private final Button remove;

			/** 一行。 */
			private Entry(KitConfig.ActivityNeed need) {
				this.need = need;
				this.count = KitUi.field(font, 0, 0, 44, "数量", Integer.toString(need.target), 4);
				this.count.setResponder(text -> saveNeedCount(need, text));
				this.remove = Button.builder(Component.literal("删"), button -> removeNeed(need))
					.bounds(0, 0, 32, 20).build();
			}

			@Override
			/** 画列表行。 */
			public void extractContent(GuiGraphicsExtractor graphics, int mouseX, int mouseY, boolean hovered, float delta) {
				int have = 0;
				ActivityRequirements.Requirement requirement = ActivityRequirements.requirement(need);
				if (minecraft.player != null && requirement != null) {
					have = ActivityRequirements.count(minecraft.player, requirement);
				}
				boolean ready = have >= need.target;
				int maxWidth = Math.max(40, getContentRight() - 90 - getContentX());
				String prefix = (ready ? "✓ " : "! ") + need.label;
				String suffix = "  " + have + " /";
				while (font.width(prefix + suffix) > maxWidth && prefix.length() > 3) {
					prefix = prefix.substring(0, prefix.length() - 1);
				}
				if (font.width(prefix + suffix) > maxWidth) prefix = prefix.substring(0, Math.max(1, prefix.length() - 1)) + "…";
				String text = prefix + suffix;
				graphics.text(font, text, getContentX(), getContentYMiddle() - 4, KitUi.argb(ready ? 0x55FF55 : 0xFFFF55));
				int buttonY = getContentY() - 2;
				remove.setPosition(getContentRight() - 34, buttonY);
				count.setPosition(getContentRight() - 82, buttonY);
				count.extractRenderState(graphics, mouseX, mouseY, delta);
				remove.extractRenderState(graphics, mouseX, mouseY, delta);
			}

			@Override
			/** 子控件。 */
			public List<? extends GuiEventListener> children() {
				return List.of(count, remove);
			}

			@Override
			/** 朗读条目。 */
			public List<? extends NarratableEntry> narratables() {
				return List.of(count, remove);
			}
		}
	}
}
