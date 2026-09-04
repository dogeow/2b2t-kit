package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.CharacterEvent;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.function.BooleanSupplier;
import dev.twob2tkit.adventure.ActivityChecklistScreen;
import dev.twob2tkit.borer.BorerAreaMarks;
import dev.twob2tkit.borer.TunnelBorer;
import dev.twob2tkit.piglin.PiglinBrawler;
import dev.twob2tkit.recipe.RecipeGuideScreen;
import dev.twob2tkit.storage.StorageRecordsScreen;
import dev.twob2tkit.structure.NearbyStructuresScreen;
import dev.twob2tkit.villager.VillagerScanner;

/**
 * 模块栏：左侧菜单 + 右侧主内容。首页是总览，分类页是开关列表。
 * 仍是游戏里的 GuiGraphics，不是浏览器。
 */
final class ClickGuiScreen extends KitHudScreen {
	private static final int ROW_H = 18;
	private static final int SET_W = 44;
	private static final Nav[] NAV = {
		new Nav("home", "首页"),
		new Nav("cruise", "巡航"),
		new Nav("borer", "盾构"),
		new Nav("guard", "保护"),
		new Nav("help", "助手"),
		new Nav("settings", "设置")
	};

	private final KitConfig config;
	private final KitController controller;
	private String page = "home";
	private int scroll;
	private String hover = "";
	private int winX;
	private int winY;
	private int winW;
	private int winH;
	private boolean dragging;
	private boolean resizing;
	private int grabOx;
	private int grabOy;
	private ClickGuiPanelScreen detail;
	private ClickGuiPanelScreen settingsPanel;

	ClickGuiScreen(KitConfig config, KitController controller) {
		super(Component.literal("2b2t-kit"), null);
		this.config = config;
		this.controller = controller;
	}

	/** 恢复窗口几何并挂接设置面板。 */
	@Override
	protected void init() {
		winW = Math.max(ClickGuiStyle.MIN_WIN_W, Math.min(config.clickGuiW, this.width));
		winH = Math.max(ClickGuiStyle.MIN_WIN_H, Math.min(config.clickGuiH, this.height));
		if (config.clickGuiX < 0 || config.clickGuiY < 0) {
			winX = Math.max(0, (this.width - winW) / 2);
			winY = Math.max(0, (this.height - winH) / 3);
		} else {
			winX = config.clickGuiX;
			winY = config.clickGuiY;
		}
		clampWin();
		if (settingsPanel != null && this.font != null) {
			settingsPanel.attach(this.font, this.width, this.height);
		}
	}

	/** 不画原版半透明遮罩。 */
	@Override
	public void extractTransparentBackground(GuiGraphicsExtractor graphics) {
	}

