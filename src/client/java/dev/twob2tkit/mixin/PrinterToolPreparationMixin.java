package dev.twob2tkit.mixin;
import dev.twob2tkit.automation.ProfessionalPrinter;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** The upstream pick helper compares components with a pristine example tool. */
@Pseudo
@Mixin(targets="me.aleksilassila.litematica.printer.actions.PrepareAction",remap=false)
public abstract class PrinterToolPreparationMixin {
    @Inject(method="send",at=@At("TAIL"),remap=false)
    private void kit$prepareActualTool(Minecraft client,LocalPlayer player,CallbackInfo info){
        ProfessionalPrinter.prepareActualTool(this,client,player);
    }
}
