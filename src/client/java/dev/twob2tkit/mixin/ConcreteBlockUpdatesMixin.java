package dev.twob2tkit.mixin;
import dev.twob2tkit.KitClient;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.network.protocol.game.ClientboundBlockUpdatePacket;
import net.minecraft.network.protocol.game.ClientboundSectionBlocksUpdatePacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** TAIL runs on the client thread after vanilla applies the authoritative server update. */
@Mixin(ClientPacketListener.class)
public abstract class ConcreteBlockUpdatesMixin {
    @Inject(method="handleBlockUpdate",at=@At("TAIL"))
    private void kit$concreteBlockUpdate(ClientboundBlockUpdatePacket packet,CallbackInfo info){
        dev.twob2tkit.automation.ProfessionalPrinter.serverBlock(packet.getPos(),packet.getBlockState());
        var job=KitClient.buildJob();if(job!=null)job.serverBlock(packet.getPos(),packet.getBlockState());
        var maker=KitClient.concrete();if(maker!=null)maker.serverBlock(packet.getPos(),packet.getBlockState());
    }
    @Inject(method="handleChunkBlocksUpdate",at=@At("TAIL"))
    private void kit$concreteSectionUpdate(ClientboundSectionBlocksUpdatePacket packet,CallbackInfo info){
        if(dev.twob2tkit.automation.ProfessionalPrinter.owned())packet.runUpdates(dev.twob2tkit.automation.ProfessionalPrinter::serverBlock);
        var job=KitClient.buildJob();if(job!=null && job.isActive())packet.runUpdates(job::serverBlock);
        var maker=KitClient.concrete();if(maker!=null && maker.isActive())packet.runUpdates(maker::serverBlock);
    }
}
