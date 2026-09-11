package dev.twob2tkit.borer;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.ItemStack;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitTab;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.ItemIconButton;

/** 盾构主界面：模式 + 子页入口 + 固定底栏。 */
public final class TunnelBorerScreen extends KitHudScreen {
	private static final int FOOTER_H = 28;

	private final KitConfig config;
	private final TunnelBorer borer;
	private Button forwardMode;
	private Button homeRouteButton;
	private Button downMode;
	private Button oreMode;
	private Button areaMode;
	private Button startButton;
	private final java.util.EnumMap<TunnelBorer.OreTarget, ItemIconButton> oreButtons = new java.util.EnumMap<>(TunnelBorer.OreTarget.class);
	private ItemIconButton oreAllToggle;

	public TunnelBorerScreen(KitConfig config, TunnelBorer borer) {
		this(null, config, borer);
	}

	public TunnelBorerScreen(Screen parent, KitConfig config, TunnelBorer borer) {
		super(Component.literal("盾构机"), parent);
		this.config = config;
		this.borer = borer;
	}

	@Override
	/** 生电标签。 */
	protected KitTab currentTab() {
		return parent == null ? KitTab.BORER : null;
	}

	@Override
	/** 底栏按钮 Y。 */
	protected int footerButtonY() {
		return this.height - 80;
	}

	/** 内容区下沿，避开底栏。 */
	private int contentLimitY() {
		return footerButtonY() - FOOTER_H;
	}

