package dev.twob2tkit.combat;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.ContainerObjectSelectionList;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 选择计入提醒的补给物品。 */
public final class HealingItemsScreen extends KitHudScreen {
	private final KitConfig config;
	private ChoiceList list;

	/** 打开补给物品勾选屏。 */
	public HealingItemsScreen(Screen parent, KitConfig config) {
		super(Component.literal("回血物品"), parent);
		this.config = config;
		config.healingItemIds = HealingItems.normalize(config.healingItemIds);
	}

	@Override
	/** 预设按钮与可滚动勾选列表。 */
	protected void init() {
		int listTop = bodyTop(48);
		int listHeight = Math.max(48, contentBottom() - 28 - listTop);
		list = addRenderableWidget(new ChoiceList(this.minecraft, this.width, listHeight, listTop));
		list.populate();
		int left = panelLeft(320);
		addRenderableWidget(Button.builder(Component.literal("熟食+面包"), button -> applyPreset(HealingItems.defaultIds()))
			.bounds(left, contentBottom(), 100, 20).build());
		addRenderableWidget(Button.builder(Component.literal("任意食物"), button -> applyPreset(Set.of(HealingItems.ANY_FOOD, HealingItems.HEALING_POTION)))
			.bounds(left + 110, contentBottom(), 100, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left + 220, contentBottom(), 100, 20).build());
	}

	@Override
	/** 画标题与摘要。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, "多选要计入的回血物资，右侧是背包现有数量", center, headerY(12), 0xFFFFFF);
		int have = this.minecraft.player == null ? 0 : HealingItems.count(this.minecraft.player, config.healingItemIds);
		KitUi.centered(graphics, this.font, "已选合计 " + have + " / 需要 " + config.minimumHealingItems, center, headerY(26),
			have >= config.minimumHealingItems ? 0x55FF55 : 0xFF5555);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, headerY(38), noticeColor);
	}

	/** 套用默认或清空勾选。 */
	private void applyPreset(Set<String> ids) {
		config.healingItemIds = new LinkedHashSet<>(ids);
		config.save();
		list.populate();
		showNotice("已更新选择", 0x55FF55);
	}

	/** 切换某一项勾选并保存。 */
	private void toggle(HealingItems.Choice choice, boolean selected) {
		if (selected) config.healingItemIds.add(choice.id());
		else config.healingItemIds.remove(choice.id());
		if (config.healingItemIds.isEmpty()) config.healingItemIds.add(choice.id());
		config.save();
	}

	private final class ChoiceList extends ContainerObjectSelectionList<ChoiceList.Entry> {
		/** 补给勾选列表控件。 */
		private ChoiceList(Minecraft minecraft, int width, int height, int y) {
			super(minecraft, width, height, y, 22);
			this.centerListVertically = false;
		}

		/** 按目录填充行。 */
		private void populate() {
			clearEntries();
			for (HealingItems.Choice choice : HealingItems.CATALOG) addEntry(new Entry(choice));
		}

		@Override
		/** 列表行宽。 */
		public int getRowWidth() {
			return Math.min(320, this.width - 24);
		}

		private final class Entry extends ContainerObjectSelectionList.Entry<Entry> {
			private final HealingItems.Choice choice;
			private final Checkbox box;

			/** 一行补给勾选。 */
			private Entry(HealingItems.Choice choice) {
				this.choice = choice;
				this.box = Checkbox.builder(Component.literal(choice.label()), font)
					.pos(0, 0)
					.selected(config.healingItemIds.contains(choice.id()))
					.onValueChange((checkbox, value) -> toggle(choice, value))
					.build();
			}

			@Override
			/** 画列表行内容。 */
			public void extractContent(GuiGraphicsExtractor graphics, int mouseX, int mouseY, boolean hovered, float delta) {
				box.setPosition(getContentX(), getContentY() - 1);
				box.extractRenderState(graphics, mouseX, mouseY, delta);
				int have = minecraft.player == null ? 0 : HealingItems.countChoice(minecraft.player, choice);
				String count = "背包 " + have;
				int color = have > 0 ? 0x55FF55 : 0xA0A0A0;
				graphics.text(font, count, getContentRight() - font.width(count) - 8, getContentYMiddle() - 4, KitUi.argb(color));
			}

			@Override
			/** 子控件列表。 */
			public List<? extends GuiEventListener> children() {
				return List.of(box);
			}

			@Override
			/** 无障碍朗读条目。 */
			public List<? extends NarratableEntry> narratables() {
				return List.of(box);
			}
		}
	}
}
