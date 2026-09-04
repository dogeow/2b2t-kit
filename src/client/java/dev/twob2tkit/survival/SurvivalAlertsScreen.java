package dev.twob2tkit.survival;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.combat.HealingItems;
import dev.twob2tkit.combat.HealingItemsScreen;

/** 生存提醒设置界面。 */
public final class SurvivalAlertsScreen extends KitHudScreen {
	private final KitConfig config;
	private Checkbox healingAlert;
	private Checkbox netherGoldAlert;
	private Checkbox totemAlert;
	private Checkbox elytraAlert;
	private EditBox minimumHealing;
	private EditBox minimumTotems;
	private EditBox minimumElytra;
	private EditBox cooldown;
	private String draftHealing;
	private String draftTotems;
	private String draftElytra;
	private String draftCooldown;

	/** 打开生存提醒设置屏。 */
	public SurvivalAlertsScreen(Screen parent, KitConfig config) {
		super(Component.literal("twob2tkit 生存提醒"), parent);
		this.config = config;
	}

	@Override
	/** 开关与阈值输入。 */
	protected void init() {
		int left = panelLeft(300);
		if (minimumHealing != null) {
			draftHealing = minimumHealing.getValue();
			draftTotems = minimumTotems.getValue();
			draftElytra = minimumElytra.getValue();
			draftCooldown = cooldown.getValue();
		}

		healingAlert = checkbox(left, bodyTop(50), "回血物资不足", config.healingItemAlert);
		minimumHealing = numberField(left + 230, bodyTop(48), 70, first(draftHealing, config.minimumHealingItems), "回血物资最低数量");
		addRenderableWidget(Button.builder(Component.literal("多选回血物品"), button -> {
			if (save(false)) this.minecraft.setScreen(new HealingItemsScreen(this, config));
		}).bounds(left, bodyTop(74), 300, 20).build());

		netherGoldAlert = checkbox(left, bodyTop(104), "下界未穿金质护甲", config.netherGoldArmorAlert);

		totemAlert = checkbox(left, bodyTop(134), "不死图腾不足", config.totemAlert);
		minimumTotems = numberField(left + 230, bodyTop(132), 70, first(draftTotems, config.minimumTotems), "不死图腾最低数量");

		elytraAlert = checkbox(left, bodyTop(164), "鞘翅耐久过低", config.elytraDurabilityAlert);
		minimumElytra = numberField(left + 230, bodyTop(162), 70, first(draftElytra, config.minimumElytraDurability), "鞘翅最低耐久");

		cooldown = numberField(left + 230, bodyTop(192), 70, first(draftCooldown, config.survivalAlertCooldownSeconds), "重复提醒间隔秒数");

		addRenderableWidget(Button.builder(Component.literal("保存"), button -> save(true)).bounds(left, contentBottom(), 145, 20).build());
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose()).bounds(left + 155, contentBottom(), 145, 20).build());
	}

	@Override
	/** 画说明与当前库存摘要。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(300);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(12), 0xFFFFFF);
		KitUi.centered(graphics, this.font, "提醒会显示在屏幕中央和聊天栏，并播放提示音", center, headerY(26), 0xA0A0A0);
		KitUi.text(graphics, this.font, "最低数量", left + 230, bodyTop(38), 0xA0A0A0);
		KitUi.text(graphics, this.font, "最低数量", left + 230, bodyTop(122), 0xA0A0A0);
		KitUi.text(graphics, this.font, "最低耐久", left + 230, bodyTop(152), 0xA0A0A0);
		KitUi.text(graphics, this.font, "重复提醒间隔（秒）", left, bodyTop(198), 0xA0A0A0);
		int have = this.minecraft.player == null ? 0 : HealingItems.count(this.minecraft.player, HealingItems.normalize(config.healingItemIds));
		KitUi.centered(graphics, this.font, "计入：" + HealingItems.summary(config.healingItemIds), center, bodyTop(220), 0x55FFFF);
		KitUi.centered(graphics, this.font, "背包合计 " + have + " / 需要 " + config.minimumHealingItems, center, bodyTop(232),
			have >= config.minimumHealingItems ? 0x55FF55 : 0xFF5555);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, contentBottom() - 16, noticeColor);
	}

	/** 创建勾选框。 */
	private Checkbox checkbox(int x, int y, String text, boolean selected) {
		return addRenderableWidget(Checkbox.builder(Component.literal(text), this.font).pos(x, y).selected(selected).build());
	}

	/** 创建数字输入框。 */
	private EditBox numberField(int x, int y, int width, String value, String narration) {
		return addRenderableWidget(KitUi.field(this.font, x, y, width, narration, value, 4));
	}

	/** 写回配置。 */
	private boolean save(boolean announce) {
		try {
			config.minimumHealingItems = KitUi.parseInt(minimumHealing, "回血最低数量", 0, 999);
			config.minimumTotems = KitUi.parseInt(minimumTotems, "图腾最低数量", 0, 99);
			config.minimumElytraDurability = KitUi.parseInt(minimumElytra, "鞘翅最低耐久", 1, 431);
			config.survivalAlertCooldownSeconds = KitUi.parseInt(cooldown, "提醒间隔", 5, 600);
			config.healingItemAlert = healingAlert.selected();
			config.netherGoldArmorAlert = netherGoldAlert.selected();
			config.totemAlert = totemAlert.selected();
			config.elytraDurabilityAlert = elytraAlert.selected();
			config.save();
			if (announce) showNotice("生存提醒设置已保存", 0x55FF55);
			return true;
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return false;
		}
	}

	@Override
	/** 关屏前保存。 */
	public void onClose() {
		if (!save(false)) return;
		super.onClose();
	}

	@Override
	/** 回车保存。 */
	protected boolean onEnterPressed() {
		save(true);
		return true;
	}

	/** 解析数字草稿；失败用默认值。 */
	private static String first(String draft, int fallback) {
		return draft != null ? draft : Integer.toString(fallback);
	}
}
