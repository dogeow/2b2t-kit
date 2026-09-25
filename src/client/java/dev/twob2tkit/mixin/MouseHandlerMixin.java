package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import net.minecraft.client.Minecraft;
import net.minecraft.client.MouseHandler;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link MouseHandler}。
 * <p>
 * 注入点：
 * <ul>
 *   <li>{@code onScroll} — {@code HEAD}（可取消）：全息预览滚轮调距离，拦截原版缩放/切物品</li>
 *   <li>{@code turnPlayer} — {@code RETURN}：鼠标转动后立刻再施加导航朝向</li>
 * </ul>
 * 为何在此时机：预览滚轮要在原版处理前抢走；朝向则要在本拍鼠标增量生效后再写回，
 * 否则巡航/盾构瞄准会被玩家微动鼠标冲掉（与 {@link MinecraftTickTailMixin} 配合）。
 */
@Mixin(MouseHandler.class)
public abstract class MouseHandlerMixin {
	@Shadow
	@Final
	private Minecraft minecraft;

	/** 无界面时把滚轮交给全息预览调距离；成功则取消原版滚动。 */
	@Inject(method = "onScroll", at = @At("HEAD"), cancellable = true)
	private void kit$previewDistance(long handle, double xoffset, double yoffset, CallbackInfo info) {
		if (this.minecraft.screen != null || this.minecraft.player == null) return;
		if (KitClient.handlePreviewScroll(yoffset)) info.cancel();
	}

	/** 玩家用鼠标转视角之后，重新施加巡航/盾构锁定的朝向。 */
	@Inject(method = "turnPlayer", at = @At("RETURN"))
	private void kit$keepCruiseLook(double mousea, CallbackInfo info) {
		KitClient.reapplyNavigationRotation(this.minecraft);
	}
}
