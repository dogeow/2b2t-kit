package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.AutomationBridge;
import dev.twob2tkit.automation.AutoRefillCompatibility;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** AutoRefill cleans the cursor even when no replacement exists; an owned SDK cursor stays owned. */
@Pseudo
@Mixin(targets="org.anti_ad.mc.ipnext.event.autorefill.AutoRefillHandler",remap=false)
public abstract class InventoryProfilesAutoRefillGuardMixin {
    @Inject(method="onTickInGame()V",at=@At("HEAD"),cancellable=true,require=0)
    private void kit$ownedRefillTick(CallbackInfo info){
        if(AutoRefillCompatibility.tick(AutomationBridge.ownsMaterialInventory()))info.cancel();
    }
}
