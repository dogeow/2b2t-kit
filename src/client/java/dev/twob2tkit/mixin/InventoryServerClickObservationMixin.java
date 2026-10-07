package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.InventoryDiagnostics;
import net.minecraft.network.protocol.game.ServerboundContainerClickPacket;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Exact integrated-server processing, after the real vanilla container click. */
@Mixin(ServerGamePacketListenerImpl.class)
public abstract class InventoryServerClickObservationMixin {
    @Shadow public ServerPlayer player;
    @Inject(method="handleContainerClick",at=@At("HEAD"))
    private void kit$receivedClick(ServerboundContainerClickPacket packet,CallbackInfo info){InventoryDiagnostics.received(player,packet);}
    @Inject(method="handleContainerClick",at=@At(value="INVOKE",target="Lnet/minecraft/world/inventory/AbstractContainerMenu;clicked(IILnet/minecraft/world/inventory/ContainerInput;Lnet/minecraft/world/entity/player/Player;)V",shift=At.Shift.BEFORE))
    private void kit$beforeClick(ServerboundContainerClickPacket packet,CallbackInfo info){InventoryDiagnostics.serverBefore(player,packet);}
    @Inject(method="handleContainerClick",at=@At(value="INVOKE",target="Lnet/minecraft/world/inventory/AbstractContainerMenu;clicked(IILnet/minecraft/world/inventory/ContainerInput;Lnet/minecraft/world/entity/player/Player;)V",shift=At.Shift.AFTER))
    private void kit$afterClick(ServerboundContainerClickPacket packet,CallbackInfo info){InventoryDiagnostics.serverAfter(player,packet);}
}