	/** 画标题、侧栏导航与主内容。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		hover = "";
		int x0 = winX;
		int y0 = winY;
		int navW = ClickGuiStyle.NAV_W;
		int title = ClickGuiStyle.TITLE;
		graphics.fill(x0, y0, x0 + winW, y0 + title, ClickGuiStyle.COL_TITLE);
		graphics.fill(x0, y0 + title, x0 + navW, y0 + winH, ClickGuiStyle.COL_NAV);
		graphics.fill(x0 + navW, y0 + title, x0 + winW, y0 + winH, ClickGuiStyle.COL_MAIN);
		KitUi.text(graphics, this.font, "2b2t-kit", x0 + 8, y0 + 5, 0xFFFFFF);
		KitUi.text(graphics, this.font, KitUi.fit(this.font, homeStatus(), 120), x0 + 92, y0 + 5, 0xBBBBBB);
		boolean overClose = hitClose(mouseX, mouseY);
		if (overClose) graphics.fill(x0 + winW - 52, y0 + 2, x0 + winW - 6, y0 + title - 2, ClickGuiStyle.COL_HOVER);
		KitUi.text(graphics, this.font, "Esc关闭", x0 + winW - 48, y0 + 5, 0xFFAAAA);
		int navY = y0 + title + 6;
		for (Nav nav : NAV) {
			boolean on = page.equals(nav.id);
			boolean over = mouseX >= x0 && mouseX < x0 + navW && mouseY >= navY && mouseY < navY + ClickGuiStyle.NAV_ITEM_H;
			int bg = on ? ClickGuiStyle.COL_NAV_ON : (over ? ClickGuiStyle.COL_HOVER : 0);
			if (bg != 0) graphics.fill(x0 + 4, navY, x0 + navW - 4, navY + ClickGuiStyle.NAV_ITEM_H - 2, bg);
			KitUi.text(graphics, this.font, nav.label, x0 + 12, navY + 5, on ? 0xFFFFFF : 0xCCCCCC);
			navY += ClickGuiStyle.NAV_ITEM_H;
		}
		int mainX = x0 + navW + ClickGuiStyle.MAIN_PAD;
		int mainW = winW - navW - ClickGuiStyle.MAIN_PAD * 2;
		int mainY = y0 + title;
		if (detail != null) drawDetail(graphics, mouseX, mouseY, mainX, mainY, mainW);
		else if (page.equals("home")) drawHome(graphics, mouseX, mouseY, mainX, mainY, mainW);
		else if (page.equals("settings")) drawSettings(graphics, mouseX, mouseY, mainX, mainY, mainW);
		else drawList(graphics, mouseX, mouseY, mainX, mainY, mainW, pageTitle(), currentMods());
		int hx = x0 + winW - ClickGuiStyle.HANDLE;
		int hy = y0 + winH - ClickGuiStyle.HANDLE;
		graphics.fill(hx, hy, x0 + winW, y0 + winH, 0x88B24CFF);
		if (detail != null && hover.isEmpty() && !detail.hoverTip().isEmpty()) hover = detail.hoverTip();
		String hint = hover;
		KitUi.text(graphics, this.font, KitUi.fit(this.font, hint, mainW), mainX, y0 + winH - 14, 0xAAAAAA);
		if (!notice.isEmpty()) {
			KitUi.text(graphics, this.font, notice, mainX, y0 + winH - 26, noticeColor);
		}
	}

	/** 画右侧详情面板与返回。 */
	private void drawDetail(GuiGraphicsExtractor graphics, int mouseX, int mouseY, int x, int top, int w) {
		boolean overBack = mouseX >= x && mouseX < x + 48 && mouseY >= top + 6 && mouseY < top + 20;
		KitUi.text(graphics, this.font, "← 返回", x, top + 8, overBack ? 0xFFFFFF : 0xD0B0FF);
		KitUi.text(graphics, this.font, detail.heading(), x + 52, top + 8, 0xFFFFFF);
		int bodyY = top + 24;
		int bodyH = winY + winH - bodyY - 16;
		detail.embedIn(x, bodyY, w, Math.max(80, bodyH));
		detail.drawEmbedded(graphics, mouseX, mouseY);
	}

	/** 画首页双列快捷卡片。 */
	private void drawHome(GuiGraphicsExtractor graphics, int mouseX, int mouseY, int x, int top, int w) {
		KitUi.text(graphics, this.font, "首页", x, top + 8, 0xFFFFFF);
		KitUi.text(graphics, this.font, KitUi.fit(this.font, homeDetail(), w), x, top + 22, 0xA0A0A0);
		int y = top + 40;
		List<Mod> cards = homeMods();
		int colW = Math.max(120, (w - 8) / 2);
		for (int i = 0; i < cards.size(); i++) {
			Mod mod = cards.get(i);
			int cx = x + (i % 2) * (colW + 8);
			int cy = y + (i / 2) * (ClickGuiStyle.HOME_CARD_H + 6);
			boolean over = mouseX >= cx && mouseX < cx + colW && mouseY >= cy && mouseY < cy + ClickGuiStyle.HOME_CARD_H;
			boolean on = mod.active.getAsBoolean();
			int bg = over ? ClickGuiStyle.COL_HOVER : (on ? ClickGuiStyle.COL_ON : ClickGuiStyle.COL_ROW);
			graphics.fill(cx, cy, cx + colW, cy + ClickGuiStyle.HOME_CARD_H, bg);
			KitUi.text(graphics, this.font, mod.name, cx + 8, cy + 6, 0xFFFFFF);
			String sub = mod.opensPage ? "打开" : (on ? "运行中，点此停止" : "开始");
			KitUi.text(graphics, this.font, sub, cx + 8, cy + 18, 0xBBBBBB);
			if (mod.hasSettings) {
				boolean overSet = over && mouseX >= cx + colW - SET_W;
				KitUi.text(graphics, this.font, "设置", cx + colW - 36, cy + 12, overSet ? 0xFFFFFF : 0xD0B0FF);
				if (over) hover = overSet ? "打开设置" : mod.tip;
			} else if (over) hover = mod.tip;
		}
	}

