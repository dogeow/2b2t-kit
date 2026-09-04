package dev.twob2tkit.mixin;

import dev.twob2tkit.adventure.LocalAdvancementManager;
import net.minecraft.advancements.AdvancementHolder;
import net.minecraft.client.multiplayer.ClientAdvancements;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link ClientAdvancements#setSelectedTab}。
 * <p>
 * 注入点：{@code HEAD}（可取消）。
 * 为何在此时机：本地注入的生存进度页签不能把选择同步给服务器；
 * 在发包前拦截，改为仅本机 {@code setSelectedTab(..., false)} 后取消原调用，
 * 避免向服务器发送不存在的进度 ID。
 */
@Mixin(ClientAdvancements.class)
public abstract class LocalAdvancementSelectionMixin {
	/** 选中本地进度标签时只改客户端选中态，不向服务器发包。 */
	@Inject(method = "setSelectedTab", at = @At("HEAD"), cancellable = true)
	private void kit$keepLocalTabClientSide(AdvancementHolder holder, boolean sendPacket, CallbackInfo info) {
		if (!sendPacket || !LocalAdvancementManager.isLocal(holder)) return;
		((ClientAdvancements) (Object) this).setSelectedTab(holder, false);
		info.cancel();
	}
}
