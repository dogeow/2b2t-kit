package dev.twob2tkit.mixin;

import dev.twob2tkit.KitKeys;
import net.minecraft.client.KeyboardHandler;
import net.minecraft.client.Minecraft;
import net.minecraft.client.input.KeyEvent;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Observe real foreground key events; native task key states never enter here. */
@Mixin(KeyboardHandler.class)
public abstract class KeyboardHandlerMixin {
    @Shadow @Final private Minecraft minecraft;

    @Inject(method = "keyPress", at = @At("HEAD"))
    private void kit$notePhysicalKey(long window, int action, KeyEvent event, CallbackInfo info) {
        KitKeys.notePhysicalKey(minecraft,event.key(),action);
    }
}
