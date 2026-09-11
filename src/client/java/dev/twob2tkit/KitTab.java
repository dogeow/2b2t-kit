package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import dev.twob2tkit.adventure.ActivityChecklistScreen;
import dev.twob2tkit.borer.TunnelBorerScreen;
import dev.twob2tkit.chopper.AutoChopper;
import dev.twob2tkit.chopper.ChopperScreen;
import dev.twob2tkit.feeder.AutoFeeder;
import dev.twob2tkit.feeder.FeederScreen;
import dev.twob2tkit.fisher.AutoFisher;
import dev.twob2tkit.fisher.FisherScreen;
import dev.twob2tkit.planter.AutoPlanter;
import dev.twob2tkit.planter.PlanterScreen;
import dev.twob2tkit.storage.StorageRecordsScreen;
import dev.twob2tkit.surround.AutoSurround;
import dev.twob2tkit.surround.SurroundScreen;

/** 分页标签：创建屏幕、读配置旧名、打开指定标签。 */
public enum KitTab {
	BORER("盾构"),
	CRUISE("巡航"),
	SURROUND("围箱"),
	FEED("喂养"),
	PLANT("种田"),
	CHOP("挖树"),
	FISH("钓鱼"),
	CHECKLIST("行动清单"),
	STORAGE("仓库"),
	GUARD("保护"),
	MORE("更多"),
	SETTINGS("设置");

	final String label;

	KitTab(String label) {
		this.label = label;
	}

	/** 创建该标签对应的屏幕实例。 */
	Screen create(KitConfig config, KitController controller) {
		return switch (this) {
			case CRUISE -> new KitScreen(config, controller);
			case BORER -> new TunnelBorerScreen(config, KitClient.borer());
			case SURROUND -> surroundScreen(config);
			case FEED -> feedScreen(config);
			case PLANT -> plantScreen(config);
			case CHOP -> chopScreen(config);
			case FISH -> fishScreen(config);
			case CHECKLIST -> new ActivityChecklistScreen(null, config);
			case STORAGE -> new StorageRecordsScreen(null, config);
			case GUARD -> new GuardHomeScreen(config, controller);
			case MORE -> new AssistHomeScreen(config, controller);
			case SETTINGS -> new SettingsHomeScreen(config);
		};
	}

	/** 从配置字符串解析；兼容旧 TECH/HELP/VILLAGE，非法则巡航。 */
	static KitTab fromConfig(String value) {
		if (value == null || value.isBlank()) return CRUISE;
		if (value.equals("TECH")) return BORER;
		if (value.equals("HELP")) return MORE;
		if (value.equals("VILLAGE")) return MORE;
		try {
			return valueOf(value);
		} catch (IllegalArgumentException ignored) {
			return CRUISE;
		}
	}

	/** 顶栏按钮悬停说明。 */
	String tooltip() {
		return switch (this) {
			case BORER -> "向前挖、找矿、区域清除";
			case CRUISE -> "高空飞向目标坐标";
			case SURROUND -> "用方块把自己围起来";
			case FEED -> "自动喂食繁殖动物";
			case PLANT -> "自动锄地、播种、收成";
			case CHOP -> "找树从底部往上砍";
			case FISH -> "自动抛竿收杆";
			case CHECKLIST -> "行动清单与进度";
			case STORAGE -> "仓库快照记录";
			case GUARD -> "生命、死亡点、提醒";
			case MORE -> "村民、容器、助手";
			case SETTINGS -> "按键、界面、通用设置";
		};
	}

	/** 打开默认首页（巡航）。 */
	static Screen home(KitConfig config, KitController controller) {
		return new KitWorkspaceScreen(config, controller);
	}

	/** 切标签：先刷巡航草稿，写入 lastUiTab 再开对应屏。 */
	static void open(Minecraft client, KitTab tab) {
		if (client.screen instanceof KitScreen cruise) cruise.flushForTabSwitch();
		KitConfig config = KitClient.config();
		KitController controller = KitClient.controller();
		if (config == null || controller == null) return;
		config.lastUiTab = tab.name();
		config.save();
		client.setScreen(tab.create(config, controller));
	}

	/** 围箱屏；模块未就绪则回首页。 */
	private static Screen surroundScreen(KitConfig config) {
		AutoSurround surround = KitClient.surround();
		return surround == null ? home(config, KitClient.controller()) : new SurroundScreen(null, config, surround);
	}

	/** 喂养屏；模块未就绪则回首页。 */
	private static Screen feedScreen(KitConfig config) {
		AutoFeeder feeder = KitClient.feeder();
		return feeder == null ? home(config, KitClient.controller()) : new FeederScreen(null, config, feeder);
	}

	/** 种田屏；模块未就绪则回首页。 */
	private static Screen plantScreen(KitConfig config) {
		AutoPlanter planter = KitClient.planter();
		return planter == null ? home(config, KitClient.controller()) : new PlanterScreen(null, config, planter);
	}

	/** 挖树屏；模块未就绪则回首页。 */
	private static Screen chopScreen(KitConfig config) {
		AutoChopper chopper = KitClient.chopper();
		return chopper == null ? home(config, KitClient.controller()) : new ChopperScreen(null, config, chopper);
	}

	/** 钓鱼屏；模块未就绪则回首页。 */
	private static Screen fishScreen(KitConfig config) {
		AutoFisher fisher = KitClient.fisher();
		return fisher == null ? home(config, KitClient.controller()) : new FisherScreen(null, config, fisher);
	}
}
