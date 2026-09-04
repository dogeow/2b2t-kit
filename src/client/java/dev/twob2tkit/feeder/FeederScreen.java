package dev.twob2tkit.feeder;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitTab;
import dev.twob2tkit.KitUi;

/** 自动喂养设置界面。 */
public final class FeederScreen extends KitHudScreen {
	private static final int TYPE_COLS = 3;
	private static final int TYPE_ROW_H = 20;
	private static final int TYPE_COL_W = 104;

	private final KitConfig config;
	private final AutoFeeder feeder;
	private final Map<String, Checkbox> typeBoxes = new HashMap<>();
	private Checkbox breedAdults;
	private Checkbox growBabies;
	private Checkbox walkTo;
	private Checkbox hideFood;
	private EditBox range;
	private int rangeRow;
	private int typesTop;
	private int typesBottom;
	private int typeScroll;
	private int typeScrollMax;
	private int stateRow;

	/** 打开自动喂养设置屏。 */
	public FeederScreen(Screen parent, KitConfig config, AutoFeeder feeder) {
		super(Component.literal("2b2t-kit 自动喂养"), parent);
		this.config = config;
		this.feeder = feeder;
	}

	@Override
	/** 顶栏在喂养标签时高亮。 */
	protected KitTab currentTab() {
		return parent == null ? KitTab.FEED : null;
	}

	@Override
	/** 繁殖/走近/动物优先列表与开始按钮。 */
	protected void init() {
		if (parent == null) addTabBar(KitTab.FEED);
		typeBoxes.clear();
		int left = panelLeft(320);
		stateRow = stateRowAboveFooter();
		int optionsTop = contentTop();
		rangeRow = optionsTop + TYPE_ROW_H * 2 + 6;
		typesTop = rangeRow + TYPE_ROW_H + 8;
		typesBottom = stateRow - STATE_ABOVE_FOOTER;

		breedAdults = checkbox(left, optionsTop, "繁殖成体", config.feederBreedAdults);
		growBabies = checkbox(left + 165, optionsTop, "催熟幼体", config.feederGrowBabies);
		walkTo = checkbox(left, optionsTop + TYPE_ROW_H, "走近再喂", config.feederWalk);
		walkTo.setTooltip(Tooltip.create(Component.literal("范围内的动物会走过去喂，不会站着一直举着小麦")));
		hideFood = checkbox(left + 165, optionsTop + TYPE_ROW_H, "喂完收起饲料", config.feederHideFood);
		hideFood.setTooltip(Tooltip.create(Component.literal("喂完换成空手或方块，不换剑斧，避免 Meteor 自动攻击把动物打死")));

		range = addRenderableWidget(KitUi.field(this.font, left + FIELD_LABEL_X, rangeRow, 70, "",
			KitUi.formatNumber(Math.max(3.0, config.feederRange)), 4));

		List<String> order = config.feederTypeOrder();
		int typeRows = (order.size() + TYPE_COLS - 1) / TYPE_COLS;
		int visibleRows = Math.max(1, (typesBottom - typesTop) / TYPE_ROW_H);
		typeScrollMax = Math.max(0, typeRows * TYPE_ROW_H - visibleRows * TYPE_ROW_H);
		typeScroll = Math.max(0, Math.min(typeScroll, typeScrollMax));

		for (int i = 0; i < order.size(); i++) {
			String id = order.get(i);
			int col = i % TYPE_COLS;
			int row = i / TYPE_COLS;
			int x = left + col * (TYPE_COL_W + 2);
			int y = typesTop + row * TYPE_ROW_H - typeScroll;
			if (y + TYPE_ROW_H <= typesTop || y >= typesBottom) continue;
			int rank = i + 1;
			addRenderableWidget(Button.builder(Component.literal("▲"), button -> moveType(id, -1))
				.bounds(x, y, 16, TYPE_ROW_H - 2)
				.tooltip(Tooltip.create(Component.literal("提高优先。没对应饲料会跳过，改喂下一种")))
				.build()).active = i > 0;
			addRenderableWidget(Button.builder(Component.literal("▼"), button -> moveType(id, 1))
				.bounds(x + 18, y, 16, TYPE_ROW_H - 2)
				.tooltip(Tooltip.create(Component.literal("降低优先")))
				.build()).active = i < order.size() - 1;
			Checkbox box = checkbox(x + 38, y, rank + "." + KitConfig.feederTypeLabel(id), config.feederTypeEnabled(id));
			typeBoxes.put(id, box);
		}

		addRenderableWidget(Button.builder(Component.literal(feeder.isActive() ? "停止喂养" : "开始喂养"), button -> {
			if (feeder.isActive()) {
				if (!saveFields()) return;
				feeder.stop(this.minecraft, "在界面中停止");
				showNotice(feeder.status(), 0xFFFF55);
				button.setMessage(Component.literal("开始喂养"));
			} else {
				startFeeder();
			}
		}).bounds(left, footerButtonY(), 155, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> {
			saveFields();
			onClose();
		}).bounds(left + 165, footerButtonY(), 155, 20).build());
	}

