package dev.twob2tkit;

import net.minecraft.client.gui.screens.Screen;
import java.util.Locale;

import static dev.twob2tkit.FeaturePages.mc;
import static dev.twob2tkit.FeaturePages.open;

/** 出行分类：巡航（含挂机保护与绕障）、风景预加载与死亡点。 */
final class TravelPages {
	private TravelPages() {
	}

	/** 巡航坐标与开始。 */
	static void cruise(Screen parent, KitConfig config, KitController controller) {
		KitFormScreen panel = new KitFormScreen(parent, "巡航", "填写目标 X / Y / Z；Y 是巡航高度。离开页面保留草稿，不自动起飞。").bind(config).id("cruise");
		panel.status(() -> controller.statusLine(mc()));
		panel.active(controller::isActive, () -> {
			if (controller.isActive()) controller.stop(mc(), "设置页停止巡航");
			else if (config.hasTarget) controller.start(mc(), config.targetX, config.targetZ, config.cruiseY);
			else panel.showNotice("请填写目标 X/Z 或填入当前位置", 0xFF7777);
		});
		panel.section("目的地");
		panel.edit("目标 X", "世界坐标；没有目标时必须填写。", () -> config.hasTarget ? KitUi.formatNumber(config.targetX) : "",
			v -> UiDraft.number(v, "目标 X", -30_000_000, 30_000_000, false), v -> { config.targetX = Double.parseDouble(v.trim()); config.hasTarget = true; config.save(); });
		panel.number("巡航 Y", "飞行高度，不是落地高度。", -64, 2048, false, () -> config.cruiseY, v -> config.cruiseY = v);
		panel.edit("目标 Z", "世界坐标；没有目标时必须填写。", () -> config.hasTarget ? KitUi.formatNumber(config.targetZ) : "",
			v -> UiDraft.number(v, "目标 Z", -30_000_000, 30_000_000, false), v -> { config.targetZ = Double.parseDouble(v.trim()); config.hasTarget = true; config.save(); });
		panel.action("填入当前位置 X/Z", "只填入草稿，保留巡航高度。", () -> {
			if (mc().player == null || controller.isActive()) return;
			panel.draftValue("目标 X", KitUi.formatNumber(mc().player.getX())); panel.draftValue("目标 Z", KitUi.formatNumber(mc().player.getZ()));
		});
		panel.action("填入当前高度", "使用当前脚底 Y。", () -> {
			if (mc().player != null && !controller.isActive()) panel.draftValue("巡航 Y", KitUi.formatNumber(mc().player.getY()));
		});
		panel.action("从剪贴板填入坐标", "支持 X Y Z、/tp 或 Chunkbase 坐标；只填写，不起飞。", () -> {
			if (controller.isActive()) return;
			var coords = KitUi.parseTeleport(mc().keyboardHandler.getClipboard());
			if (coords == null) { panel.showNotice("剪贴板未找到有效坐标", 0xFF7777); return; }
			panel.draftValue("目标 X", KitUi.formatNumber(coords.x())); panel.draftValue("目标 Z", KitUi.formatNumber(coords.z()));
			if (coords.y() != null) panel.draftValue("巡航 Y", KitUi.formatNumber(coords.y()));
		});
		panel.section("出行");
		panel.action("继续上次巡航", "使用控制器保存的目标，不把本页草稿当成新目标。", () -> { if (!controller.isActive() && controller.resume(mc())) mc().gui.setScreen(null); });
		panel.action("回地狱门", "按已记录的路线返航。", () -> KitClient.goNetherPortal(mc()));
		panel.advanced("挂机保护 · 填 0 关闭");
		panel.slider("玩家警戒", "挂机（钓鱼/巡航/挖树等）时附近有陌生玩家就下线。0=关。", 0.0, 256.0, 1.0, () -> config.playerRadius, v -> config.playerRadius = v);
		panel.slider("最低心数", "挂机时血量掉到这就下线。4=半血。0=关。", 0.0, 10.0, 0.5, () -> config.minHealth / 2.0, v -> {
			config.minHealth = v * 2.0;
			config.save();
		});
		panel.slider("挂机怪物半径", "走近的骷髅不下线。只在钓鱼时被打中一次才下。此项不再按距离踢人。", 0.0, 32.0, 1.0, () -> config.afkHostileRadius, v -> config.afkHostileRadius = v);
		panel.slider("卡住秒数", "一直不动就停。0=关。", 0, 600, () -> config.stuckSeconds, v -> config.stuckSeconds = v);
		panel.bool("到达后自动离线", "飞到点就断开服务器。", () -> config.disconnectOnArrival, v -> config.disconnectOnArrival = v);
		panel.advanced("飞行与绕障");
		panel.slider("到达半径", "靠近目标多少格算到。", 1.0, 128.0, 1.0, () -> config.arrivalRadius, v -> config.arrivalRadius = v);
		panel.slider("转向速度", "度/tick，越大转得越快。", 1.0, 120.0, 1.0, () -> config.turnSpeed, v -> config.turnSpeed = v);
		panel.bool("前方障碍自动绕行", "贴身先升高，远处再水平绕。", () -> config.obstacleAvoidance, v -> config.obstacleAvoidance = v);
		panel.slider("障碍探测", "前方多少格内开始绕障。", 8.0, 128.0, 1.0, () -> config.obstacleLookAhead, v -> config.obstacleLookAhead = v);
		panel.slider("绕障环距", "贴身绕开后再平移多少格。", 4.0, 64.0, 1.0, () -> config.obstacleBypassDistance, v -> config.obstacleBypassDistance = v);
		panel.bool("升空时挖掉头上", "基岩、箱子不挖。", () -> config.clearCeiling, v -> config.clearCeiling = v);
		open(parent, panel);
	}

