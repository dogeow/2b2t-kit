package dev.twob2tkit.planter;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/** Farming movement is flat: an obstacle must stall/skip, never trigger a jump. */
public final class PlanterApproachTracker {
    private PlanterApproachTracker() {}
    public record WalkInputs(boolean forward, boolean jump) {}
    public static WalkInputs inputs(double horizontalDistance) {
        return new WalkInputs(Double.isFinite(horizontalDistance) && horizontalDistance > .2, false);
    }
    public static void walkToward(Minecraft client, LocalPlayer player, Vec3 destination) {
        var movement = inputs(Math.hypot(destination.x-player.getX(), destination.z-player.getZ()));
        client.options.keyUp.setDown(movement.forward());
        client.options.keyDown.setDown(false);
        client.options.keyLeft.setDown(false);
        client.options.keyRight.setDown(false);
        client.options.keyJump.setDown(movement.jump());
    }
}
