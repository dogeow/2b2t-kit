package dev.twob2tkit.mixin;
import dev.twob2tkit.automation.ProfessionalPrinter;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Optional native printer integration; its rotation, item selection and placement actions remain native. */
@Pseudo
@Mixin(targets="me.aleksilassila.litematica.printer.Printer",remap=false)
public abstract class PrinterProposalMixin implements dev.twob2tkit.automation.PrinterGateInstalled {
    @Inject(method="onGameTick",at=@At("HEAD"),cancellable=true,remap=false)
    private void kit$gateProposal(CallbackInfoReturnable<Boolean> info){
        if(ProfessionalPrinter.owned()&&!ProfessionalPrinter.allowNativeProposal(this))info.setReturnValue(false);
    }
    @Inject(method="onGameTick",at=@At("RETURN"),remap=false)
    private void kit$proposalQueued(CallbackInfoReturnable<Boolean> info){
        if(ProfessionalPrinter.owned()&&Boolean.TRUE.equals(info.getReturnValue()))ProfessionalPrinter.nativeProposalQueued(this);
    }
}