	/** 画分类开关列表。 */
	private void drawList(GuiGraphicsExtractor graphics, int mouseX, int mouseY, int x, int top, int w, String title, List<Mod> mods) {
		KitUi.text(graphics, this.font, title, x, top + 8, 0xFFFFFF);
		int listTop = top + 26;
		int listBottom = winY + winH - 18;
		int y = listTop - scroll;
		for (Mod mod : mods) {
			if (y + ROW_H < listTop) {
				y += ROW_H;
				continue;
			}
			if (y > listBottom) break;
			boolean over = mouseX >= x && mouseX < x + w && mouseY >= y && mouseY < y + ROW_H && mouseY >= listTop;
			boolean on = mod.active.getAsBoolean();
			int bg = over ? ClickGuiStyle.COL_HOVER : (on ? ClickGuiStyle.COL_ON : ClickGuiStyle.COL_ROW);
			int drawY = Math.max(y, listTop);
			graphics.fill(x, drawY, x + w, Math.min(y + ROW_H, listBottom), bg);
			if (y >= listTop) {
				boolean rightLabel = mod.hasSettings || !mod.opensPage;
				int nameW = rightLabel ? w - 72 : w - 16;
				KitUi.text(graphics, this.font, KitUi.fit(this.font, mod.name, nameW), x + 8, y + 5,
					on ? 0xFFFFFF : 0xCCCCCC);
				if (mod.hasSettings) {
					boolean overSet = over && mouseX >= x + w - SET_W;
					KitUi.text(graphics, this.font, "设置", x + w - 36, y + 5, overSet ? 0xFFFFFF : 0xD0B0FF);
				} else if (!mod.opensPage) {
					ClickGuiPanelScreen.drawCheck(graphics, x + w - 16, y + 5, on);
				}
			}
			if (over) hover = mod.hasSettings && mouseX >= x + w - SET_W ? "打开设置" : mod.tip;
			y += ROW_H;
		}
	}

	/** 画设置页嵌入面板。 */
	private void drawSettings(GuiGraphicsExtractor graphics, int mouseX, int mouseY, int x, int top, int w) {
		KitUi.text(graphics, this.font, "设置", x, top + 8, 0xFFFFFF);
		int bodyY = top + 22;
		int bodyH = winY + winH - bodyY - 16;
		ClickGuiPanelScreen panel = settingsPanel();
		panel.embedIn(x, bodyY, w, Math.max(80, bodyH));
		panel.drawEmbedded(graphics, mouseX, mouseY);
		if (hover.isEmpty() && !panel.hoverTip().isEmpty()) hover = panel.hoverTip();
	}

	/** 懒创建通用设置面板。 */
	private ClickGuiPanelScreen settingsPanel() {
		if (settingsPanel == null) {
			settingsPanel = ClickGuiPages.general(this, config);
			if (this.font != null) settingsPanel.attach(this.font, this.width, this.height);
		}
		return settingsPanel;
	}

