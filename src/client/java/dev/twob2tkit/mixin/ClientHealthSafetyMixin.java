package dev.twob2tkit.mixin;

import dev.twob2tkit.combat.EmergencyExit;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.network.protocol.game.ClientboundSetHealthPacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Vanilla has applied authoritative health on the client thread before Meteor's next Post tick. */
@Mixin(ClientPacketListener.class)
public abstract class ClientHealthSafetyMixin {
    @Inject(method="handleSetHealth",at=@At("TAIL"))
    private void kit$observeHealth(ClientboundSetHealthPacket packet,CallbackInfo info){
        EmergencyExit.observeHealth(Minecraft.getInstance());
    }
}
