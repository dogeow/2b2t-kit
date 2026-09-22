package dev.twob2tkit.combat;

/** Height is a preference, never a reason to wait through fatal damage. */
public final class EmergencyExitPolicy {
    public enum Decision{CLIMB,DISCONNECT}
    public static Decision decide(double health,double rise,long elapsed,boolean routeAvailable){
        return health<=6 || rise>=11.7 || elapsed>=8000 || !routeAvailable?Decision.DISCONNECT:Decision.CLIMB;
    }
    public static boolean safeStep(double x,double y,double z,double tx,double ty,double tz,double mx,double my,double mz,double radius){
        double before=(x-mx)*(x-mx)+(y-my)*(y-my)+(z-mz)*(z-mz);
        double after=(tx-mx)*(tx-mx)+(ty-my)*(ty-my)+(tz-mz)*(tz-mz);
        return after>=radius*radius || after>=before-.01;
    }
    private EmergencyExitPolicy(){}
}
