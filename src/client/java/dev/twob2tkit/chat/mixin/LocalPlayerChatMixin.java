package dev.twob2tkit.chat.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import dev.twob2tkit.chat.core.LocalChatDelivery;
import net.minecraft.client.multiplayer.chat.ChatListener;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

@Mixin(LocalPlayer.class)
abstract class LocalPlayerChatMixin {
    @WrapOperation(method = "sendSystemMessage", at = @At(value = "INVOKE", target =
            "Lnet/minecraft/client/multiplayer/chat/ChatListener;handleSystemMessage(Lnet/minecraft/network/chat/Component;Z)V"))
    private void mcbilingual$trackLocalDelivery(ChatListener listener, Component message, boolean remote,
                                               Operation<Void> original) {
        // LocalPlayer uses the same chat path as server notices, even for messages it creates locally.
        LocalChatDelivery.run(() -> original.call(listener, message, remote));
    }
}
