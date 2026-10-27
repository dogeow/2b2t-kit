package dev.twob2tkit.automation;

/** One guarded ordinary attack on a wild squid; never a kill or ink receipt. */
final class InkAttackPolicy {
    static final int PROTOCOL=3;
    private InkAttackPolicy(){}
    static boolean target(String type,boolean alive,boolean removed,boolean named,float health){
        return ("minecraft:squid".equals(type)||"minecraft:glow_squid".equals(type))&&alive&&!removed&&!named&&Float.isFinite(health)&&health>0;
    }
    static boolean environment(boolean inWater,boolean burning,int air,int workFloor){
        return !burning&&(!inWater||workFloor>0&&workFloor<=300&&air>=workFloor);
    }
}
