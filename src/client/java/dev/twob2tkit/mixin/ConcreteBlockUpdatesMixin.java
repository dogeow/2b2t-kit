package dev.twob2tkit.mixin;
import dev.twob2tkit.KitClient;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.network.protocol.game.ClientboundBlockUpdatePacket;
import net.minecraft.network.protocol.game.ClientboundBlockChangedAckPacket;
import net.minecraft.network.protocol.game.ClientboundSectionBlocksUpdatePacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** TAIL runs after vanilla receives server state; prediction correction may wait for sequence ACK. */
@Mixin(ClientPacketListener.class)
public abstract class ConcreteBlockUpdatesMixin {
    @Inject(method="handleBlockUpdate",at=@At("TAIL"))
    private void kit$concreteBlockUpdate(ClientboundBlockUpdatePacket packet,CallbackInfo info){
        dev.twob2tkit.storage.StorageLifecycle.blockUpdated(net.minecraft.client.Minecraft.getInstance(),packet.getPos());
        if((Object)this==net.minecraft.client.Minecraft.getInstance().getConnection()){
            dev.twob2tkit.automation.SingleBlockMiningConfirmation.serverBlock(net.minecraft.client.Minecraft.getInstance(),packet.getPos(),packet.getBlockState());
            dev.twob2tkit.automation.ProfessionalPrinter.serverBlock(packet.getPos(),packet.getBlockState());
            dev.twob2tkit.automation.AutomationBridge.serverBlock(packet.getPos(),packet.getBlockState());
        }
        var job=KitClient.buildJob();if(job!=null)job.serverBlock(packet.getPos(),packet.getBlockState());
        var maker=KitClient.concrete();if(maker!=null)maker.serverBlock(packet.getPos(),packet.getBlockState());
    }
    @Inject(method="handleChunkBlocksUpdate",at=@At("TAIL"))
    private void kit$concreteSectionUpdate(ClientboundSectionBlocksUpdatePacket packet,CallbackInfo info){
        packet.runUpdates((pos,state)->dev.twob2tkit.storage.StorageLifecycle.blockUpdated(net.minecraft.client.Minecraft.getInstance(),pos));
        if((Object)this==net.minecraft.client.Minecraft.getInstance().getConnection()){
            packet.runUpdates((pos,state)->dev.twob2tkit.automation.SingleBlockMiningConfirmation.serverBlock(net.minecraft.client.Minecraft.getInstance(),pos,state));
            if(dev.twob2tkit.automation.ProfessionalPrinter.owned())packet.runUpdates(dev.twob2tkit.automation.ProfessionalPrinter::serverBlock);
            packet.runUpdates(dev.twob2tkit.automation.AutomationBridge::serverBlock);
        }
        var job=KitClient.buildJob();if(job!=null && job.isActive())packet.runUpdates(job::serverBlock);
        var maker=KitClient.concrete();if(maker!=null && maker.isActive())packet.runUpdates(maker::serverBlock);
    }
    @Inject(method="handleBlockChangedAck",at=@At("TAIL"))
    private void kit$singleBlockChangedAck(ClientboundBlockChangedAckPacket packet,CallbackInfo info){
        var client=net.minecraft.client.Minecraft.getInstance();
        if((Object)this==client.getConnection())
            dev.twob2tkit.automation.SingleBlockMiningConfirmation.serverAck(client,packet.sequence());
    }
}
