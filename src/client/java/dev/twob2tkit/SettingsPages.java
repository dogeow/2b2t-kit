package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import dev.twob2tkit.recipe.LocalRecipeBookInjector;

import static dev.twob2tkit.FeaturePages.mc;
import static dev.twob2tkit.FeaturePages.open;

/** 设置分类：通用偏好与运行/兼容。 */
final class SettingsPages {
	private SettingsPages() {
	}

	/** 通用偏好：外观、补货与配方。按键、翻译和引擎各有独立入口，不在这里重复。 */
	static void settings(Screen parent, KitConfig c) {
		var p = new KitFormScreen(parent, "通用设置", "开关即时保存。按键、聊天翻译和运行引擎在「设置」分类的独立入口。").bind(c).id("settings");
		p.section("界面");
		p.bool("简洁面板配色", "关闭为默认 Minecraft 风格；不改变功能或快捷键。", () -> c.clickGui, v -> c.clickGui = v);
		p.section("补货");
		p.bool("打开容器后自动补货", "根据行动清单与补货规则处理。", () -> c.autoRestockFromOpenedContainers, v -> c.autoRestockFromOpenedContainers = v);
		p.section("配方");
		p.bool("首次材料配方提示", "第一次拿到关键材料时在聊天里提示相关配方。", () -> c.localRecipeHints, v -> c.localRecipeHints = v);
		p.bool("背包与工作台配方书增强", "使用本地相关配方。", () -> c.recipeBookEnhancementEnabled, v -> LocalRecipeBookInjector.setEnhancementEnabled(mc(), v));
		p.danger("重置已看配方提示", "仅重置配方提示记录，不清空收藏、工程或物品。", () -> { c.seenRecipeHints.clear(); c.save(); });
		open(parent, p);
	}

	/** 版本、依赖与运行引擎热加载。 */
	static void diagnostics(Screen parent, KitConfig c) {
		var p = new KitFormScreen(parent, "运行与兼容", "信息为当前客户端状态；已安装不等于模块已经启用。").bind(c).id("diagnostics");
		String version = net.fabricmc.loader.api.FabricLoader.getInstance().getModContainer("twob2tkit").map(m -> m.getMetadata().getVersion().getFriendlyString()).orElse("开发环境");
		p.section("版本");
		p.note("主包版本：" + version);
		p.liveNote(() -> "运行引擎：" + engineLabel());
		for (String id : new String[]{"meteor-client", "bobby", "voxy", "litematica", "malilib"})
			p.note(id + "：" + net.fabricmc.loader.api.FabricLoader.getInstance().getModContainer(id).map(m -> "已安装 " + m.getMetadata().getVersion().getFriendlyString()).orElse("未安装"));
		p.action("复制诊断摘要", "只复制版本信息，不复制账号或聊天记录。", () -> mc().keyboardHandler.setClipboard("twob2tkit " + version + "; engine=" + engineLabel()));
		p.section("运行引擎");
		p.note("只替换 config/twob2tkit/runtime/twob2tkit-engine.jar；界面、按键和 Mixin 改动仍需重启。");
		p.action("检查并加载运行引擎", "更新挖矿、防护、施工寻路与走位；保留投影任务。", () -> { var r = KitClient.reloadBorerRuntime(mc(), false); p.showNotice(r.message(), r.success() ? 0x77DDCC : 0xFF7777); });
		p.danger("恢复内置引擎", "停止相关动作并恢复主包内置引擎，不删除工程。", () -> { var r = KitClient.reloadBorerRuntime(mc(), true); p.showNotice(r.message(), r.success() ? 0x77DDCC : 0xFF7777); });
		p.section("日志");
		p.note("游戏目录 logs/latest.log；config/twob2tkit 下的功能日志。");
		open(parent, p);
	}

	private static String engineLabel() {
		return KitClient.borer() == null ? "尚未初始化" : KitClient.borer().runtimeLabel();
	}
}