	/** 处理关闭、拖窗、导航与模块点击。 */
	@Override
	public boolean mouseClicked(MouseButtonEvent event, boolean doubleClick) {
		int mx = (int)event.x();
		int my = (int)event.y();
		if (event.button() != 0) return hitWin(mx, my);
		if (hitClose(mx, my)) {
			this.minecraft.setScreen(null);
			return true;
		}
		if (hitHandle(mx, my)) {
			resizing = true;
			grabOx = mx;
			grabOy = my;
			setDragging(true);
			return true;
		}
		if (hitTitle(mx, my)) {
			dragging = true;
			grabOx = mx - winX;
			grabOy = my - winY;
			setDragging(true);
			return true;
		}
		int x0 = winX;
		int y0 = winY;
		int navW = ClickGuiStyle.NAV_W;
		if (mx >= x0 && mx < x0 + navW && my >= y0 + ClickGuiStyle.TITLE && my < y0 + winH) {
			int navY = y0 + ClickGuiStyle.TITLE + 6;
			for (Nav nav : NAV) {
				if (my >= navY && my < navY + ClickGuiStyle.NAV_ITEM_H) {
					page = nav.id;
					scroll = 0;
					closeDetail();
					return true;
				}
				navY += ClickGuiStyle.NAV_ITEM_H;
			}
			return true;
		}
		int mainX = x0 + navW + ClickGuiStyle.MAIN_PAD;
		int mainW = winW - navW - ClickGuiStyle.MAIN_PAD * 2;
		int mainY = y0 + ClickGuiStyle.TITLE;
		if (detail != null) {
			if (mx >= mainX && mx < mainX + 48 && my >= mainY + 6 && my < mainY + 20) {
				closeDetail();
				return true;
			}
			return detail.mouseClickedEmbedded(event) || hitWin(mx, my);
		}
		if (page.equals("settings")) {
			return settingsPanel().mouseClickedEmbedded(event) || hitWin(mx, my);
		}
		if (page.equals("home")) {
			List<Mod> cards = homeMods();
			int colW = Math.max(120, (mainW - 8) / 2);
			int y = mainY + 40;
			for (int i = 0; i < cards.size(); i++) {
				int cx = mainX + (i % 2) * (colW + 8);
				int cy = y + (i / 2) * (ClickGuiStyle.HOME_CARD_H + 6);
				if (mx >= cx && mx < cx + colW && my >= cy && my < cy + ClickGuiStyle.HOME_CARD_H) {
					Mod mod = cards.get(i);
					if (mod.hasSettings && mx >= cx + colW - SET_W) mod.right.run();
					else mod.left.run();
					return true;
				}
			}
			return hitWin(mx, my);
		}
		List<Mod> mods = currentMods();
		int listTop = mainY + 26;
		int y = listTop - scroll;
		for (Mod mod : mods) {
			if (my >= Math.max(y, listTop) && my < y + ROW_H && my >= listTop && mx >= mainX && mx < mainX + mainW) {
				if (mod.hasSettings && mx >= mainX + mainW - SET_W) mod.right.run();
				else mod.left.run();
				return true;
			}
			y += ROW_H;
		}
		return hitWin(mx, my);
	}

	/** 拖移或缩放窗口。 */
	@Override
	public boolean mouseDragged(MouseButtonEvent event, double dx, double dy) {
		if (event.button() != 0) return super.mouseDragged(event, dx, dy);
		if (detail != null && detail.mouseDraggedEmbedded(event)) return true;
		if (dragging) {
			winX = (int)event.x() - grabOx;
			winY = (int)event.y() - grabOy;
			clampWin();
			return true;
		}
		if (resizing) {
			winW = (int)event.x() - winX;
			winH = (int)event.y() - winY;
			clampWin();
			return true;
		}
		return super.mouseDragged(event, dx, dy);
	}

	/** 结束拖窗并保存几何。 */
	@Override
	public boolean mouseReleased(MouseButtonEvent event) {
		if (detail != null) detail.mouseReleasedEmbedded();
		if (event.button() == 0 && (dragging || resizing)) {
			dragging = false;
			resizing = false;
			setDragging(false);
			saveWin();
			return true;
		}
		return super.mouseReleased(event);
	}

