package dev.twob2tkit.chopper;

/** A restored Flight hover beside a proved dry floor is a valid side standby. */
final class ChopperStandbyPolicy {
    private ChopperStandbyPolicy(){}
    static boolean arrived(boolean safeFloor,double distanceSquared,double horizontalSpeed,double verticalSpeed){
        return safeFloor&&Double.isFinite(distanceSquared)&&distanceSquared>=0&&distanceSquared<.04
            &&Double.isFinite(horizontalSpeed)&&horizontalSpeed>=0&&horizontalSpeed<=.01
            &&Double.isFinite(verticalSpeed)&&Math.abs(verticalSpeed)<=.1;
    }
}
