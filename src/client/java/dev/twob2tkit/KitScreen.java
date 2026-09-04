package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.cruise.CruiseOptionsScreen;
import dev.twob2tkit.structure.NearbyStructuresScreen;

/** 巡航：坐标输入与开始/停止。 */
final class KitScreen extends KitHudScreen {
	private final KitConfig config;
	private final KitController controller;
	private EditBox targetX;
	private EditBox cruiseY;
	private EditBox targetZ;
	private boolean applyingTeleport;
	private Button resumeButton;
	private Button stopButton;
	private String draftX;
	private String draftZ;
	private String draftY;
	private int coordTop;

	KitScreen(KitConfig config, KitController controller) {
		this(null, config, controller);
	}

	KitScreen(Screen parent, KitConfig config, KitController controller) {
		super(Component.literal("twob2tkit 巡航"), parent);
		this.config = config;
		this.controller = controller;
	}

	/** 顶层为巡航标签；嵌套子页无标签。 */
	@Override
	protected KitTab currentTab() {
		return parent == null ? KitTab.CRUISE : null;
	}

	/** 布置坐标输入、地点/结构入口与开始停止。 */
	@Override
	protected void init() {
		if (parent == null) addTabBar(KitTab.CRUISE);
		int left = panelLeft(340);
		int top = contentTop();
		captureDrafts();

		coordTop = top;
		targetX = addRenderableWidget(KitUi.field(this.font, left, top + 12, 108, "X",
			draftOr(draftX, config.hasTarget ? config.targetX : currentX()), 128));
		cruiseY = addRenderableWidget(KitUi.field(this.font, left + 116, top + 12, 108, "Y",
			draftOr(draftY, config.cruiseY), 24));
		targetZ = addRenderableWidget(KitUi.field(this.font, left + 232, top + 12, 108, "Z",
			draftOr(draftZ, config.hasTarget ? config.targetZ : currentZ()), 24));
		targetX.setHint(Component.literal("X"));
		cruiseY.setHint(Component.literal("Y"));
		targetZ.setHint(Component.literal("Z"));
		targetX.setTooltip(Tooltip.create(Component.literal("可粘贴 /tp 382832 ~ 311344 或 Chunkbase 坐标，会自动拆到 X Y Z")));
		targetX.setResponder(this::applyTeleportIfPresent);

		int fillRow = top + 48;
		addRenderableWidget(Button.builder(Component.literal("填入当前位置"), button -> fillCurrentXZ())
			.bounds(left, fillRow, 108, 20)
			.tooltip(Tooltip.create(Component.literal("用当前站立位置填写目标 X / Z，不改巡航高度")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("填入当前高度"), button -> fillCurrentY())
			.bounds(left + 116, fillRow, 108, 20)
			.tooltip(Tooltip.create(Component.literal("用当前脚底高度填写巡航 Y")))
			.build());

		int cruiseRow = footerButtonY();
		int cruiseOptionsRow = cruiseRow - 24;
		int middleRow = cruiseOptionsRow - 32;

		int saved = config.savedPlaces == null ? 0 : config.savedPlaces.size();
		addRenderableWidget(Button.builder(Component.literal("地点收藏" + (saved > 0 ? " " + saved : "")), button -> openSavedPlaces())
			.bounds(left, middleRow, 108, 20)
			.tooltip(Tooltip.create(Component.literal("查看、新增、飞往已存地点。")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("附近结构"), button -> openNearbyStructures())
			.bounds(left + 116, middleRow, 108, 20).build());
		addRenderableWidget(Button.builder(Component.literal("回地狱门"), button -> KitClient.goNetherPortal(this.minecraft))
			.bounds(left + 232, middleRow, 108, 20)
			.tooltip(Tooltip.create(Component.literal("沿走过的路飞回记下的地狱门")))
			.build());

		addRenderableWidget(Button.builder(Component.literal("巡航选项"), button -> {
			applyBestEffort();
			this.minecraft.setScreen(new CruiseOptionsScreen(this, config));
		}).bounds(left, cruiseOptionsRow, 340, 20)
			.tooltip(Tooltip.create(Component.literal("到达半径、绕障、挖顶、到达离线。不常用，不放首页。")))
			.build());

		addRenderableWidget(Button.builder(Component.literal("开始巡航"), button -> start())
			.bounds(left, cruiseRow, 108, 20)
			.tooltip(Tooltip.create(Component.literal("回车也可开始；会保存当前填写的坐标")))
			.build());
		resumeButton = addRenderableWidget(Button.builder(Component.literal("继续上次"), button -> resume())
			.bounds(left + 116, cruiseRow, 108, 20).build());
		stopButton = addRenderableWidget(Button.builder(Component.literal("停止巡航"), button -> stop())
			.bounds(left + 232, cruiseRow, 108, 20).build());

		refreshButtons();
		setInitialFocus(targetX);
		if (parent != null) {
			addBackButton(left + 232, cruiseRow, 108);
		}
	}

	/** 每拍刷新继续/停止按钮可用态。 */
	@Override
	public void tick() {
		refreshButtons();
	}

	/** 画 XYZ 标签与提示。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int left = panelLeft(340);
		int center = this.width / 2;
		if (coordTop > 0) {
			KitUi.text(graphics, this.font, "X", left, coordTop, 0xFFFFFF);
			KitUi.text(graphics, this.font, "Y", left + 116, coordTop, 0xFFFFFF);
			KitUi.text(graphics, this.font, "Z", left + 232, coordTop, 0xFFFFFF);
		}
		if (!notice.isEmpty()) {
			KitUi.centered(graphics, this.font, notice, center, footerNoticeY(), noticeColor);
		}
	}

	/** 回车开始巡航。 */
	@Override
	protected boolean onEnterPressed() {
		start();
		return true;
	}

	/** 热键：运行中则停，否则开始。 */
	@Override
	protected boolean onStartStopKey() {
		if (controller.isActive()) {
			stop();
			return true;
		}
		start();
		return true;
	}

	/** 关屏前尽力保存坐标草稿。 */
	@Override
	public void onClose() {
		applyBestEffort();
		super.onClose();
	}

	/** 校验坐标并起飞。 */
	private void start() {
		ParsedValues values = parseValues();
		if (values == null) return;
		applySettings(values);
		controller.start(this.minecraft, values.targetX, values.targetZ, values.cruiseY);
		this.minecraft.setScreen(null);
	}

	/** 继续上次目标。 */
	private void resume() {
		applyBestEffort();
		if (controller.resume(this.minecraft)) this.minecraft.setScreen(null);
		else showNotice("没有保存过目标", 0xFF5555);
	}

	/** 在界面停止巡航。 */
	private void stop() {
		controller.stop(this.minecraft, "在 GUI 中停止");
		showNotice("已停止巡航", 0xFFFF55);
		refreshButtons();
	}

	/** 粘贴传送文本时拆到 XYZ。 */
	private void applyTeleportIfPresent(String value) {
		if (applyingTeleport || targetX == null || targetZ == null || cruiseY == null) return;
		if (!KitUi.looksLikeTeleport(value)) return;
		KitUi.TeleportCoords coords = KitUi.parseTeleport(value);
		if (coords == null) return;
		applyingTeleport = true;
		targetX.setValue(KitUi.formatNumber(coords.x()));
		targetZ.setValue(KitUi.formatNumber(coords.z()));
		if (coords.y() != null) {
			cruiseY.setValue(KitUi.formatNumber(coords.y()));
		}
		applyingTeleport = false;
		String yNote = coords.y() == null ? "，Y 仍用当前巡航高度" : "，Y " + KitUi.formatNumber(coords.y());
		showNotice("已解析坐标 X " + KitUi.formatNumber(coords.x()) + "  Z " + KitUi.formatNumber(coords.z()) + yNote, 0x55FF55);
	}

	/** 用当前位置填目标 XZ。 */
	private void fillCurrentXZ() {
		if (this.minecraft.player == null) return;
		targetX.setValue(KitUi.formatNumber(this.minecraft.player.getX()));
		targetZ.setValue(KitUi.formatNumber(this.minecraft.player.getZ()));
		showNotice("已填入当前 X / Z，可再改巡航高度后开始", 0x55FFFF);
	}

	/** 用当前高度填巡航 Y。 */
	private void fillCurrentY() {
		if (this.minecraft.player == null) return;
		cruiseY.setValue(KitUi.formatNumber(this.minecraft.player.getY()));
		showNotice("已填入当前高度作为巡航 Y", 0x55FFFF);
	}

	/** 切标签前保存有效坐标。 */
	void flushForTabSwitch() {
		if (targetX != null) applyBestEffort();
	}

	/** 打开附近结构页。 */
	private void openNearbyStructures() {
		applyBestEffort();
		this.minecraft.setScreen(new NearbyStructuresScreen(this, config, controller, KitClient.seedScout()));
	}

	/** 打开地点收藏页。 */
	private void openSavedPlaces() {
		applyBestEffort();
		this.minecraft.setScreen(new KitSavedPlacesScreen(this, config, controller));
	}

	/** 解析三框；失败则提示并返回 null。 */
	private ParsedValues parseValues() {
		applyTeleportIfPresent(targetX.getValue());
		try {
			return new ParsedValues(
				KitUi.parse(targetX, "X", -30_000_000.0, 30_000_000.0),
				KitUi.parse(targetZ, "Z", -30_000_000.0, 30_000_000.0),
				KitUi.parse(cruiseY, "Y", -64.0, 2048.0)
			);
		} catch (IllegalArgumentException exception) {
			showNotice(exception.getMessage(), 0xFF5555);
			return null;
		}
	}

	/** 能解析的坐标写入配置，不强制全合法。 */
	private void applyBestEffort() {
		Double x = KitUi.tryParse(targetX, -30_000_000.0, 30_000_000.0);
		Double z = KitUi.tryParse(targetZ, -30_000_000.0, 30_000_000.0);
		Double y = KitUi.tryParse(cruiseY, -64.0, 2048.0);
		if (x != null && z != null && y != null) {
			config.targetX = x;
			config.targetZ = z;
			config.cruiseY = y;
			config.hasTarget = true;
		}
		config.save();
	}

	/** 把已解析坐标写入配置。 */
	private void applySettings(ParsedValues values) {
		config.targetX = values.targetX;
		config.targetZ = values.targetZ;
		config.cruiseY = values.cruiseY;
		config.hasTarget = true;
		config.save();
	}

	/** 按是否有目标/是否巡航刷新按钮。 */
	private void refreshButtons() {
		if (resumeButton != null) resumeButton.active = config.hasTarget;
		if (stopButton != null) stopButton.active = controller.isActive();
	}

	/** 重建控件前记下输入框草稿。 */
	private void captureDrafts() {
		if (targetX == null) return;
		draftX = targetX.getValue();
		draftZ = targetZ.getValue();
		draftY = cruiseY.getValue();
	}

	/** 有草稿用草稿，否则格式化数字。 */
	private String draftOr(String draft, double fallback) {
		return draft != null ? draft : KitUi.formatNumber(fallback);
	}

	/** 玩家当前 X，无人则 0。 */
	private double currentX() {
		return this.minecraft.player == null ? 0.0 : this.minecraft.player.getX();
	}

	/** 玩家当前 Z，无人则 0。 */
	private double currentZ() {
		return this.minecraft.player == null ? 0.0 : this.minecraft.player.getZ();
	}

	/** 一次解析出的目标与巡航高度。 */
	private record ParsedValues(double targetX, double targetZ, double cruiseY) {
	}
}
