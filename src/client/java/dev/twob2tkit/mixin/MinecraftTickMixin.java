package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link Minecraft#tick()}。
 * <p>
 * 注入点：{@code HEAD}，Mixin 优先级 2000（偏晚，尽量排在其它 HEAD 注入之后）。
 * 为何在此时机：26.1 里玩家在 {@code tick} 开头就采样 {@code KeyMapping}；
 * 盾构/巡航等导航输入必须在采样之前写好，否则会出现「键已按下但人不走」。
 * 写在 {@code END_CLIENT_TICK} 会太晚。
 */
@Mixin(value = Minecraft.class, priority = 2000)
public abstract class MinecraftTickMixin {
	/** 在玩家采样按键之前分发导航 tick，写入移动/挖掘等输入。 */
	@Inject(method = "tick", at = @At("HEAD"))
	private void kit$tickBeforeMeteor(CallbackInfo info) {
		KitClient.tickNavigation(Minecraft.getInstance());
	}

	/** Scripted mining drives the normal game-mode API once per tick, even unfocused. */
	@Inject(method = "continueAttack", at = @At("HEAD"), cancellable = true)
	private void kit$ownedMining(boolean held, CallbackInfo info) {
		if (dev.twob2tkit.automation.AutomationBridge.ownsMining() || KitClient.concrete()!=null && KitClient.concrete().ownsMining()) info.cancel();
	}
}