	/** 主按钮按上次任务能否在当前世界继续而定：能继续就「继续上次」，否则直接「开始新任务」。 */
	static void scenery(Screen parent, KitConfig c) {
		scenery(parent,c,null);
	}

	record MapCentre(net.minecraft.client.multiplayer.ClientLevel level,double x,double z) {}

	static void scenery(Screen parent, KitConfig c, MapCentre center) {
		String location=center==null ? "当前位置" : "地图选点 "+(int)Math.floor(center.x())+", "+(int)Math.floor(center.z());
		var b = KitClient.borer();
		var saved = ScenerySavedTask.read(mc());
		boolean resumable = saved != null && saved.belongsTo(ScenerySavedTask.currentWorld(mc()));
		var p = new KitFormScreen(parent, "风景预加载", "以"+location+"为圆心，按半径补齐未加载区块。").bind(c).id("scenery");
		p.slider("新任务半径（格）", "16–32768；大范围按 512×512 格分批，耗时与磁盘占用随面积增加。", 16, 32768, () -> c.sceneryRadiusBlocks, v -> c.sceneryRadiusBlocks = v);
		Runnable startNew = () -> {
			if (b != null && b.isActive()) { p.showNotice("请先停止当前任务，再新建风景任务", 0xFF7777); return; }
			if (!p.finishEdits()) return;
			Runnable run = () -> {
				if (center!=null && mc().level!=center.level()) {
					p.showNotice("地图选点所属世界已变化，请重新选点",0xFF7777); return;
				}
				boolean started=center==null ? KitClient.startScenery(mc(),c.sceneryRadiusBlocks,false)
					: KitClient.startMapScenery(mc(),c.sceneryRadiusBlocks,center);
				if (started) mc().gui.setScreen(null);
				else p.showNotice(b == null ? "模块未就绪" : b.sceneryStatus(), 0xFF7777);
			};
			if (saved == null) run.run();
			else mc().gui.setScreen(new KitConfirmScreen(p, "新建风景任务", "使用"+location+"和半径 " + c.sceneryRadiusBlocks + " 格，替换上次（" + saved.place() + "）的进度。", run));
		};
		p.active(() -> b != null && b.isSceneryActive(), () -> {
			if (b != null && b.isSceneryActive()) b.stop(mc(), "手动停止风景任务，保留进度");
			else if (center!=null || !resumable) startNew.run();
			else if (!KitClient.startScenery(mc(), c.sceneryRadiusBlocks, true)) p.showNotice(b == null ? "模块未就绪" : b.sceneryStatus(), 0xFF7777);
		}).runLabels(resumable && center==null ? "继续上次" : "开始新任务", "停止并保留").runUsesDraft(false);
		p.status(() -> b == null ? "运行引擎未就绪" : b.sceneryStatus());
		if (resumable) p.note("上次任务：圆心 " + saved.x() + ", " + saved.z() + "，半径 " + saved.radius() + " 格。继续会保留原圆心和进度。");
		else if (saved != null) p.note("上次任务在 " + saved.place() + "，与当前连接或维度不同，不能继续；开始新任务会替换它。");
		if (resumable && center==null) p.action("改为从当前位置新建", "替换上次任务的进度前需要确认。", startNew);
		if (resumable && center!=null) p.action("继续上次", "沿用上次的圆心、半径与已保存区块。", () -> {
			if (mc().level!=center.level() || (b!=null && b.isActive())) {
				p.showNotice("请在原世界停止当前任务后再继续",0xFF7777); return;
			}
			if (KitClient.startScenery(mc(),c.sceneryRadiusBlocks,true)) mc().gui.setScreen(null);
			else p.showNotice(b==null ? "模块未就绪" : b.sceneryStatus(),0xFF7777);
		});
		if (resumable) p.action("扩大上次半径", "以原圆心扩大到滑块半径，同时复用 Bobby 缓存。", () -> {
			if (!p.finishEdits()) return;
			if (c.sceneryRadiusBlocks<=saved.radius()) {
				p.showNotice("请把半径调到大于 "+saved.radius()+" 格",0xFF7777);
				return;
			}
			if (KitClient.expandScenery(mc(),c.sceneryRadiusBlocks)) mc().gui.setScreen(null);
			else p.showNotice(b==null ? "模块未就绪" : b.sceneryStatus(),0xFF7777);
		});
		open(parent, p);
	}

