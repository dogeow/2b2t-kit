package dev.twob2tkit.adventure;

import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.AssistHomeScreen;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitController;
import dev.twob2tkit.KitHudScreen;

/** 旧入口，转到顶部「助手」标签。 */
public final class AdventureScreen extends KitHudScreen {
	private final KitConfig config;
	private final KitController controller;

	/** 旧助手入口，打开后立刻跳到 AssistHomeScreen。 */
	public AdventureScreen(Screen parent, KitConfig config, KitController controller) {
		super(Component.literal("助手"), parent);
		this.config = config;
		this.controller = controller;
	}

	@Override
	/** 关掉本屏，改开助手首页。 */
	protected void init() {
		this.minecraft.setScreen(new AssistHomeScreen(config, controller));
	}
}
