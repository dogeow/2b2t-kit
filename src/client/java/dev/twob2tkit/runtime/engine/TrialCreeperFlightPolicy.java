package dev.twob2tkit.runtime.engine;

import java.util.UUID;

/** Strike, rise beyond the real fuse reset distance, and only then descend for the next strike. */
final class TrialCreeperFlightPolicy {
    enum Decision { HIGH_APPROACH, DESCEND, ATTACK, WAIT, UNAVAILABLE }
    record Step(Decision decision,String reason) {}
    private UUID target;
    private long started,progressAt,lastTick,pausedAt=Long.MIN_VALUE;
    private double lowestHealth,originX,originZ;
    private boolean retreating=true,exhausted;
    private String reason="";
    Step step(UUID id,long tick,double x,double z,double health,double distance,double playerY,double mobY,
              boolean aligned,boolean swelling,boolean inRange,boolean cooledDown,boolean columnClear) {
        if(id==null||tick<0||!Double.isFinite(x)||!Double.isFinite(z)||!Double.isFinite(health)||health<=0
            ||!Double.isFinite(distance)||distance<0||!Double.isFinite(playerY)||!Double.isFinite(mobY))
            return new Step(Decision.UNAVAILABLE,"invalid_observation");
        if(!id.equals(target)){
            target=id;started=progressAt=lastTick=tick;originX=x;originZ=z;lowestHealth=health;
            retreating=true;exhausted=false;reason="";pausedAt=Long.MIN_VALUE;
        }
        if(pausedAt!=Long.MIN_VALUE){long delta=Math.max(0,tick-pausedAt);started+=delta;progressAt+=delta;pausedAt=Long.MIN_VALUE;}
        if(tick<lastTick)return fail("clock_changed");lastTick=tick;
        if(exhausted)return new Step(Decision.UNAVAILABLE,reason);
        if(health<lowestHealth){lowestHealth=health;progressAt=tick;}
        if(tick-started>800)return fail("time_limit");
        if(tick-progressAt>=240)return fail("no_confirmed_damage");
        if(Math.hypot(x-originX,z-originZ)>12||distance>16)return fail("travel_limit");
        if(swelling)retreating=true;
        if(retreating){
            if(!swelling&&aligned&&playerY>=mobY+7.6&&distance>TrialCreeperMeleePolicy.RESET_DISTANCE)
                retreating=false;
            else return new Step(Decision.HIGH_APPROACH,"rise_and_reset_fuse");
        }
        if(!aligned){retreating=true;return new Step(Decision.HIGH_APPROACH,"target_moved");}
        if(!columnClear)return fail("strike_or_return_column_blocked");
        if(inRange)return new Step(cooledDown?Decision.ATTACK:Decision.WAIT,cooledDown?"within_reach":"attack_cooldown");
        return new Step(Decision.DESCEND,"verified_strike_column");
    }
    void attacked(){retreating=true;}
    boolean activeTarget(UUID id){return id!=null&&id.equals(target)&&!exhausted;}
    Step fail(String value){exhausted=true;reason=value;return new Step(Decision.UNAVAILABLE,value);}
    void pause(long tick){if(target!=null&&pausedAt==Long.MIN_VALUE)pausedAt=tick;}
    void reset(){target=null;exhausted=false;retreating=true;pausedAt=Long.MIN_VALUE;}
}
