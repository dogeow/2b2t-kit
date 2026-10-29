package dev.twob2tkit.combat;

/** A bounded recovery pause after escaping a mob's ignition, not a lower-health exemption. */
final class ResidualFireWaitPolicy {
    // Vanilla 26.2 AbstractSkeleton constructs its bow goal with radius 15.
    // Keep a one-block margin; other ranged mobs retain a wider exclusion.
    static double rangedRadius(String type){
        return switch(type==null?"":type){
            case "minecraft:skeleton","minecraft:stray","minecraft:bogged","minecraft:parched"->16;
            case "minecraft:ghast","minecraft:blaze","minecraft:wither","minecraft:warden","minecraft:ender_dragon"->64;
            default->40;
        };
    }
    record Sample(boolean owned,boolean bodySafe,boolean threatsClear,boolean burning,
                  boolean lingeringDamage,boolean knownMobIgnition,boolean canStart,
                  double health,double maximum,int food){}
    static final class Window {
        private long started=-1;
        private boolean spent;
        boolean active(){return started>=0;}
        long started(){return started;}
        void reset(){started=-1;spent=false;}
        boolean observe(long now,Sample s){
            boolean safe=now>=0&&s!=null&&s.owned()&&s.bodySafe()&&s.threatsClear()
                &&Double.isFinite(s.health())&&Double.isFinite(s.maximum())&&s.maximum()>0
                &&s.health()>=Math.max(18,s.maximum()*.8)&&s.health()<=s.maximum()&&s.food()>=18;
            if(s!=null&&!s.burning())spent=false;
            if(!safe||active()&&(now<started||now-started>20000)
                    ||s.burning()&&!s.lingeringDamage()) {
                if(active()&&s!=null&&s.burning())spent=true;
                started=-1;return false;
            }
            if(active()){
                if(!s.burning()&&s.health()>=s.maximum()){reset();return false;}
                return true;
            }
            if(!spent&&s.burning()&&s.lingeringDamage()&&s.knownMobIgnition()&&s.canStart()){
                started=now;return true;
            }
            return false;
        }
    }
    private ResidualFireWaitPolicy(){}
}
