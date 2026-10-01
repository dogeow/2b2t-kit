package dev.twob2tkit.mixin;

import dev.twob2tkit.automation.AutomationBridge;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.network.protocol.game.ClientboundContainerSetContentPacket;
import net.minecraft.network.protocol.game.ClientboundContainerSetSlotPacket;
import net.minecraft.network.protocol.game.ClientboundSetPlayerInventoryPacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Read-only, current-connection observations after vanilla applies inventory packets. */
@Mixin(ClientPacketListener.class)
public abstract class BucketInventoryUpdatesMixin {
    @Inject(method="handleSetPlayerInventory",at=@At("TAIL"))
    private void kit$bucketInventory(ClientboundSetPlayerInventoryPacket packet,CallbackInfo info) {
        if((Object)this==Minecraft.getInstance().getConnection())
            AutomationBridge.serverBucketInventory(this,0,packet.slot(),true,packet.contents());
    }
    @Inject(method="handleContainerSetSlot",at=@At("TAIL"))
    private void kit$bucketSlot(ClientboundContainerSetSlotPacket packet,CallbackInfo info) {
        if((Object)this==Minecraft.getInstance().getConnection()&&packet.getContainerId()==0)
            AutomationBridge.serverBucketInventory(this,0,packet.getSlot(),false,packet.getItem());
    }
    @Inject(method="handleContainerContent",at=@At("TAIL"))
    private void kit$bucketContent(ClientboundContainerSetContentPacket packet,CallbackInfo info) {
        var c=Minecraft.getInstance();
        if((Object)this!=c.getConnection()||c.player==null||packet.containerId()!=0)return;
        int slot=36+c.player.getInventory().getSelectedSlot();
        if(slot>=36&&slot<45&&slot<packet.items().size())
            AutomationBridge.serverBucketInventory(this,0,slot,false,packet.items().get(slot));
    }
}