	@Override
	/** 模式按钮、找矿勾选与子页入口。 */
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirectCategory(dev.twob2tkit.UiFeature.Category.MINING)) return;
		if (parent == null) addTabBar(KitTab.BORER);
		oreButtons.clear();
		oreAllToggle = null;
		forwardMode = downMode = oreMode = areaMode = null;
		homeRouteButton = null;

		TunnelBorer.Mode mode = TunnelBorer.Mode.fromConfig(config.borerLastMode);
		int left = panelLeft(340);
		int y = contentTop();
		int limit = contentLimitY();

		y = buildModeRow(left, y);
		if (y < limit && mode == TunnelBorer.Mode.ORE) y = buildOreIcons(left, y);
		if (y < limit) y = buildModeLink(left, y, mode);
		if (y < limit) y = buildSubLink(left, y, "轴向瞄准 ▸", "只沿东西南北上下挖；清空路点也在这。",
			() -> this.minecraft.setScreen(new BorerRouteScreen(this, config, borer)));
		if (y < limit) y = buildSubLink(left, y, "安全与回家 ▸", "封水、遇怪、挖完回家等。",
			() -> this.minecraft.setScreen(new BorerSafetyScreen(this, config, borer)));
		buildFooter(left);

		refreshModeButtons();
	}

	/** 向前/向下/找矿/区域模式按钮。 */
	private int buildModeRow(int left, int y) {
		int w = 66;
		int step = 68;
		homeRouteButton = addRenderableWidget(Button.builder(Component.literal(homeRouteLabel()), b -> toggleHomeRoute())
			.bounds(left, y, w, 20)
			.tooltip(Tooltip.create(Component.literal("开关金色回家箭头（只显示不自动走）。路点在「轴向瞄准」里可清空。")))
			.build());
		forwardMode = addRenderableWidget(Button.builder(Component.literal("向前挖"), b -> setMode(TunnelBorer.Mode.FORWARD))
			.bounds(left + step, y, w, 20).build());
		downMode = addRenderableWidget(Button.builder(Component.literal("向下挖"), b -> setMode(TunnelBorer.Mode.DOWN))
			.bounds(left + step * 2, y, w, 20).build());
		oreMode = addRenderableWidget(Button.builder(Component.literal("自动找矿"), b -> setMode(TunnelBorer.Mode.ORE))
			.bounds(left + step * 3, y, w, 20).build());
		areaMode = addRenderableWidget(Button.builder(Component.literal("区域挖"), b -> setMode(TunnelBorer.Mode.AREA))
			.bounds(left + step * 4, y, w, 20).build());
		return y + 24;
	}

	/** 回家路线按钮文案。 */
	private String homeRouteLabel() {
		if (borer != null && borer.isShowingHomeRoute()) return "路线：开";
		int trailPoints = borer == null ? 0 : borer.trailLength();
		return trailPoints > 0 ? "路线：" + trailPoints : "回家路线";
	}

	/** 只显示或关闭回家箭头。 */
	private void toggleHomeRoute() {
		if (borer == null) return;
		borer.toggleHomeRoute(this.minecraft);
		showNotice(borer.status(), 0x55FFFF);
		refreshModeButtons();
	}

	/** 找矿目标物品图标行。 */
	private int buildOreIcons(int left, int y) {
		int icon = 28;
		int gap = 3;
		int step = icon + gap;
		int limit = contentLimitY();
		int slot = 0;

		oreAllToggle = addOreIcon(left, y, icon, step, slot++, limit,
			new ItemStack(Items.COMPASS),
			Component.literal("全选任意矿石"),
			this::toggleAllOres);

		for (TunnelBorer.OreTarget ore : TunnelBorer.OreTarget.values()) {
			if (ore == TunnelBorer.OreTarget.ANY) continue;
			int by = y + (slot / 11) * step;
			if (by + icon > limit) break;
			ItemIconButton button = addOreIcon(left, y, icon, step, slot++, limit,
				new ItemStack(ore.icon()),
				Component.literal("开关：" + ore.label),
				() -> toggleOre(ore));
			oreButtons.put(ore, button);
		}
		int slots = Math.max(slot, 1);
		return y + ((slots + 10) / 11) * step + 2;
	}

	/** 加一个找矿目标图标按钮。 */
	private ItemIconButton addOreIcon(int left, int y, int icon, int step, int slot, int limit,
		ItemStack stack, Component tip, Runnable action) {
		int by = y + (slot / 11) * step;
		if (by + icon > limit) {
			return addRenderableWidget(new ItemIconButton(-9999, -9999, 1, 1, stack, tip, action));
		}
		return addRenderableWidget(new ItemIconButton(
			left + (slot % 11) * step, by, icon, icon, stack, tip, action));
	}

	/** 全选/清空找矿目标。 */
	private void toggleAllOres() {
		if (TunnelBorer.OreTarget.contains(config.borerOreTarget, TunnelBorer.OreTarget.ANY)) {
			deselectAllOres();
		} else {
			selectAllOres();
		}
	}

	/** 勾选全部找矿目标。 */
	private void selectAllOres() {
		config.borerOreTarget = TunnelBorer.OreTarget.ANY.name();
		config.save();
		refreshModeButtons();
		showNotice("找矿：全选任意矿石", 0x55FFFF);
	}

	/** 清空找矿目标。 */
	private void deselectAllOres() {
		config.borerOreTarget = TunnelBorer.OreTarget.DIAMOND.name();
		config.save();
		refreshModeButtons();
		showNotice("找矿：钻石", 0x55FFFF);
	}

	/** 按模式打开对应设置子页。 */
	private int buildModeLink(int left, int y, TunnelBorer.Mode mode) {
		if (mode == TunnelBorer.Mode.AREA) {
			y = buildSubLink(left, y, "区域与工程 ▸  " + BorerAreaMarks.sizeLabel(config),
				"同页设置范围、命名保存、加载工程、开始。", () -> this.minecraft.setScreen(new AreaSetupScreen(this, config)));
			addRenderableWidget(Button.builder(Component.literal("保存当前工程"), b -> {
				if (!config.borerAreaASet || !config.borerAreaBSet) { this.minecraft.setScreen(new AreaSetupScreen(this, config)); return; }
				String name = BorerAreaProjects.activeName(config);
				if (name.isBlank()) name = BorerAreaProjects.defaultName(config);
				config.upsertAreaProject(name, BorerAreaProjects.currentDimension(this.minecraft));
				showNotice("已保存：" + name, 0x77DDCC);
			}).bounds(left, y, 166, 20).build());
			addRenderableWidget(Button.builder(Component.literal("加载 / 管理工程"), b -> this.minecraft.setScreen(new AreaProjectsScreen(this, config))).bounds(left + 172, y, 168, 20).build());
			return y + 24;
		}
		return buildSubLink(left, y, "巷道设置 ▸  " + config.borerWidth + "×" + config.borerHeight,
			"断面、朝向、前探与找矿半径。", () -> this.minecraft.setScreen(new TunnelSetupScreen(this, config)));
	}

	/** 子页入口按钮。 */
	private int buildSubLink(int left, int y, String label, String tip, Runnable open) {
		addRenderableWidget(Button.builder(Component.literal(label), b -> open.run())
			.bounds(left, y, 340, 20)
			.tooltip(Tooltip.create(Component.literal(tip)))
			.build());
		return y + 24;
	}

	/** 开始/停止与返回底栏。 */
	private void buildFooter(int left) {
		int footerY = footerButtonY();
		startButton = addRenderableWidget(Button.builder(Component.literal("开始"), b -> startSaved())
			.bounds(left, footerY, 72, 20).build());
		addRenderableWidget(Button.builder(Component.literal("沿路回家"), b -> {
			if (borer == null) return;
			this.minecraft.setScreen(null);
			borer.goHome(this.minecraft);
		}).bounds(left + 80, footerY, 80, 20).build());
		addRenderableWidget(Button.builder(Component.literal("回地狱门"), b -> KitClient.goNetherPortal(this.minecraft))
			.bounds(left + 168, footerY, 80, 20).build());
		if (parent != null) {
			addBackButton(left + 256, footerY, 84);
		} else {
			addRenderableWidget(Button.builder(Component.literal("停止"), b -> {
				if (borer == null) return;
				borer.stop(this.minecraft, "在界面中停止");
				showNotice(borer.status(), 0xFFFF55);
			}).bounds(left + 256, footerY, 84, 20).build());
		}
	}

	@Override
	/** 画状态与找矿说明。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		int top = tabContentTop();
		if (!notice.isEmpty()) {
			KitUi.centered(graphics, this.font, KitUi.fit(this.font, notice, 340),
				center, top + 2, noticeColor);
		}
		int left = panelLeft(340);
		int footerY = footerButtonY();
		graphics.fill(left, footerY - 10, left + 340, footerY - 8, 0x44FFFFFF);
	}

	/** 写入上次模式并刷新按钮。 */
	private void setMode(TunnelBorer.Mode mode) {
		config.borerLastMode = mode.name();
		config.save();
		if (mode == TunnelBorer.Mode.AREA) { this.minecraft.setScreen(new AreaSetupScreen(this, config)); return; }
		rebuildWidgets();
		showNotice("已选" + mode.label + "，点开始启动", 0x55FFFF);
	}

	/** 切换单个找矿目标。 */
	private void toggleOre(TunnelBorer.OreTarget target) {
		config.borerOreTarget = TunnelBorer.OreTarget.toggle(config.borerOreTarget, target);
		config.save();
		refreshModeButtons();
		showNotice("找矿：" + TunnelBorer.OreTarget.labels(config.borerOreTarget), 0x55FFFF);
	}

	/** 用上次模式启动或停止盾构。 */
	private void startSaved() {
		if (borer != null && borer.isActive()) { borer.stop(this.minecraft, "界面停止"); refreshModeButtons(); return; }
		TunnelBorer.Mode mode = TunnelBorer.Mode.fromConfig(config.borerLastMode);
		if (mode == TunnelBorer.Mode.AREA && (!config.borerAreaASet || !config.borerAreaBSet)) {
			showNotice("区域挖要先设点A和点B（区域设置）", 0xFF5555);
			return;
		}
		if (borer == null) return;
		if (mode == TunnelBorer.Mode.AREA) KitClient.prepareForBorer(this.minecraft);
		borer.start(this.minecraft, mode);
		this.minecraft.setScreen(null);
	}

	/** 当前模式按钮变灰。 */
	private void refreshModeButtons() {
		TunnelBorer.Mode mode = TunnelBorer.Mode.fromConfig(config.borerLastMode);
		if (forwardMode != null) forwardMode.active = mode != TunnelBorer.Mode.FORWARD;
		if (homeRouteButton != null) {
			homeRouteButton.setMessage(Component.literal(homeRouteLabel()));
		}
		if (startButton != null) {
			startButton.active = borer != null;
			startButton.setMessage(Component.literal(borer != null && borer.isActive() ? "停止" : "开始"));
		}
		if (downMode != null) downMode.active = mode != TunnelBorer.Mode.DOWN;
		if (oreMode != null) oreMode.active = mode != TunnelBorer.Mode.ORE;
		if (areaMode != null) areaMode.active = mode != TunnelBorer.Mode.AREA;
		boolean all = TunnelBorer.OreTarget.contains(config.borerOreTarget, TunnelBorer.OreTarget.ANY);
		if (oreAllToggle != null) {
			oreAllToggle.setChosen(all);
			oreAllToggle.setIcon(
				new ItemStack(all ? Items.COMPASS : Items.BARRIER),
				Component.literal(all ? "已全选任意矿石，点一下只留钻石" : "未全选，点一下全选任意矿石"));
		}
		for (var entry : oreButtons.entrySet()) {
			TunnelBorer.OreTarget ore = entry.getKey();
			if (ore == TunnelBorer.OreTarget.ANY) {
				entry.getValue().setChosen(all);
			} else {
				entry.getValue().setChosen(all || TunnelBorer.OreTarget.contains(config.borerOreTarget, ore));
			}
		}
	}
}
