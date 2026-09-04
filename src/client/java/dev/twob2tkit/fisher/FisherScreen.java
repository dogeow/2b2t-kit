package dev.twob2tkit.fisher;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitTab;
import dev.twob2tkit.KitUi;

/** 自动钓鱼设置界面。 */
public final class FisherScreen extends KitHudScreen {
	private final KitConfig config;
	private final AutoFisher fisher;
	private Checkbox leaveHook;
	private EditBox chestRange;
	private int optionsTop;
	private int rangeRow;

	/** 打开自动钓鱼设置屏。 */
	public FisherScreen(Screen parent, KitConfig config, AutoFisher fisher) {
		super(Component.literal("twob2tkit 自动钓鱼"), parent);
		this.config = config;
		this.fisher = fisher;
	}

	@Override
	/** 顶栏在钓鱼标签时高亮；从别处打开则无标签。 */
	protected KitTab currentTab() {
		return parent == null ? KitTab.FISH : null;
	}

	@Override
	/** 勾选 Meteor 钩子、箱子半径与开始/返回按钮。 */
	protected void init() {
		if (parent == null) addTabBar(KitTab.FISH);
		int left = panelLeft(320);
		optionsTop = contentTop();
		leaveHook = addRenderableWidget(Checkbox.builder(Component.literal("钩子交给 Meteor auto-fish"), this.font)
			.pos(left, optionsTop)
			.selected(config.fisherLeaveHookToMeteor)
			.build());
		leaveHook.setTooltip(Tooltip.create(Component.literal(
			"勾上后这边只锁开始时的位置和视角、满包存箱。抛钩收钩用 Meteor 的 auto-fish。关掉则自己抛收。")));
		rangeRow = optionsTop + CONTROL_ROW_STEP + SECTION_GAP;
		chestRange = addRenderableWidget(KitUi.field(this.font, left + FIELD_LABEL_X, rangeRow, 48, "",
			Integer.toString(Math.max(2, config.fisherChestRange)), 2));
		chestRange.setTooltip(Tooltip.create(Component.literal("开始钓鱼时在这个半径内找箱子。满包后走过去存，再走回钓点。")));

		addRenderableWidget(Button.builder(Component.literal(fisher.isActive() ? "停止钓鱼" : "开始钓鱼"), button -> {
			if (fisher.isActive()) {
				if (!saveFields()) return;
				fisher.stop(this.minecraft, "在界面中停止");
				showNotice(fisher.status(), 0xFFFF55);
				button.setMessage(Component.literal("开始钓鱼"));
			} else {
				startFish();
			}
		}).bounds(left, footerButtonY(), 155, 20)
			.tooltip(Tooltip.create(Component.literal("开始时记下当前坐标和视角，之后一直用这个角度抛竿。")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> {
			saveFields();
			onClose();
		}).bounds(left + 165, footerButtonY(), 155, 20).build());
	}

	@Override
	/** 画标题、半径标签与运行状态。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		if (parent != null) {
			KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(8), 0xFFFFFF);
		}
		KitUi.text(graphics, this.font, "附近箱子半径（格）", panelLeft(320), rangeRow + INLINE_LABEL_DY, 0xA0A0A0);
		String state = fisher.isActive() ? "运行中  " + fisher.status() : "未开始";
		KitUi.centered(graphics, this.font, state, center, stateRowAboveFooter(), fisher.isActive() ? 0x55FF55 : 0xA0A0A0);
		if (!notice.isEmpty()) {
			KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
		}
	}

	/** 保存配置后启动钓鱼。 */
	private void startFish() {
		if (!saveFields()) return;
		KitClient.startFisher(this.minecraft);
	}

	/** 把界面控件写回配置并落盘。 */
	private boolean saveFields() {
		try {
			config.fisherLeaveHookToMeteor = leaveHook.selected();
			config.fisherChestRange = (int)Math.round(KitUi.parse(chestRange, "箱子范围", 2.0, 8.0));
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
