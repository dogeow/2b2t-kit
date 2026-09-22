package dev.twob2tkit.runtime.engine;

import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;

/** Cargo cruising is faster than excavation positioning, with braking and a matching swept-body probe. */
final class BorerCargoMotion {
    static BorerAreaMotion.Input of(Command c,Pose p,float yaw){
        if(c.action()!=Action.X&&c.action()!=Action.Z)return BorerAreaMotion.of(c,p,yaw);
        boolean x=c.action()==Action.X;double error=(x?c.x()-p.x():c.z()-p.z());
        double speed=speed(error,x?p.vx():p.vz());
        return new BorerAreaMotion.Input(x?(error>0?-90:90):(error>0?0:180),speed>0,false,false,speed);
    }
    static double speed(double error,double velocity){
        double distance=Math.abs(error),toward=Math.max(0,Math.signum(error)*velocity);
        double remaining=Math.max(0,distance-toward);
        // Two input frames at Meteor's faster sprint scale must still fit before the stopping point.
        return Math.min(distance<.8?.005:.08,remaining/30.0);
    }
    static double probe(double error,double velocity){
        return Math.min(Math.abs(error),Math.max(.25,Math.abs(velocity)+speed(error,velocity)*15));
    }
}
