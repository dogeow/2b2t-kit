package dev.twob2tkit.chopper;

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

/**
 * 自动挖树设置界面：走近/树叶/补种/范围等开关，以及开始停止。
 */
public final class ChopperScreen extends KitHudScreen {
	private final KitConfig config;
	private final AutoChopper chopper;
	private Checkbox walkTo;
	private Checkbox leaves;
	private Checkbox replant;
	private Checkbox requireLeaves;
	private Checkbox pickup;
	private EditBox range;

	public ChopperScreen(Screen parent, KitConfig config, AutoChopper chopper) {
		super(Component.literal("twob2tkit 自动挖树"), parent);
		this.config = config;
		this.chopper = chopper;
	}

	/** 当前标签；从父屏打开时不画顶栏。 */
	@Override
	protected KitTab currentTab() {
		return parent == null ? KitTab.CHOP : null;
	}

	/** 勾选框、范围输入与底栏按钮。 */
	@Override
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("CHOPPER", parent)) return;
		if (parent == null) addTabBar(KitTab.CHOP);
		int left = panelLeft(320);
		int optionsTop = contentTop();
		walkTo = checkbox(left, optionsTop, "走近再砍", config.chopperWalk);
		walkTo.setTooltip(Tooltip.create(Component.literal("站着够得着就落地砍（更快）。原木在头顶够不着时才开飞行。")));
		leaves = checkbox(left + 165, optionsTop, "连树叶一起挖", config.chopperLeaves);
		leaves.setTooltip(Tooltip.create(Component.literal("默认只砍原木，树叶会自己凋落。勾选后会挖树叶，并换成剪刀（空中也会换）")));
		replant = checkbox(left, optionsTop + CONTROL_ROW_STEP, "砍完补种树苗", config.chopperReplant);
		replant.setTooltip(Tooltip.create(Component.literal("树干砍完后，在原位置补种对应树苗（橡树、红树胚芽、菌类等）")));
		requireLeaves = checkbox(left + 165, optionsTop + CONTROL_ROW_STEP, "必须连着树叶", config.chopperRequireLeaves);
		requireLeaves.setTooltip(Tooltip.create(Component.literal("只砍树冠下的树。木头房子不会动")));
		pickup = checkbox(left, optionsTop + CONTROL_ROW_STEP * 2, "砍完去捡木头", config.chopperPickup);
		pickup.setTooltip(Tooltip.create(Component.literal("人往往停在树顶，木头掉在树根。勾选后会先落到掉落物上捡原木、树苗、苹果、木棍，再补种或找下一棵")));

		int rangeRow = optionsTop + CONTROL_ROW_STEP * 3 + SECTION_GAP;
		range = addRenderableWidget(KitUi.field(this.font, left + FIELD_LABEL_X, rangeRow, 70, "搜寻范围",
			KitUi.formatNumber(Math.max(4.0, config.chopperRange)), 4));

		addRenderableWidget(Button.builder(Component.literal(chopper.isActive() ? "停止挖树" : "开始挖树"), button -> {
			if (chopper.isActive()) {
				if (!saveFields()) return;
				chopper.stop(this.minecraft, "在界面中停止");
				showNotice(chopper.status(), 0xFFFF55);
				button.setMessage(Component.literal("开始挖树"));
			} else {
				startChopper();
			}
		}).bounds(left, footerButtonY(), 155, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> {
			saveFields();
			onClose();
		}).bounds(left + 165, footerButtonY(), 155, 20).build());
	}

	/** 画说明与运行统计。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(320);
		int center = this.width / 2;
		int optionsTop = contentTop();
		if (parent != null) KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(8), 0xFFFFFF);
		int rangeRow = optionsTop + CONTROL_ROW_STEP * 3 + SECTION_GAP;
		KitUi.text(graphics, this.font, "搜寻范围（格）", left, rangeRow + INLINE_LABEL_DY, 0xA0A0A0);
		String state = chopper.isActive()
			? "运行中：砍了 " + chopper.choppedLogs() + " 根  "
				+ chopper.treesDone() + " 棵  补种 " + chopper.replanted()
				+ "  捡 " + chopper.pickedLoot() + "  " + chopper.status()
			: "当前未启动";
		int stateRow = stateRowAboveFooter();
		KitUi.centered(graphics, this.font, state, center, stateRow, chopper.isActive() ? 0x55FF55 : 0xA0A0A0);
		KitUi.centered(graphics, this.font, "有斧砍原木，有剪刀剪树叶。够不着的高处才会飞", center, stateRow - 36, 0xA0A0A0);
		KitUi.centered(graphics, this.font, "红树连根一起砍。下界菌柄会补种对应真菌", center, stateRow - 18, 0xA0A0A0);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
	}

	/** 存配置后启动挖树并关界面。 */
	private void startChopper() {
		if (!saveFields()) return;
		KitClient.startChopper(this.minecraft);
		this.minecraft.setScreen(null);
	}

	/** 构造已勾选状态的复选框。 */
	private Checkbox checkbox(int x, int y, String text, boolean selected) {
		return addRenderableWidget(Checkbox.builder(Component.literal(text), this.font)
			.pos(x, y)
			.selected(selected)
			.build());
	}

	/** 把控件写回配置；校验失败则红字提示。 */
	private boolean saveFields() {
		try {
			config.chopperWalk = walkTo.selected();
			config.chopperLeaves = leaves.selected();
			config.chopperReplant = replant.selected();
			config.chopperRequireLeaves = requireLeaves.selected();
			config.chopperPickup = pickup.selected();
			config.chopperRange = KitUi.parse(range, "搜寻范围", 4.0, 32.0);
			config.save();
			return true;
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return false;
		}
	}

	/** 关界面前保存字段。 */
	@Override
	public void onClose() {
		saveFields();
		super.onClose();
	}
}