	/** 详情/列表滚轮。 */
	@Override
	public boolean mouseScrolled(double mx, double my, double sx, double sy) {
		if (detail != null && hitWin((int)mx, (int)my)) {
			return detail.mouseScrolledEmbedded(sy);
		}
		if (page.equals("settings") && hitWin((int)mx, (int)my)) {
			return settingsPanel().mouseScrolledEmbedded(sy);
		}
		if (hitWin((int)mx, (int)my) && !page.equals("home")) {
			int max = Math.max(0, currentMods().size() * ROW_H - (winH - 70));
			scroll = Math.max(0, Math.min(max, scroll - (int)Math.round(sy * ROW_H)));
			return true;
		}
		return super.mouseScrolled(mx, my, sx, sy);
	}

	/** Esc 关详情或交给父类。 */
	@Override
	public boolean keyPressed(KeyEvent event) {
		if (detail != null && detail.keyPressedEmbedded(event)) return true;
		if (detail != null && event.isEscape()) {
			closeDetail();
			return true;
		}
		return super.keyPressed(event);
	}

	/** 详情编辑字符。 */
	@Override
	public boolean charTyped(CharacterEvent event) {
		if (detail != null && detail.charTypedEmbedded(event)) return true;
		return super.charTyped(event);
	}

	/** 打开右侧详情设置。 */
	void showDetail(ClickGuiPanelScreen panel) {
		closeDetail();
		this.detail = panel;
		if (this.font != null) {
			panel.attach(this.font, this.width, this.height);
		}
	}

	/** 提交编辑并关掉详情。 */
	private void closeDetail() {
		if (detail != null) detail.finishEdits();
		detail = null;
	}

	/** 点是否在主窗内。 */
	private boolean hitWin(int mx, int my) {
		return mx >= winX && mx < winX + winW && my >= winY && my < winY + winH;
	}

	/** 点是否在标题栏。 */
	private boolean hitTitle(int mx, int my) {
		return mx >= winX && mx < winX + winW && my >= winY && my < winY + ClickGuiStyle.TITLE;
	}

	/** 点是否在关闭区。 */
	private boolean hitClose(int mx, int my) {
		return mx >= winX + winW - 52 && mx < winX + winW && my >= winY && my < winY + ClickGuiStyle.TITLE;
	}

	/** 点是否在右下缩放柄。 */
	private boolean hitHandle(int mx, int my) {
		return mx >= winX + winW - ClickGuiStyle.HANDLE && mx < winX + winW
			&& my >= winY + winH - ClickGuiStyle.HANDLE && my < winY + winH;
	}

	/** 把窗口夹在屏幕内。 */
	private void clampWin() {
		winW = Math.max(ClickGuiStyle.MIN_WIN_W, Math.min(winW, this.width));
		winH = Math.max(ClickGuiStyle.MIN_WIN_H, Math.min(winH, this.height));
		winX = Math.max(0, Math.min(winX, Math.max(0, this.width - winW)));
		winY = Math.max(0, Math.min(winY, Math.max(0, this.height - winH)));
	}

	/** 把窗口几何写入配置。 */
	private void saveWin() {
		config.clickGuiX = winX;
		config.clickGuiY = winY;
		config.clickGuiW = winW;
		config.clickGuiH = winH;
		config.save();
	}

	/** 当前导航中文标题。 */
	private String pageTitle() {
		for (Nav nav : NAV) {
			if (nav.id.equals(page)) return nav.label;
		}
		return "2b2t-kit";
	}

	/** 当前分类的模块列表。 */
	private List<Mod> currentMods() {
		return switch (page) {
			case "cruise" -> cruiseMods();
			case "borer" -> borerMods();
			case "guard" -> guardMods();
			case "help" -> helpMods();
			default -> homeMods();
		};
	}

