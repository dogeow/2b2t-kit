package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import dev.twob2tkit.MeteorModules;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Camera;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Final first-person camera alignment, after ordinary player interpolation and Meteor camera adjustments. */
@Mixin(value = Camera.class, priority = 500)
public abstract class BorerCombatCameraMixin {
    @Shadow protected abstract void setRotation(float yaw, float pitch);
    @Inject(method = "alignWithEntity", at = @At("TAIL"))
    private void kit$visibleCombatAim(float partialTicks, CallbackInfo info) {
        Minecraft client = Minecraft.getInstance();
        RotationAim.Look look = KitClient.borerCombatLook(client);
        if (look == null || !client.options.getCameraType().isFirstPerson() || client.getCameraEntity() != client.player) return;
        // Do not hijack an independently positioned camera. The release gate waits instead.
        if (MeteorModules.isActive("meteordevelopment.meteorclient.systems.modules.render.Freecam")) return;
        setRotation(look.yaw(), look.pitch());
        KitClient.combatViewRendered(client, look);
    }
}