	/** 最近死亡点操作。 */
	static void death(Screen parent, KitConfig config, KitController controller) {
        dev.twob2tkit.combat.ServerDeathSync.sync(mc(),config);
		KitFormScreen panel = new KitFormScreen(parent, "最近死亡点", "返回、设为巡航目标或复制坐标。");
		panel.status(() -> deathSummary(config));
		panel.action("自动返回死亡点上方", "升到安全高度，到达后不离线。", () -> {
			if (!config.hasDeathPoint) return;
            if(!dev.twob2tkit.combat.ServerDeathSync.currentScope(mc(),config)){panel.showNotice("这是其他服务器或角色的记录",0xFF7777);return;}
			if (mc().level == null || !mc().level.dimension().identifier().toString().equals(config.deathDimension)) { panel.showNotice("死亡点在另一维度，请先切换维度", 0xFF7777); return; }
			double safeY = Math.max(config.cruiseY, config.deathY + 32.0);
			controller.startDeathRecovery(mc(), config.deathX, config.deathZ, safeY);
			mc().gui.setScreen(null);
		});
		panel.action("设为巡航目标", "返回后可开始巡航。", () -> {
			if (!config.hasDeathPoint) return;
            if(!dev.twob2tkit.combat.ServerDeathSync.currentScope(mc(),config)){panel.showNotice("这是其他服务器或角色的记录",0xFF7777);return;}
			if (mc().level == null || !mc().level.dimension().identifier().toString().equals(config.deathDimension)) { panel.showNotice("死亡点在另一维度，请先切换维度", 0xFF7777); return; }
			config.targetX = config.deathX;
			config.targetZ = config.deathZ;
			config.cruiseY = Math.max(config.cruiseY, config.deathY + 32.0);
			config.hasTarget = true;
			config.save();
		});
		panel.action("复制坐标", "", () -> {
			if (!config.hasDeathPoint || mc().keyboardHandler == null) return;
			mc().keyboardHandler.setClipboard(String.format(Locale.ROOT, "%.1f %.1f %.1f", config.deathX, config.deathY, config.deathZ));
		});
		panel.danger("清除死亡点", "清除当前死亡点记录，不能通过返回撤销。", () -> {
			config.clearDeathPoint();
		});
		open(parent, panel);
	}

	/** 死亡点摘要文案。 */
	private static String deathSummary(KitConfig config) {
        if(!config.hasDeathPoint)return "还没有记录到当前死亡点。";
        String origin=config.deathSource.equals("server")?"服务器同步":config.deathSource.equals("client")?"在线记录":"旧版记录";
        String dimension=switch(config.deathDimension){case "minecraft:overworld"->"主世界";case "minecraft:the_nether"->"下界";case "minecraft:the_end"->"末地";default->config.deathDimension;};
        String time=config.deathTimeEpochMillis>0?java.time.format.DateTimeFormatter.ofPattern("MM-dd HH:mm:ss").withZone(java.time.ZoneId.systemDefault()).format(java.time.Instant.ofEpochMilli(config.deathTimeEpochMillis)):"死亡时间未提供";
        return String.format(Locale.ROOT,"%s · %s · X %.0f Y %.0f Z %.0f · %s",origin,dimension,config.deathX,config.deathY,config.deathZ,time);
	}
}
