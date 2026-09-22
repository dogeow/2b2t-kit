package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.AutomationBridge;
import dev.twob2tkit.automation.CraftingCompatibility;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Keep the user's continuous-crafting preference; suppress only during owned Kit work. */
@Pseudo
@Mixin(targets="org.anti_ad.mc.ipnext.event.ContinuousCraftingHandler",remap=false)
public abstract class InventoryProfilesCraftingGuardMixin {
    @Inject(method="onTickInGame",at=@At("HEAD"),cancellable=true,require=0)
    private void kit$ownedTick(CallbackInfo info){
        CraftingCompatibility.tickHookSeen();
        if(AutomationBridge.ownsMaterialInventory())info.cancel();
    }
    @Inject(method="onCrafted",at=@At("HEAD"),cancellable=true,require=0)
    private void kit$ownedCraft(CallbackInfo info){
        if(AutomationBridge.ownsMaterialInventory())info.cancel();
    }
}
