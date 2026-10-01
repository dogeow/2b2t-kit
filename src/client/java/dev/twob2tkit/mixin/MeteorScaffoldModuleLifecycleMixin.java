package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.AutomationBridge;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Observe external toggle round trips, so restoration cannot overwrite later user choices. */
@Pseudo
@Mixin(targets="meteordevelopment.meteorclient.systems.modules.Module",remap=false)
public abstract class MeteorScaffoldModuleLifecycleMixin {
    @Inject(method="toggle()V",at=@At("HEAD"),remap=false)
    private void kit$observeLeasedModuleToggle(CallbackInfo info){
        AutomationBridge.projectionScaffoldModuleToggleObserved(this);
        dev.twob2tkit.automation.MaterialMiningLease.moduleToggleObserved(this);
    }
}
