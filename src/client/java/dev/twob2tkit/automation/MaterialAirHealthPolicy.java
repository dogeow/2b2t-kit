package dev.twob2tkit.automation;

/** A healed tick must not conceal an injury during a currently owned waypoint. */
final class MaterialAirHealthPolicy {
    private MaterialAirHealthPolicy() {}
    static boolean interruptible(boolean underwater,double currentY,double targetY){
        // New injury must not stop a verified oxygen escape while still submerged.
        return !(underwater&&Double.isFinite(currentY)&&Double.isFinite(targetY)&&targetY>currentY+1);
    }
    static boolean interruptible(boolean underwater,double currentY,double targetY,boolean defensiveRise){
        if(defensiveRise&&Double.isFinite(currentY)&&Double.isFinite(targetY)&&targetY>=currentY-1)return false;
        return interruptible(underwater,currentY,targetY);
    }
    static boolean interrupted(float startingHealth,long startingHurtAt,float health,long hurtAt){
        return !Float.isFinite(startingHealth)||!Float.isFinite(health)||health<=0
            ||health<startingHealth||hurtAt>startingHurtAt;
    }
}
