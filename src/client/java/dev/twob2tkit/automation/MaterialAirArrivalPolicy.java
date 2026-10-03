package dev.twob2tkit.automation;

import net.minecraft.world.phys.Vec3;

/** Exact material waypoints require real stationary observations, not Cruise's broad arrival hint. */
final class MaterialAirArrivalPolicy {
    static final int STABLE_TICKS=8;
    static final int RESTORED_TICKS=8;
    record Motion(boolean vertical,boolean horizontal,boolean moving,double speed) {}
    enum Decision { WAIT, RESTORE, REACQUIRE, CONFIRMED }
    static final class Settlement {
        private final double arrival;
        private int stableTicks,restoredTicks,restorations;
        private boolean restored,done;
        Settlement(double arrival){this.arrival=arrival;}
        void precision(){restored=false;done=false;pause();}
        void pause(){stableTicks=restoredTicks=0;}
        Decision observe(Vec3 error,Vec3 displacement,Vec3 velocity){
            boolean inRange=inside(error,arrival),still=stationary(displacement,velocity);
            if(!restored){
                stableTicks=inRange&&still?stableTicks+1:0;
                if(stableTicks>=STABLE_TICKS){restored=true;restoredTicks=0;restorations++;return Decision.RESTORE;}
            }else{
                restoredTicks=inRange&&still?restoredTicks+1:0;
                if(!inRange){
                    if(restorations>=3)throw new IllegalStateException("Restored Flight settings did not keep the precise waypoint stable");
                    precision();return Decision.REACQUIRE;
                }
                if(restoredTicks>=RESTORED_TICKS){done=true;return Decision.CONFIRMED;}
            }
            return Decision.WAIT;
        }
        boolean restored(){return restored;}
        boolean done(){return done;}
        int stableTicks(){return stableTicks;}
        int restoredTicks(){return restoredTicks;}
        int restorations(){return restorations;}
    }
    private MaterialAirArrivalPolicy() {}
    static boolean takeOver(Vec3 error,Vec3 velocity,boolean cruising){
        return !cruising||Math.hypot(error.x,error.z)<=Math.max(3,Math.hypot(velocity.x,velocity.z)*8+.5);
    }
    static Motion motion(Vec3 error){
        double horizontal=Math.hypot(error.x,error.z);double absY=Math.abs(error.y);
        // Meteor shares one speed between both axes. Align first so a large
        // altitude error cannot turn a tiny horizontal correction into an overshoot.
        if(horizontal>.06)return new Motion(false,true,true,Math.min(.06,horizontal/20));
        if(absY>.06)return new Motion(true,false,true,Math.min(.08,absY/10));
        return new Motion(false,false,false,0);
    }
    static boolean inside(Vec3 error,double arrival){
        return Double.isFinite(error.lengthSqr())&&Math.hypot(error.x,error.z)<=arrival
            &&Math.abs(error.y)<=Math.min(.25,arrival);
    }
    static boolean stationary(Vec3 displacement,Vec3 velocity){
        // Minecraft may expose the next gravity term (-0.0784 Y/tick) while
        // Meteor is actually hovering. Real position change must still be tiny.
        return Double.isFinite(displacement.lengthSqr())&&Double.isFinite(velocity.lengthSqr())
            &&Math.hypot(displacement.x,displacement.z)<=.005&&Math.abs(displacement.y)<=.005
            &&Math.hypot(velocity.x,velocity.z)<=.01&&Math.abs(velocity.y)<=.1;
    }
}
