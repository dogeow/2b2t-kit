package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.AutomationBridge;
import dev.twob2tkit.automation.ProjectionScaffoldFill;
import net.minecraft.core.BlockPos;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Before Scaffold autoswitches or schedules any placement; unmanaged user Scaffold passes through. */
@Pseudo
@Mixin(targets="meteordevelopment.meteorclient.systems.modules.movement.Scaffold",remap=false)
public abstract class MeteorScaffoldTargetMixin implements ProjectionScaffoldFill.GateInstalled {
    @Inject(method="place(Lnet/minecraft/core/BlockPos;)Z",at=@At("HEAD"),cancellable=true,remap=false)
    private void kit$boundedScaffoldTarget(BlockPos target,CallbackInfoReturnable<Boolean> result){
        if(!AutomationBridge.projectionScaffoldTargetAllowed(target))result.setReturnValue(false);
    }
    @Inject(method="place(Lnet/minecraft/core/BlockPos;)Z",at=@At("RETURN"),remap=false)
    private void kit$scaffoldTargetEnded(BlockPos target,CallbackInfoReturnable<Boolean> result){
        AutomationBridge.projectionScaffoldCandidateEnded();
    }
}
