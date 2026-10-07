package dev.twob2tkit.mixin;
import dev.twob2tkit.automation.InventoryDiagnostics;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.network.protocol.Packet;
import net.minecraft.network.protocol.game.ServerboundContainerClickPacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;
@Mixin(MultiPlayerGameMode.class)
public abstract class InventoryClientClickObservationMixin {
    @ModifyArg(method="handleContainerInput",at=@At(value="INVOKE",target="Lnet/minecraft/client/multiplayer/ClientPacketListener;send(Lnet/minecraft/network/protocol/Packet;)V"),index=0)
    private Packet<?> kit$observeClick(Packet<?> packet){
        if(packet instanceof ServerboundContainerClickPacket click)InventoryDiagnostics.outbound(click);return packet;
    }
}
