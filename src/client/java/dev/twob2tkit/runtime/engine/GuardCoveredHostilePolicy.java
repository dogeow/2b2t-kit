package dev.twob2tkit.runtime.engine;

/** A current full floor and blocked sight permit work, never a kill/calm credit. */
final class GuardCoveredHostilePolicy {
    /** Exclude teleportation, phasing, sonic attacks and other barrier bypasses. */
    static boolean supported(String type){
        return java.util.Set.of("minecraft:creeper","minecraft:zombie","minecraft:husk","minecraft:drowned",
            "minecraft:skeleton","minecraft:stray","minecraft:bogged","minecraft:spider","minecraft:cave_spider").contains(type==null?"":type);
    }
    record Evidence(boolean standalone,boolean healthyDry,boolean projectile,boolean current,
                    boolean ordinary,boolean visible,boolean swelling,boolean receivedHit,
                    boolean fullFloor,double mobTop,double floorBottom,double floorTop,double feet) {}
    static boolean fullBarrierBox(double x0,double y0,double z0,double x1,double y1,double z1){
        return Double.isFinite(x0)&&Double.isFinite(y0)&&Double.isFinite(z0)
            &&Double.isFinite(x1)&&Double.isFinite(y1)&&Double.isFinite(z1)
            &&x0<=1e-7&&z0<=1e-7&&x1>=1-1e-7&&z1>=1-1e-7&&y1-y0>=.5-1e-7;
    }
    static boolean safe(Evidence e){
        return e!=null&&e.standalone()&&e.healthyDry()&&!e.projectile()&&e.current()&&e.ordinary()
            &&!e.visible()&&!e.swelling()&&!e.receivedHit()&&e.fullFloor()
            &&Double.isFinite(e.mobTop())&&Double.isFinite(e.floorBottom())&&Double.isFinite(e.floorTop())&&Double.isFinite(e.feet())
            &&e.floorBottom()>=e.mobTop()+.2&&e.floorTop()-e.floorBottom()>=.5-1e-7
            &&e.floorTop()<=e.feet()+.05&&e.feet()-e.floorTop()<=32;
    }
}
