package dev.twob2tkit.chopper;

import net.minecraft.world.phys.Vec3;
import java.util.function.DoublePredicate;

/** A tiny lift is valid only if both the lift and the following horizontal movement fit. */
final class ChopperCollisionRecovery {
    static Vec3 clearanceLift(Vec3 wanted,DoublePredicate canLift,DoublePredicate canContinue) {
        if(Math.abs(wanted.y)>.00001 || wanted.horizontalDistanceSqr()<.00001)return null;
        for(double height:new double[]{.05,.10,.15,.20})
            if(canLift.test(height)&&canContinue.test(height))return new Vec3(0,height,0);
        return null;
    }
}
