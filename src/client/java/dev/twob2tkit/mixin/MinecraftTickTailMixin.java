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
 * 注入点：{@code RETURN}，Mixin 优先级 500。
 * 为何在此时机：Meteor 等模组会在 tick 中途改玩家朝向；
 * 在方法返回时再写回巡航/盾构需要的朝向，避免本拍导航瞄准被覆盖。
 * 与 {@link MouseHandlerMixin} 的 {@code turnPlayer} RETURN 互补。
 */
@Mixin(value = Minecraft.class, priority = 500)
public abstract class MinecraftTickTailMixin {
	/** tick 结束后把导航锁定的朝向重新施加到玩家身上。 */
	@Inject(method = "tick", at = @At("RETURN"))
	private void kit$restoreNavigationRotationAfterMeteor(CallbackInfo info) {
		KitClient.reapplyNavigationRotation(Minecraft.getInstance());
	}
}
