package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.BorerHost;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;

/** Optional host support: an already installed old host must keep normal melee available. */
final class BorerMeteorThreatLease {
    static boolean acquire(BorerHost host, Minecraft client, Entity target) {
        if (target == null || !target.isAlive() || client.player == null || !client.player.hasLineOfSight(target)) return false;
        try { return host.prepareMeleeTarget(target.getType()); }
        catch (LinkageError oldHost) { return false; }
    }
    static void release(BorerHost host) {
        try { host.releaseMeleeTarget(); }
        catch (LinkageError oldHost) { /* Old hosts never acquired this optional lease. */ }
    }
    private BorerMeteorThreatLease() {}
}