	@Override
	/** 动物列表区域滚轮滚动。 */
	public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
		if (mouseY >= typesTop && mouseY < typesBottom && typeScrollMax > 0) {
			typeScroll = Math.max(0, Math.min(typeScrollMax, typeScroll - (int)Math.round(scrollY * TYPE_ROW_H)));
			rebuildWidgets();
			return true;
		}
		return super.mouseScrolled(mouseX, mouseY, scrollX, scrollY);
	}

	@Override
	/** 画范围标签、优先说明与运行状态。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(320);
		int center = this.width / 2;
		if (parent != null) {
			KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(8), 0xFFFFFF);
		}
		KitUi.text(graphics, this.font, "搜寻范围（格）", left, rangeRow + INLINE_LABEL_DY, 0xA0A0A0);
		KitUi.text(graphics, this.font, "动物优先（上先喂）", left, typesTop - LABEL_ABOVE_FIELD, 0xA0A0A0);
		if (typeScrollMax > 0) {
			KitUi.text(graphics, this.font, "滚轮查看更多", left + 200, typesTop - LABEL_ABOVE_FIELD, 0x888888);
		}
		String state = feeder.isActive()
			? "运行中：已喂 " + feeder.fedCount() + " 次  " + feeder.status()
			: "当前未启动";
		KitUi.centered(graphics, this.font, state, center, stateRow, feeder.isActive() ? 0x55FF55 : 0xA0A0A0);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
	}

	/** 保存后启动喂养并关屏。 */
	private void startFeeder() {
		if (!saveFields()) return;
		KitClient.startFeeder(this.minecraft);
		this.minecraft.setScreen(null);
	}

	/** 调整动物优先顺序后重建控件。 */
	private void moveType(String id, int delta) {
		if (!saveFields()) return;
		config.moveFeederType(id, delta);
		config.save();
		rebuildWidgets();
	}

	/** 创建勾选框并加入界面。 */
	private Checkbox checkbox(int x, int y, String text, boolean selected) {
		return addRenderableWidget(Checkbox.builder(Component.literal(text), this.font)
			.pos(x, y)
			.selected(selected)
			.build());
	}

	/** 写回配置；至少一种动物且勾了繁殖或催熟。 */
	private boolean saveFields() {
		try {
			config.feederBreedAdults = breedAdults.selected();
			config.feederGrowBabies = growBabies.selected();
			config.feederWalk = walkTo.selected();
			config.feederHideFood = hideFood.selected();
			config.feederRange = KitUi.parse(range, "搜寻范围", 3.0, 24.0);
			for (String id : KitConfig.FEEDER_TYPE_IDS) {
				Checkbox box = typeBoxes.get(id);
				if (box != null) config.setFeederTypeEnabled(id, box.selected());
			}
			if (!config.feederBreedAdults && !config.feederGrowBabies) {
				throw new IllegalArgumentException("请至少勾选繁殖成体或催熟幼体");
			}
			if (!anyTypeEnabled()) {
				throw new IllegalArgumentException("请至少勾选一种动物");
			}
			config.save();
			return true;
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return false;
		}
	}

	/** 是否至少勾了一种动物。 */
	private boolean anyTypeEnabled() {
		for (String id : KitConfig.FEEDER_TYPE_IDS) {
			if (config.feederTypeEnabled(id)) return true;
		}
		return false;
	}

	@Override
	/** 关屏前先保存。 */
	public void onClose() {
		saveFields();
		super.onClose();
	}
}
