package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;

/** Continue only through a verified landing or existing guarded bridge/retreat logic. */
final class BorerNoSupportRecovery {
    private BorerNoSupportRecovery() {}
    static void handle(DefaultTunnelBorerEngine engine, Minecraft client, LocalPlayer player) {
        engine.occludedTicks++;
        BlockPos feet=player.blockPosition(), next=feet.relative(engine.forward);
        boolean immediateFluid=engine.isLava(client,feet.below()) || engine.isLava(client,next)
            || engine.isLava(client,next.below()) || BorerHazards.isWater(client,feet.below())
            || BorerHazards.isWater(client,next) || BorerHazards.isWater(client,next.below());
        int drop=engine.safeDropAhead(client,player);
        boolean safeDrop=BorerNoSupportPolicy.walkSafeDrop(player.onGround(),player.isInLava() || player.isInWater(),
            BorerHazards.playerOnMagma(client,player),immediateFluid,drop);
        if (safeDrop) {
            // The existing bridge helper refuses to cover ore or the target descent column.
            if (engine.occludedTicks>=40 && engine.place.placeStalledDescentSupport(client,player,drop)) {
                engine.occludedTicks=0;return;
            }
            engine.releaseMine(client);
            engine.clearMiningTarget(client,"no-support-safe-drop");
            client.options.keyShift.setDown(false);
            engine.faceForward(player);
            engine.nudgeToColumnCenter(client,player);
            client.options.keyUp.setDown(true);
            engine.attemptedForward=true;
            engine.status="前方落差已确认安全，直接下落 " + drop + " 格";
            engine.overlay(client,engine.status,0x55FFFF);
            return;
        }
        boolean ore=engine.mode==DefaultTunnelBorerEngine.Mode.ORE, collecting=engine.loot.active();
        if (BorerNoSupportPolicy.replanOre(ore,collecting,engine.occludedTicks)
                && engine.ores.skipActive(client,"前方无安全落点，铺路和绕行未成功，暂换目标")) {
            engine.occludedTicks=0;return;
        }
        if (BorerNoSupportPolicy.stopUnroutable(ore,engine.oreTargetPos!=null || engine.sideOreTargetPos!=null,
                collecting,engine.occludedTicks)) {
            engine.stop(client,"前方没有安全落点，无法铺路或绕行，已停挖保留现场");return;
        }
        engine.status="前方没有安全立足点，保持停步并尝试安全路线";
    }
}