	/** 标题栏运行中摘要。 */
	private String homeStatus() {
		List<String> bits = new ArrayList<>();
		if (controller.isActive()) bits.add("巡航");
		TunnelBorer borer = KitClient.borer();
		if (borer != null && borer.isActive()) bits.add(borer.mode().label);
		if (KitClient.fisher() != null && KitClient.fisher().isActive()) bits.add("钓鱼");
		if (KitClient.planter() != null && KitClient.planter().isActive()) bits.add("种田");
		if (KitClient.chopper() != null && KitClient.chopper().isActive()) bits.add("挖树");
		return bits.isEmpty() ? "空闲" : String.join(" · ", bits);
	}

	/** 首页副标题：巡航目标与盾构状态。 */
	private String homeDetail() {
		TunnelBorer borer = KitClient.borer();
		String borerLine = borer != null && borer.isActive()
			? "盾构运行中：" + borer.mode().label
			: "盾构未开  ·  " + BorerAreaMarks.sizeLabel(config);
		String cruiseLine = controller.isActive()
			? "巡航中"
			: (config.hasTarget
				? String.format("巡航目标 %.0f %.0f", config.targetX, config.targetZ)
				: "还没填巡航坐标");
		return cruiseLine + "   " + borerLine;
	}

	/** 首页快捷模块。 */
	private List<Mod> homeMods() {
		List<Mod> list = new ArrayList<>();
		list.add(mod("巡航", "没填坐标会打开坐标页。",
			() -> controller.isActive(),
			() -> {
				if (controller.isActive()) {
					controller.stop(this.minecraft, "首页停止巡航");
					return;
				}
				if (config.hasTarget) controller.start(this.minecraft, config.targetX, config.targetZ, config.cruiseY);
				else ClickGuiPages.cruise(this, config, controller);
			},
			() -> ClickGuiPages.cruise(this, config, controller)));
		list.add(borerMode("区域挖", TunnelBorer.Mode.AREA, "两点围成矩形往下挖。没标点会打开盾构设置。"));
		list.add(borerMode("向下挖", TunnelBorer.Mode.DOWN, "向下挖竖井。"));
		list.add(borerMode("自动找矿", TunnelBorer.Mode.ORE, "按勾选矿种找矿开道。"));
		list.add(mod("自动钓鱼", "锁定开始时的位置和视角。",
			() -> KitClient.fisher() != null && KitClient.fisher().isActive(),
			() -> KitClient.toggleFisher(this.minecraft),
			() -> ClickGuiPages.fisher(this, config)));
		list.add(openMod("盾构设置", "矿种、区域两点、一次挖高。", this::openBorer));
		return list;
	}

	/** 巡航分类模块。 */
	private List<Mod> cruiseMods() {
		List<Mod> list = new ArrayList<>();
		list.add(mod("巡航", "点卡片开始/停止。没填坐标会打开坐标页。点设置改坐标。",
			() -> controller.isActive(),
			() -> {
				if (controller.isActive()) {
					controller.stop(this.minecraft, "模块栏停止巡航");
					return;
				}
				if (config.hasTarget) controller.start(this.minecraft, config.targetX, config.targetZ, config.cruiseY);
				else ClickGuiPages.cruise(this, config, controller);
			},
			() -> ClickGuiPages.cruise(this, config, controller)));
		list.add(openMod("巡航坐标", "填 X / Y / Z、开始巡航。",
			() -> ClickGuiPages.cruise(this, config, controller)));
		list.add(openMod("巡航选项", "到达半径、绕障、挖顶、到达离线。",
			() -> ClickGuiPages.cruiseOptions(this, config)));
		list.add(openMod("地点收藏", "查看、新增、飞往已存地点。",
			() -> open(new KitSavedPlacesScreen(this, config, controller))));
		list.add(openMod("附近结构", "按种子列出村庄、前哨、要塞等。",
			() -> open(new NearbyStructuresScreen(this, config, controller, KitClient.seedScout()))));
		return list;
	}

