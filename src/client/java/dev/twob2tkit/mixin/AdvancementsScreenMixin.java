package dev.twob2tkit.mixin;

import dev.twob2tkit.adventure.LocalAdvancementManager;
import net.minecraft.client.gui.screens.advancements.AdvancementsScreen;
import net.minecraft.client.multiplayer.ClientAdvancements;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link AdvancementsScreen#init}。
 * <p>
 * 注入点：{@code HEAD}。
 * 为何在此时机：进度界面初始化一开始就确保本机生存树已注入到
 * {@link ClientAdvancements}，后续建页签/绘制才能看到本地进度；过晚可能漏第一帧。
 * 只写本机配置，不向服务器伪造进度。
 */
@Mixin(AdvancementsScreen.class)
public abstract class AdvancementsScreenMixin {
	@Shadow @Final private ClientAdvancements advancements;

	/** 打开进度界面时注入本地生存进度树。 */
	@Inject(method = "init", at = @At("HEAD"))
	private void kit$injectLocalSurvivalTree(CallbackInfo info) {
		LocalAdvancementManager.ensureInjected(advancements);
	}
}
