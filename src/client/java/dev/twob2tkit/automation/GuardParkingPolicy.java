package dev.twob2tkit.automation;

/** An unattended multiplayer client may keep its PvE guard only at a verified high hover. */
public final class GuardParkingPolicy {
    private GuardParkingPolicy() {}

    public static boolean ready(double x,double y,double z,double targetX,double targetY,double targetZ,
                                int groundY,float health,boolean flightActive,boolean guardArmed){
        return Double.isFinite(x)&&Double.isFinite(y)&&Double.isFinite(z)
            && Double.isFinite(targetX)&&Double.isFinite(targetY)&&Double.isFinite(targetZ)
            && health>=18&&flightActive&&guardArmed
            && targetY-groundY>=20&&y-groundY>=18
            && Math.hypot(x-targetX,z-targetZ)<=8&&Math.abs(y-targetY)<=2;
    }
}
