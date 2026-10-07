package dev.twob2tkit.mixin;
import io.netty.channel.Channel;
import net.minecraft.network.Connection;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
@Mixin(Connection.class)
public interface InventoryConnectionDiagnosticsAccess {
    @Accessor("channel") Channel kit$getChannel();
}
