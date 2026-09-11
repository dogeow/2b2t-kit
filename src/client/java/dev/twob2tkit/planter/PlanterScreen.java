package dev.twob2tkit.planter;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitTab;
import dev.twob2tkit.KitUi;

/** 自动种田设置界面。 */
public final class PlanterScreen extends KitHudScreen {
	private final KitConfig config;
	private final AutoPlanter planter;
	private Checkbox walkTo;
	private Checkbox till;
	private Checkbox stack;
	private Checkbox harvest;
	private Checkbox pickup;
	private EditBox range;
	private int optionsTop;
	private int rangeRow;
	private int cropRow;
	private int stateRow;

	/** 打开自动种田设置屏。 */
	public PlanterScreen(Screen parent, KitConfig config, AutoPlanter planter) {
		super(Component.literal("twob2tkit 自动种田"), parent);
		this.config = config;
		this.planter = planter;
	}

	@Override
	/** 顶栏在种田标签时高亮。 */
	protected KitTab currentTab() {
		return parent == null ? KitTab.PLANT : null;
	}

	@Override
	/** 走近/锄地/收成等选项与开始按钮。 */
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("PLANTER", parent)) return;
		if (parent == null) addTabBar(KitTab.PLANT);
		int left = panelLeft(320);
		optionsTop = contentTop();
		walkTo = checkbox(left, optionsTop, "走近再种", config.planterWalk);
		walkTo.setTooltip(Tooltip.create(Component.literal("范围内的空耕地或甘蔗位会走过去种")));
		till = checkbox(left + 165, optionsTop, "没有耕地时先锄地", config.planterTill);
		till.setTooltip(Tooltip.create(Component.literal("手里是小麦种子、胡萝卜等需要耕地的作物时，会把泥土/草方块锄成耕地再种。只锄水源 4 格内能浇到的地")));
		stack = checkbox(left, optionsTop + 24, "甘蔗仙人掌往上叠", config.planterStack);
		stack.setTooltip(Tooltip.create(Component.literal("默认只补地面空位。勾选后会在已有甘蔗、仙人掌、竹子上继续往上种")));
		harvest = checkbox(left + 165, optionsTop + 24, "自动收成（收完再种）", config.planterHarvest);
		harvest.setTooltip(Tooltip.create(Component.literal(
			"收成熟的小麦、胡萝卜、地狱疣等，然后种回锁定的作物。没拿种子时也会先收田里已熟的，打掉就有种子。小麦田里不会去收胡萝卜。走过耕地会潜行。Meteor 没有自动收成；若开了 Nuker 收田，把这项关掉以免抢左键")));
		pickup = checkbox(left, optionsTop + 48, "收完捡掉落物", config.planterPickup);
		pickup.setTooltip(Tooltip.create(Component.literal("收成或种完附近没有空位时，把地上同种作物的种子和收成捡进背包。需要「走近再种」才能走过去捡")));

		rangeRow = optionsTop + CONTROL_ROW_STEP * 3 + SECTION_GAP;
		range = addRenderableWidget(KitUi.field(this.font, left + FIELD_LABEL_X, rangeRow, 70, "",
			KitUi.formatNumber(Math.max(3.0, config.planterRange)), 4));

		stateRow = stateRowAboveFooter();
		cropRow = Math.max(rangeRow + CONTROL_ROW_STEP + SECTION_GAP, stateRow - CONTROL_ROW_STEP * 2 - SECTION_GAP);

		addRenderableWidget(Button.builder(Component.literal(planter.isActive() ? "停止种田" : "开始种田"), button -> {
			if (planter.isActive()) {
				if (!saveFields()) return;
				planter.stop(this.minecraft, "在界面中停止");
				showNotice(planter.status(), 0xFFFF55);
				button.setMessage(Component.literal("开始种田"));
			} else {
				startPlanter();
			}
		}).bounds(left, footerButtonY(), 155, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> {
			saveFields();
			onClose();
		}).bounds(left + 165, footerButtonY(), 155, 20).build());
	}

	@Override
	/** 画范围、当前作物与运行状态。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(320);
		int center = this.width / 2;
		if (parent != null) {
			KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(8), 0xFFFFFF);
		}
		KitUi.text(graphics, this.font, "搜寻范围（格）", left, rangeRow + INLINE_LABEL_DY, 0xA0A0A0);

		String held = "—";
		if (this.minecraft.player != null) {
			ItemStack main = this.minecraft.player.getMainHandItem();
			if (AutoPlanter.isCrop(main)) held = main.getHoverName().getString();
			else if (planter.isActive()) held = planter.cropLabel();
		}
		KitUi.centered(graphics, this.font, "当前作物：" + held, center, cropRow, 0x55FFFF);

		String state = planter.isActive()
			? "运行中：种了 " + planter.plantedCount() + "  锄了 " + planter.tilledCount()
				+ "  收了 " + planter.harvestedCount() + "  捡了 " + planter.pickedLootCount() + "  " + planter.status()
			: "当前未启动";
		KitUi.centered(graphics, this.font, "走过耕地会潜行。种子用完不会改种；换手上的种子才换作物", center, stateRow - 36, 0xA0A0A0);
		KitUi.centered(graphics, this.font, "可可豆挂丛林原木侧面。副手图腾不会被换掉", center, stateRow - 18, 0xA0A0A0);
		KitUi.centered(graphics, this.font, state, center, stateRow, planter.isActive() ? 0x55FF55 : 0xA0A0A0);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
	}

	/** 保存后启动种田。 */
	private void startPlanter() {
		if (!saveFields()) return;
		KitClient.startPlanter(this.minecraft);
		this.minecraft.setScreen(null);
	}

	/** 创建勾选框并加入界面。 */
	private Checkbox checkbox(int x, int y, String text, boolean selected) {
		return addRenderableWidget(Checkbox.builder(Component.literal(text), this.font)
			.pos(x, y)
			.selected(selected)
			.build());
	}

	/** 写回配置并落盘。 */
	private boolean saveFields() {
		try {
			config.planterWalk = walkTo.selected();
			config.planterTill = till.selected();
			config.planterStack = stack.selected();
			config.planterHarvest = harvest.selected();
			config.planterPickup = pickup.selected();
			config.planterRange = KitUi.parse(range, "搜寻范围", 3.0, 24.0);
			config.save();
			return true;
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return false;
		}
	}

	@Override
	/** 关屏前先保存。 */
	public void onClose() {
		saveFields();
		super.onClose();
	}
}
