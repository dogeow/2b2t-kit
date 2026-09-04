package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.network.protocol.game.ClientboundLoginPacket;
import net.minecraft.network.protocol.game.ClientboundRespawnPacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link ClientPacketListener} 的登录/重生包处理。
 * <p>
 * 注入点：{@code handleLogin} / {@code handleRespawn} 的 {@code TAIL}。
 * 为何在此时机：原版已从包里解析出 {@code commonPlayerSpawnInfo} 之后，
 * 再抓取种子哈希供结构定位等本地功能使用；过早注入字段可能尚未就绪。
 */
@Mixin(ClientPacketListener.class)
public abstract class ClientLoginSeedMixin {
	/** 登录完成后从生成信息捕获世界种子相关数据。 */
	@Inject(method = "handleLogin", at = @At("TAIL"))
	private void kit$captureLoginSeed(ClientboundLoginPacket packet, CallbackInfo info) {
		KitClient.captureSpawnSeed(packet.commonPlayerSpawnInfo());
	}

	/** 重生/切维后同样刷新种子相关数据。 */
	@Inject(method = "handleRespawn", at = @At("TAIL"))
	private void kit$captureRespawnSeed(ClientboundRespawnPacket packet, CallbackInfo info) {
		KitClient.captureSpawnSeed(packet.commonPlayerSpawnInfo());
	}
}
