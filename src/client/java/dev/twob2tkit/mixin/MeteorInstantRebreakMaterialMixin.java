package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.AutomationBridge;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** An already queued Meteor rotation callback cannot break an owned temporary work block. */
@Pseudo
@Mixin(targets="meteordevelopment.meteorclient.systems.modules.player.InstantRebreak",remap=false)
public abstract class MeteorInstantRebreakMaterialMixin {
    @Inject(method="sendPacket()V",at=@At("HEAD"),cancellable=true,remap=false)
    private void kit$keepMaterialMiningOwned(CallbackInfo info){
        if(AutomationBridge.materialMiningPacketBlocked())info.cancel();
    }
}
