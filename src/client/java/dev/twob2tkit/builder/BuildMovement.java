package dev.twob2tkit.builder;
/** Legacy depot movement policy; projection motion lives in the reloadable navigation engine. */
public final class BuildMovement {
    private BuildMovement(){}
    public static boolean vertical(double dy){return dy>.015 || dy<-.08;}
    public static boolean arrived(double dx,double dy,double dz){return Math.hypot(dx,dz)<.12 && !vertical(dy);}
}
