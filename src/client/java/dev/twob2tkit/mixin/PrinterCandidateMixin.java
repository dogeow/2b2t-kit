package dev.twob2tkit.mixin;
import dev.twob2tkit.automation.ProfessionalPrinter;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Pseudo
@Mixin(targets="me.aleksilassila.litematica.printer.guides.Guides",remap=false)
public abstract class PrinterCandidateMixin implements dev.twob2tkit.automation.PrinterCandidateGateInstalled {
    @Inject(method="getInteractionGuides",at=@At("HEAD"),remap=false)
    private void kit$candidate(@Coerce Object state,CallbackInfoReturnable<Object> info){
        if(ProfessionalPrinter.owned())ProfessionalPrinter.observeCandidate(state);
    }
}
