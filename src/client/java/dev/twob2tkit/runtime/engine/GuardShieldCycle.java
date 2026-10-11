package dev.twob2tkit.runtime.engine;

import java.util.UUID;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** Shield-first counterattacks; a timer opens a window, never confirms an arrow block. */
final class GuardShieldCycle {
    static final int MIN_BLOCK_TICKS=8, WAIT_TICKS=40, ATTACK_TICKS=32;
    enum Action { DISABLED, BLOCK, ATTACK }
    private UUID target;
    private long phaseAt=Long.MIN_VALUE,blockingAt=Long.MIN_VALUE,lastTick=Long.MIN_VALUE;
    private int previousDamage;
    private boolean attacking,observedBlock;

    Action update(UUID id,long tick,boolean enabled,boolean blocking,int damage,boolean incoming,boolean hurt){
        if(!enabled||id==null||damage<0){reset();return Action.DISABLED;}
        if(!id.equals(target)||tick<lastTick){reset();target=id;phaseAt=tick;previousDamage=damage;}
        lastTick=tick;
        if(attacking){
            previousDamage=damage;
            if(incoming||hurt||tick-phaseAt>=ATTACK_TICKS){block(tick);return Action.BLOCK;}
            return Action.ATTACK;
        }
        if(blocking){
            if(blockingAt==Long.MIN_VALUE)blockingAt=tick;
            if(damage>previousDamage&&!hurt)observedBlock=true;
        }else blockingAt=Long.MIN_VALUE;
        previousDamage=damage;
        // Actual shield wear already proves a settled block. Waiting another
        // eight ticks consumes most of a skeleton's next-shot interval.
        if(blockingAt!=Long.MIN_VALUE&&!incoming&&!hurt
                &&(observedBlock||tick-blockingAt>=MIN_BLOCK_TICKS&&tick-phaseAt>=WAIT_TICKS)){
            attacking=true;phaseAt=tick;observedBlock=false;return Action.ATTACK;
        }
        return Action.BLOCK;
    }
    void shot(long tick){if(target!=null)block(tick);}
    boolean enabled(){return target!=null;}
    boolean counterattacking(){return target!=null&&attacking;}
    private void block(long tick){attacking=false;observedBlock=false;phaseAt=tick;blockingAt=Long.MIN_VALUE;}
    void reset(){target=null;phaseAt=blockingAt=lastTick=Long.MIN_VALUE;previousDamage=0;attacking=observedBlock=false;}

    static boolean incoming(Vec3 position,Vec3 velocity,AABB body,Vec3 playerVelocity){
        if(!GuardWeaponPolicy.finiteVector(position)||!GuardWeaponPolicy.finiteVector(velocity)
                ||!GuardWeaponPolicy.finiteVector(playerVelocity)||!GuardWeaponPolicy.finiteBox(body))return true;
        Vec3 relative=velocity.subtract(playerVelocity);
        double speed=relative.lengthSqr();
        if(speed<.0001)return false;
        double time=-position.subtract(body.getCenter()).dot(relative)/speed;
        return time>=0&&time<=12&&body.inflate(.6).distanceToSqr(position.add(relative.scale(time)))<.01;
    }
}
