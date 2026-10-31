package dev.twob2tkit.automation;
import net.minecraft.world.InteractionResult;
/** The same client-swing decision used by Minecraft.startUseItem; never another use. */
final class VanillaInteractionPolicy {
    static final int PROTOCOL=1;
    static boolean clientSwingRequired(InteractionResult result){
        return result instanceof InteractionResult.Success success
            &&success.swingSource()==InteractionResult.SwingSource.CLIENT;
    }
}
