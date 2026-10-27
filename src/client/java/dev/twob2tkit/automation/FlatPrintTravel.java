package dev.twob2tkit.automation;

import net.minecraft.world.phys.Vec3;

/** Moving must not carry the player out of reach of an already queued real click. */
public final class FlatPrintTravel {
    private FlatPrintTravel() {}
    public static boolean horizontal(Vec3 delta) {
        return delta!=null && Double.isFinite(delta.lengthSqr())
            && Math.abs(delta.y)<=.025001 && delta.horizontalDistanceSqr()>1e-12;
    }
    public static boolean keepsReach(Vec3 eye,Vec3 probe,Vec3 pendingHit) {
        if(eye==null||probe==null||!Double.isFinite(eye.lengthSqr())
                ||!Double.isFinite(probe.lengthSqr())||probe.length()>.36)return false;
        return pendingHit==null || Double.isFinite(pendingHit.lengthSqr())
            && eye.add(probe).distanceToSqr(pendingHit)<=4.05*4.05;
    }
}
