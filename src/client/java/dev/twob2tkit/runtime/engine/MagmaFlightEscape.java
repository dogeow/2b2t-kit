package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.util.Mth;
import net.minecraft.world.phys.AABB;

/** Verified short vertical lift from magma, retaining sneak if no safe lift exists. */
final class MagmaFlightEscape {
    private MagmaFlightEscape() {}

    static boolean tryStart(DefaultTunnelBorerEngine engine, LocalPlayer player, Minecraft client) {
        AABB body = player.getBoundingBox();
        // The current box can be crouched: include the standing expansion as well as one block of lift.
        double lift = 1.05 + Math.max(0.0, 1.8 - body.getYsize());
        AABB swept = body.expandTowards(0.0, lift, 0.0);
        boolean loaded = true, fluidFree = true;
        for (int x=Mth.floor(swept.minX); x<=Mth.floor(swept.maxX-1.0e-6); x++) {
            for (int z=Mth.floor(swept.minZ); z<=Mth.floor(swept.maxZ-1.0e-6); z++) {
                for (int y=Mth.floor(swept.minY); y<=Mth.floor(swept.maxY-1.0e-6); y++) {
                    BlockPos pos=new BlockPos(x,y,z);
                    if (!client.level.hasChunkAt(pos)) loaded=false;
                    else if (!client.level.getFluidState(pos).isEmpty()) fluidFree=false;
                }
            }
        }
        boolean clear = MagmaLiftPolicy.hasClearance(loaded,
            loaded && client.level.noCollision(player, swept), fluidFree);
        boolean started = clear && engine.enableMeteorFlight(player);
        MagmaLiftPolicy.Input input = MagmaLiftPolicy.input(started);
        client.options.keyJump.setDown(input.jump());
        client.options.keyShift.setDown(input.sneak());
        return started;
    }
}
