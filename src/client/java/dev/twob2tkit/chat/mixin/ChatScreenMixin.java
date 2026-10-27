package dev.twob2tkit.chat.mixin;

import dev.twob2tkit.chat.BilingualClient;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.network.chat.Style;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(ChatScreen.class)
public abstract class ChatScreenMixin {
    @Inject(method = "handleComponentClicked", at = @At("HEAD"), cancellable = true)
    private void mcbilingual$translateClick(Style style, boolean insert, CallbackInfoReturnable<Boolean> result) {
        if (style != null && BilingualClient.handleTranslationClick(style.getClickEvent())) result.setReturnValue(true);
    }
}
