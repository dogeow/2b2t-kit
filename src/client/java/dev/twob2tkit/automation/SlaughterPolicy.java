package dev.twob2tkit.automation;

import java.util.Set;

/** A single ordinary attack on a freshly observed surplus adult, never a kill receipt. */
final class SlaughterPolicy {
    static final int PROTOCOL = 1;
    static final int DEFAULT_KEEP = 20;
    private static final Set<String> FOOD_ANIMALS = Set.of(
        "minecraft:cow", "minecraft:sheep", "minecraft:pig", "minecraft:chicken");
    private SlaughterPolicy() {}

    record Bounds(int minX,int minY,int minZ,int maxX,int maxY,int maxZ) {
        boolean valid() {
            long x=(long)maxX-minX+1,y=(long)maxY-minY+1,z=(long)maxZ-minZ+1;
            return x>0&&x<=32&&y>0&&y<=32&&z>0&&z<=32&&x*y*z<=8192;
        }
        boolean contains(double x,double y,double z) {
            return valid()&&Double.isFinite(x)&&Double.isFinite(y)&&Double.isFinite(z)
                &&x>=minX&&x<((double)maxX+1)&&y>=minY&&y<((double)maxY+1)
                &&z>=minZ&&z<((double)maxZ+1);
        }
    }
    static boolean owned(boolean materialLease,String task,String leaseTask,String world,String leaseWorld,
                         String currentWorld,long revision,long leaseRevision,long currentRevision,
                         long expiresIn,long heartbeatAge) {
        return materialLease&&task!=null&&!task.isBlank()&&task.equals(leaseTask)
            &&world!=null&&!world.isBlank()&&world.equals(leaseWorld)&&world.equals(currentWorld)
            &&revision==currentRevision&&leaseRevision==currentRevision
            &&expiresIn>=0&&expiresIn<=15000&&heartbeatAge>=0&&heartbeatAge<=15000;
    }
    static boolean safe(boolean pveGuard,boolean busy,boolean manual,boolean held,boolean survival,
                        float health,int food,boolean onGround,boolean usingItem,boolean hurt,
                        boolean wetOrBurning,boolean otherWork,boolean ordinaryWeapon,boolean sweepClear) {
        return pveGuard&&!busy&&!manual&&!held&&survival&&Float.isFinite(health)&&health>=19&&food>=8
            &&!onGround&&!usingItem&&!hurt&&!wetOrBurning&&!otherWork&&ordinaryWeapon&&sweepClear;
    }
    static boolean adult(String type,boolean alive,boolean removed,boolean baby,boolean named,float health) {
        return FOOD_ANIMALS.contains(type)&&alive&&!removed&&!baby&&!named&&Float.isFinite(health)&&health>0;
    }
    static boolean surplus(int adults,int keep) { return keep>=2&&adults>keep; }
    static boolean aim(boolean exactIdentity,boolean visible,double distance,double reach,float cooldown) {
        return exactIdentity&&visible&&Double.isFinite(distance)&&distance>=0&&Double.isFinite(reach)
            &&reach>.2&&distance<=reach-.2&&Float.isFinite(cooldown)&&cooldown>=.95F;
    }
}
