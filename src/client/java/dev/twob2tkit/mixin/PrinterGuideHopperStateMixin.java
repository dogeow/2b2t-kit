package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.PrinterHopperPrediction;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Pseudo
@Mixin(targets="me.aleksilassila.litematica.printer.guides.Guide",remap=false)
public abstract class PrinterGuideHopperStateMixin {
    @Inject(method="statesEqual(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/block/state/BlockState;)Z",at=@At("HEAD"),cancellable=true,remap=false)
    private void kit$hopperPrediction(BlockState predicted,BlockState schematic,CallbackInfoReturnable<Boolean> result) {
        if(PrinterHopperPrediction.matches(predicted,schematic))result.setReturnValue(Boolean.TRUE);
    }
}