	/** 盾构分类模块。 */
	private List<Mod> borerMods() {
		List<Mod> list = new ArrayList<>();
		list.add(borerMode("向前挖", TunnelBorer.Mode.FORWARD, "沿当前朝向开 1×2。右键打开盾构设置。"));
		list.add(borerMode("向下挖", TunnelBorer.Mode.DOWN, "向下挖阶梯。右键打开盾构设置。"));
		list.add(borerMode("自动找矿", TunnelBorer.Mode.ORE, "按勾选的矿种找矿开道。右键打开盾构设置。"));
		list.add(borerMode("区域挖", TunnelBorer.Mode.AREA, "两点围成矩形往下挖。太远可点准星或输入坐标。"));
		list.add(mod("沿路回家", "按挖矿路点走回起点。",
			() -> {
				TunnelBorer borer = KitClient.borer();
				return borer != null && borer.isGoingHome();
			},
			() -> KitClient.goBorerHome(this.minecraft),
			this::openBorer));
		list.add(mod("回家路点", "只显示回家箭头，不自动走。",
			() -> {
				TunnelBorer borer = KitClient.borer();
				return borer != null && borer.isShowingHomeRoute();
			},
			() -> {
				TunnelBorer borer = KitClient.borer();
				if (borer != null) borer.toggleHomeRoute(this.minecraft);
			},
			this::openBorer));
		list.add(openMod("盾构设置", "宽度、矿种、区域两点、遇岩浆、沿路回家。", this::openBorer));
		return list;
	}

	/** 某一挖法的开关卡片。 */
	private Mod borerMode(String name, TunnelBorer.Mode mode, String tip) {
		return mod(name, tip,
			() -> {
				TunnelBorer borer = KitClient.borer();
				return borer != null && borer.isActive() && borer.mode() == mode;
			},
			() -> {
				TunnelBorer borer = KitClient.borer();
				if (borer == null) return;
				if (borer.isActive() && borer.mode() == mode) borer.stop(this.minecraft, "模块栏关闭");
				else if (mode == TunnelBorer.Mode.AREA && (!config.borerAreaASet || !config.borerAreaBSet)) {
					openBorer();
				} else {
					KitClient.prepareForBorer(this.minecraft);
					borer.start(this.minecraft, mode);
				}
			},
			this::openBorer);
	}

	/** 打开盾构设置详情。 */
	private void openBorer() {
		ClickGuiPages.borer(this, config);
	}

	/** 保护分类模块。 */
	private List<Mod> guardMods() {
		List<Mod> list = new ArrayList<>();
		list.add(toggle("自动保护", "被怪物打了就打开 Meteor 杀戮光环和自动断开。岩浆烫伤不算。不自己挥剑。",
			() -> config.autoProtectOnHit,
			() -> {
				config.autoProtectOnHit = !config.autoProtectOnHit;
				config.save();
			}));
		list.add(mod("自动围箱", "用方块把自己围起来。右键选方块和形状。",
			() -> KitClient.surround() != null && KitClient.surround().isActive(),
			() -> KitClient.toggleSurround(this.minecraft),
			() -> ClickGuiPages.surround(this, config)));
		list.add(openMod("生存提醒", "治疗物品、鞘翅、图腾数量不够时提示。",
			() -> ClickGuiPages.survival(this, config)));
		list.add(openMod("最近死亡点", "飞回上次死亡坐标。",
			() -> ClickGuiPages.death(this, config, controller)));
		list.add(openMod("玩家白名单", "这些玩家靠近时不触发提醒。",
			() -> open(new KitTrustedPlayersScreen(this, config))));
		list.add(mod("自动打猪人", "下界刷经验：近战、反火球、射恶魂。右键设置。",
			() -> KitClient.brawler() != null && KitClient.brawler().isActive(),
			() -> {
				PiglinBrawler brawler = KitClient.brawler();
				if (brawler != null) brawler.toggle(this.minecraft);
			},
			() -> ClickGuiPages.brawler(this, config)));
		list.add(mod("恶魂防护", "没开打猪人时也反弹火球、射恶魂。",
			() -> config.ghastGuardEnabled,
			() -> {
				config.ghastGuardEnabled = !config.ghastGuardEnabled;
				config.save();
			},
			() -> ClickGuiPages.brawler(this, config)));
		return list;
	}

