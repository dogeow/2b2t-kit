package dev.twob2tkit.automation;

/** Tight, frame-owned eligibility and braking for a supervised outdoor descent. */
public final class FreefallPolicy {
    public static final double EARLY_BRAKE=16.0;
    private FreefallPolicy() {}
    public static boolean eligible(double playerY,double brakeY,float health,boolean guard,boolean flight){
        return Double.isFinite(playerY)&&Double.isFinite(brakeY)
            && playerY-brakeY>24&&health>=18&&guard&&flight;
    }
    public static boolean brake(double playerY,double brakeY,float health,boolean screenOpen){
        return screenOpen||health<18||playerY<=brakeY+EARLY_BRAKE;
    }
}
