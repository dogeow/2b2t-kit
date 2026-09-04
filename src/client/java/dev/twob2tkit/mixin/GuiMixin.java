package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Gui;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link Gui#extractRenderState}。
 * <p>
 * 注入点：{@code TAIL}。
 * 为何在此时机：原版 HUD 状态已抽取完毕后，再叠画 twob2tkit 的屏幕 HUD
 * （盾构状态、AI 面板等），避免被原版后续逻辑盖掉或排到错误层级。
 */
@Mixin(Gui.class)
public abstract class GuiMixin {
	/** 在原版 GUI 抽取之后绘制本 Mod 的屏幕叠加 HUD。 */
	@Inject(method = "extractRenderState", at = @At("TAIL"))
	private void kit$renderScreenHud(GuiGraphicsExtractor graphics, DeltaTracker deltaTracker, CallbackInfo info) {
		KitClient.renderScreenHud(Minecraft.getInstance(), graphics);
	}
}