	/** 助手分类模块。 */
	private List<Mod> helpMods() {
		List<Mod> list = new ArrayList<>();
		list.add(mod("自动喂养", "走近动物按顺序喂。右键选种类。不要和 Meteor auto-breed 一起开。",
			() -> KitClient.feeder() != null && KitClient.feeder().isActive(),
			() -> KitClient.toggleFeeder(this.minecraft),
			() -> ClickGuiPages.feeder(this, config)));
		list.add(mod("自动种田", "收成熟作物再种。右键选作物和田大小。",
			() -> KitClient.planter() != null && KitClient.planter().isActive(),
			() -> KitClient.togglePlanter(this.minecraft),
			() -> ClickGuiPages.planter(this, config)));
		list.add(mod("自动挖树", "找树、砍、补种。右键设置范围。",
			() -> KitClient.chopper() != null && KitClient.chopper().isActive(),
			() -> KitClient.toggleChopper(this.minecraft),
			() -> ClickGuiPages.chopper(this, config)));
		list.add(mod("自动钓鱼", "锁定开始时的位置和视角，满包存箱。",
			() -> KitClient.fisher() != null && KitClient.fisher().isActive(),
			() -> KitClient.toggleFisher(this.minecraft),
			() -> ClickGuiPages.fisher(this, config)));
		list.add(toggle("村庄职业", "头顶显示现有职业，准星列出还缺的。",
			() -> {
				VillagerScanner scanner = KitClient.villagerScanner();
				return scanner != null && scanner.isEnabled();
			},
			() -> KitClient.toggleVillagerScan(this.minecraft)));
		list.add(mod("投影建造", "按 Litematica 投影摆背包里有的方块。右键打开页面。",
			() -> KitClient.machines() != null && KitClient.machines().isPlacing(),
			() -> {
				if (KitClient.machines() != null) KitClient.machines().toggle(this.minecraft);
			},
			() -> {
				if (KitClient.machines() != null) {
					open(new TechHomeScreen(this, KitClient.machines()));
				}
			}));
		list.add(toggle("回地狱门", "沿走过的路飞回记下的下界门。",
			() -> {
				TunnelBorer borer = KitClient.borer();
				return borer != null && borer.isReturningToPortal();
			},
			() -> KitClient.goNetherPortal(this.minecraft)));
		list.add(openMod("行动清单", "按目标列出要做的事。",
			() -> open(new ActivityChecklistScreen(this, config))));
		list.add(openMod("配方指南", "本地配方，不向服务器伪造。",
			() -> open(new RecipeGuideScreen(this, config))));
		list.add(openMod("仓库记录", "开过的箱子记在本地。",
			() -> open(new StorageRecordsScreen(this, config))));
		return list;
	}

	/** 关掉模块栏，回到分页界面。 */
	void switchToPages() {
		config.clickGui = false;
		config.save();
		KitTab.open(this.minecraft, KitTab.CRUISE);
	}

	/** 打开嵌套屏幕。 */
	private void open(Screen screen) {
		this.minecraft.setScreen(screen);
	}

	/** 无右侧设置的开关项。 */
	private static Mod toggle(String name, String tip, BooleanSupplier active, Runnable run) {
		return new Mod(name, tip, active, run, run, false, false);
	}

	/** 左开/停、右开设置的模块项。 */
	private static Mod mod(String name, String tip, BooleanSupplier active, Runnable left, Runnable right) {
		return new Mod(name, tip, active, left, right, true, false);
	}

	/** 只打开子页的入口项。 */
	private static Mod openMod(String name, String tip, Runnable open) {
		return new Mod(name, tip, () -> false, open, open, false, true);
	}

	/** 侧栏导航项。 */
	private record Nav(String id, String label) {
	}

	/** 模块栏一行/卡片数据。 */
	private record Mod(
		String name,
		String tip,
		BooleanSupplier active,
		Runnable left,
		Runnable right,
		boolean hasSettings,
		boolean opensPage
	) {
	}
}
