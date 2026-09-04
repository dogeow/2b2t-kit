package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import net.minecraft.client.player.LocalPlayer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 注入目标：{@link LocalPlayer#isShiftKeyDown()}。
 * <p>
 * 注入点：{@code RETURN}，Mixin 优先级 2000。
 * 为何在此时机：漏斗/箱子等潜行放置需要持续为 {@code true}；
 * 在返回值确定后强制改写，即使其它客户端模组本拍已清掉潜行状态也能盖回去。
 */
@Mixin(value = LocalPlayer.class, priority = 2000)
public abstract class LocalPlayerShiftMixin {
	/** 放置需要潜行时，强制让本方法返回 true。 */
	@Inject(method = "isShiftKeyDown", at = @At("RETURN"), cancellable = true)
	private void kit$forceSneakForPlacement(CallbackInfoReturnable<Boolean> cir) {
		if (KitClient.forceSneakForPlacement()) {
			cir.setReturnValue(true);
		}
	}
}
