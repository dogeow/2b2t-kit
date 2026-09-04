package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

/** 最近死亡点：查看坐标、返航、设为目标、复制或清除。 */
public final class DeathPointScreen extends KitHudScreen {
	private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").withZone(ZoneId.systemDefault());
	private final KitConfig config;
	private final KitController controller;

	DeathPointScreen(Screen parent, KitConfig config, KitController controller) {
		super(Component.literal("2b2t-kit 最近死亡点"), parent);
		this.config = config;
		this.controller = controller;
	}

	/** 布置返航、设目标、复制、清除与返回。 */
	@Override
	protected void init() {
		int left = panelLeft(300);
		Button returnButton = addRenderableWidget(Button.builder(Component.literal("自动返回死亡点上方"), button -> travel()).bounds(left, bodyTop(118), 300, 20).build());
		returnButton.active = config.hasDeathPoint && sameDimension();
		addRenderableWidget(Button.builder(Component.literal("设为巡航目标"), button -> applyAsTarget()).bounds(left, bodyTop(144), 145, 20).build())
			.active = config.hasDeathPoint;
		addRenderableWidget(Button.builder(Component.literal("复制坐标"), button -> copy()).bounds(left + 155, bodyTop(144), 145, 20).build())
			.active = config.hasDeathPoint;
		addRenderableWidget(Button.builder(Component.literal("清除死亡点"), button -> clear()).bounds(left, bodyTop(170), 145, 20).build())
			.active = config.hasDeathPoint;
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose()).bounds(left + 155, bodyTop(170), 145, 20).build());
	}

	/** 画死亡维度、坐标、凶手与被打记录。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(14), 0xFFFFFF);
		if (!config.hasDeathPoint) {
			KitUi.centered(graphics, this.font, "还没有记录到死亡坐标", center, bodyTop(56), 0xA0A0A0);
			KitUi.centered(graphics, this.font, "角色死亡时会自动记录维度与 X / Y / Z", center, bodyTop(74), 0xA0A0A0);
		} else {
			KitUi.centered(graphics, this.font, "维度：" + dimensionLabel(config.deathDimension)
				+ (config.deathActivity.isBlank() ? "" : "  ·  " + config.deathActivity), center, bodyTop(40), 0x55FFFF);
			KitUi.centered(graphics, this.font,
				String.format(Locale.ROOT, "X %.1f   Y %.1f   Z %.1f", config.deathX, config.deathY, config.deathZ),
				center, bodyTop(52), 0xFFFFFF);
			KitUi.centered(graphics, this.font, "死亡：" + formatTime(config.deathTimeEpochMillis)
				+ (config.deathKiller.isBlank() ? "" : "  凶手：" + config.deathKiller), center, bodyTop(64), 0xFFAAAA);
			if (!config.deathMessage.isBlank()) {
				KitUi.centered(graphics, this.font, KitUi.fit(this.font, config.deathMessage, 320), center, bodyTop(76), 0xA0A0A0);
			}
			if (config.lastAttackTimeEpochMillis > 0) {
				KitUi.centered(graphics, this.font, "上次被打：" + formatTime(config.lastAttackTimeEpochMillis)
					+ "  " + (config.lastAttacker.isBlank() ? "未知" : config.lastAttacker)
					+ String.format(Locale.ROOT, "  血%.1f", config.lastAttackHealth), center, bodyTop(88), 0xFFFFAA);
			}
			if (!sameDimension()) KitUi.centered(graphics, this.font, "当前维度不同，需先自行进入对应维度", center, bodyTop(102), 0xFFFF55);
		}
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, bodyTop(198), noticeColor);
		KitUi.centered(graphics, this.font, "返航会升至安全巡航高度；到达后不离线，请手动下降捡取", center, bodyTop(216), 0xA0A0A0);
	}

	/** 升到安全高度飞往死亡点上方，到达不离线。 */
	private void travel() {
		if (!config.hasDeathPoint || !sameDimension()) return;
		double safeY = Math.max(config.cruiseY, config.deathY + 32.0);
		controller.startDeathRecovery(this.minecraft, config.deathX, config.deathZ, safeY);
		this.minecraft.setScreen(null);
	}

	/** 把死亡 XZ 写入巡航目标并抬高巡航 Y。 */
	private void applyAsTarget() {
		if (!config.hasDeathPoint) return;
		config.targetX = config.deathX;
		config.targetZ = config.deathZ;
		config.cruiseY = Math.max(config.cruiseY, config.deathY + 32.0);
		config.hasTarget = true;
		config.save();
		showNotice("已设为巡航目标，返回主界面后可开始", 0x55FF55);
	}

	/** 把死亡坐标复制到剪贴板。 */
	private void copy() {
		if (!config.hasDeathPoint) return;
		String text = String.format(Locale.ROOT, "%.1f %.1f %.1f", config.deathX, config.deathY, config.deathZ);
		this.minecraft.keyboardHandler.setClipboard(text);
		showNotice("已复制：" + text, 0x55FFFF);
	}

	/** 清配置里的死亡点并刷新按钮。 */
	private void clear() {
		config.clearDeathPoint();
		showNotice("死亡点已清除", 0xFFFF55);
		rebuildWidgets();
	}

	/** 当前世界是否与死亡记录同一维度。 */
	private boolean sameDimension() {
		return this.minecraft.level != null && this.minecraft.level.dimension().identifier().toString().equals(config.deathDimension);
	}

	/** 把 epoch 毫秒格式成本地时间；无效则「无」。 */
	private static String formatTime(long epochMillis) {
		if (epochMillis <= 0) return "无";
		return TIME_FORMAT.format(Instant.ofEpochMilli(epochMillis));
	}

	/** 维度 id 转中文标签。 */
	private String dimensionLabel(String dimension) {
		return switch (dimension) {
			case "minecraft:overworld" -> "主世界";
			case "minecraft:the_nether" -> "下界";
			case "minecraft:the_end" -> "末地";
			default -> dimension;
		};
	}
}
