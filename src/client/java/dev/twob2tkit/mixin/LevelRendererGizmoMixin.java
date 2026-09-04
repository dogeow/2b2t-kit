package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.LevelRenderer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link LevelRenderer#finalizeGizmoCollection}。
 * <p>
 * 注入点：{@code HEAD}。
 * 为何在此时机：在每帧 gizmo 收集流程里发射指引（区域框、回家箭头等），
 * 与客户端 tick 解耦，避免同一拍连画两次叠成重影。
 */
@Mixin(LevelRenderer.class)
public abstract class LevelRendererGizmoMixin {
	/** 在本帧 gizmo 收集开始时发出 twob2tkit 的世界指引。 */
	@Inject(method = "finalizeGizmoCollection", at = @At("HEAD"))
	private void kit$emitFrameGizmos(CallbackInfo info) {
		KitClient.emitFrameGizmos(Minecraft.getInstance());
	}
}
