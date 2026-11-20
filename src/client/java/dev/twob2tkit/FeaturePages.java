package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;

/** 各分类配置页共用的打开方式：统一绑定 KitConfig 后显示。 */
final class FeaturePages {
	private FeaturePages() {
	}

	/** 绑定当前配置并打开页面。 */
	static void open(Screen parent, KitFormScreen panel) {
		mc().gui.setScreen(panel.bind(KitClient.config()));
	}

	/** 当前客户端实例。 */
	static Minecraft mc() {
		return Minecraft.getInstance();
	}
}
