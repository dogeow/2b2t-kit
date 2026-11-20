package dev.twob2tkit;

import net.minecraft.client.gui.screens.Screen;
import java.util.Locale;

import static dev.twob2tkit.FeaturePages.mc;
import static dev.twob2tkit.FeaturePages.open;

/** 出行分类：巡航、巡航选项、风景预加载与死亡点。 */
final class TravelPages {
	private TravelPages() {
	}

	/** 巡航坐标与开始。 */
	static void cruise(Screen parent, KitConfig config, KitController controller) {
		KitFormScreen panel = new KitFormScreen(parent, "巡航", "填写目标 X / Y / Z；Y 是巡航高度。返回保留草稿，不自动起飞。").bind(config).id("cruise");
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
		open(parent, panel);
	}

	/** 巡航挂机保护与绕障选项。 */
	static void cruiseOptions(Screen parent, KitConfig config) {
		KitFormScreen panel = new KitFormScreen(parent, "巡航选项", "挂机保护。填 0 即关闭对应项。");
		panel.slider("到达半径", "靠近目标多少格算到。", 1.0, 128.0, 1.0, () -> config.arrivalRadius, v -> config.arrivalRadius = v);
		panel.slider("玩家警戒", "挂机（钓鱼/巡航/挖树等）时附近有陌生玩家就下线。0=关。", 0.0, 256.0, 1.0, () -> config.playerRadius, v -> config.playerRadius = v);
		panel.slider("最低心数", "挂机时血量掉到这就下线。4=半血。0=关。", 0.0, 10.0, 0.5, () -> config.minHealth / 2.0, v -> {
			config.minHealth = v * 2.0;
			config.save();
		});
		panel.slider("挂机怪物半径", "走近的骷髅不下线。只在钓鱼时被打中一次才下。此项不再按距离踢人。", 0.0, 32.0, 1.0, () -> config.afkHostileRadius, v -> config.afkHostileRadius = v);
		panel.slider("卡住秒数", "一直不动就停。0=关。", 0, 600, () -> config.stuckSeconds, v -> config.stuckSeconds = v);
		panel.slider("转向速度", "度/tick，越大转得越快。", 1.0, 120.0, 1.0, () -> config.turnSpeed, v -> config.turnSpeed = v);
		panel.slider("障碍探测", "前方多少格内开始绕障。", 8.0, 128.0, 1.0, () -> config.obstacleLookAhead, v -> config.obstacleLookAhead = v);
		panel.slider("绕障环距", "贴身绕开后再平移多少格。", 4.0, 64.0, 1.0, () -> config.obstacleBypassDistance, v -> config.obstacleBypassDistance = v);
		panel.bool("到达后自动离线", "飞到点就断开服务器。", () -> config.disconnectOnArrival, v -> config.disconnectOnArrival = v);
		panel.bool("前方障碍自动绕行", "贴身先升高，远处再水平绕。", () -> config.obstacleAvoidance, v -> config.obstacleAvoidance = v);
		panel.bool("升空时挖掉头上", "基岩、箱子不挖。", () -> config.clearCeiling, v -> config.clearCeiling = v);
		open(parent, panel);
	}

	static void scenery(Screen parent, KitConfig c) {
		var b = KitClient.borer();
		var p = new KitFormScreen(parent, "风景预加载", "新建使用当前位置；继续上次保留原圆心、半径和进度。").bind(c).id("scenery");
		p.slider("新任务半径（格）", "16–4096；大半径耗时与磁盘占用更大。不会改变巡航目标。", 16, 4096, () -> c.sceneryRadiusBlocks, v -> c.sceneryRadiusBlocks = v);
		p.active(() -> b != null && b.isSceneryActive(), () -> {
			if (b != null && b.isSceneryActive()) b.stop(mc(), "手动停止风景任务，保留进度");
			else if (!KitClient.startScenery(mc(), c.sceneryRadiusBlocks, true)) p.showNotice(b == null ? "模块未就绪" : b.sceneryStatus(), 0xFF7777);
		}).runLabels("继续上次", "停止并保留").runUsesDraft(false);
		p.liveNote(() -> b == null ? "运行引擎未就绪" : b.sceneryStatus());
		p.note("按实际服务端视距补漏，采用引擎确认的缓存后端；只标记已确认接收并保存的区块。未获知的状态不会显示为完成。");
		p.action("当前位置新建任务", "替换上次风景任务前需要确认；不改挖矿工程或巡航坐标。", () -> {
			if (b != null && b.isActive()) { p.showNotice("请先停止当前任务，再新建风景任务", 0xFF7777); return; }
			if (!p.finishEdits()) return;
			mc().gui.setScreen(new KitConfirmScreen(p, "新建风景任务", "使用当前位置和半径 " + c.sceneryRadiusBlocks + " 格，替换上次风景任务的进度。", () -> {
				if (KitClient.startScenery(mc(), c.sceneryRadiusBlocks, false)) mc().gui.setScreen(null);
				else p.showNotice(b == null ? "模块未就绪" : b.sceneryStatus(), 0xFF7777);
			}));
		});
		open(parent, p);
	}

	/** 最近死亡点操作。 */
	static void death(Screen parent, KitConfig config, KitController controller) {
        dev.twob2tkit.combat.ServerDeathSync.sync(mc(),config);
		KitFormScreen panel = new KitFormScreen(parent, "最近死亡点", deathSummary(config));
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
