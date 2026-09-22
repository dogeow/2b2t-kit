package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoMotionTest {
    @Test void cruisingDoesNotStopEveryOtherTickToZeroHorizontalSpeed(){
        Pose p=new Pose(.5,68.25,.5,0,0,0);
        var trip=new BorerCargoTrip(p,new BlockPos(30,65,30),64);trip.step(b->Cell.AIR,p);
        p=new Pose(.8,68.25,.5,.3,-.0784,0);
        assertEquals(Action.X,trip.step(b->Cell.AIR,p).action());
    }
    @Test void fasterMovementChecksPastTheOldQuarterBlockProbe(){
        Pose p=new Pose(.75,68.25,.5,0,0,0);
        var trip=new BorerCargoTrip(p,new BlockPos(30,65,30),64);trip.step(b->Cell.AIR,p);
        Command result=trip.step(b->b.getX()==2?Cell.SOLID:Cell.AIR,p);
        assertEquals(Action.BLOCKED,result.action());assertEquals(2,result.block().getX());
    }
    @Test void incomingVelocityAndBothFlightScalesFitTheProbeAndBrakingDistance(){
        for(double distance:new double[]{.09,.3,.79,.81,3,8,40})for(double v:new double[]{0,.05,.4,.8}){
            double speed=BorerCargoMotion.speed(distance,v);
            assertTrue(speed<=.08);
            assertTrue(speed*15<=BorerCargoMotion.probe(distance,v)+1e-9);
            assertTrue(speed*30<=Math.max(0,distance-v)+1e-9);
        }
    }
    @Test void realDepotDistanceRoundTripsFasterWithoutOvershootingWithDelayedInputs(){
        int baseline=run(false,10,false);
        int accelerated=run(true,10,false);
        assertTrue(accelerated<baseline*.65,"old="+baseline+" new="+accelerated);
        run(true,15,false);run(true,10,true);run(true,15,true);
        System.out.println("Recorded depot route simulation: old="+baseline+" ticks; new="+accelerated+" ticks");
    }
    private int run(boolean fast,int scale,boolean delay){
        Pose p=new Pose(760982.56,64.23,797898.56,0,0,0);
        Pose start=p, service=new Pose(761019.5,64.05,797851.5,0,0,0);
        var trip=new BorerCargoTrip(start,new BlockPos(761019,64,797852),new BorerCargoRouting.Route(service,90.05,false,false));
        float yaw=0;BorerAreaMotion.Input pending=new BorerAreaMotion.Input(0,false,false,false,0);
        boolean serviced=false;int tick=0;
        for(;tick<5000&&trip.stage()!=BorerCargoTrip.Stage.DONE;tick++){
            Command command=trip.step(b->Cell.AIR,p);assertNotEquals(Action.BLOCKED,command.action());
            if(trip.stage()==BorerCargoTrip.Stage.SERVICE){
                assertEquals(service.x(),p.x(),.10);assertEquals(service.z(),p.z(),.10);assertEquals(service.y(),p.y(),.11);
                serviced=true;trip.returnToWork();
            }
            var requested=fast?BorerCargoMotion.of(command,p,yaw):legacy(command,p,yaw);
            var applied=delay?pending:requested;pending=requested;yaw=requested.yaw();
            double dx=applied.forward()?-Math.sin(Math.toRadians(applied.yaw()))*applied.speed()*scale:0;
            double dz=applied.forward()?Math.cos(Math.toRadians(applied.yaw()))*applied.speed()*scale:0;
            double dy=(applied.up()?1:applied.down()?-1:0)*applied.speed()*5;
            if(Math.abs(dx)+Math.abs(dz)>.00001)assertEquals(90.05,p.y(),.11,"horizontal motion must stay above the excavation");
            p=new Pose(p.x()+dx,p.y()+dy,p.z()+dz,dx,dy,dz);
            assertTrue(p.x()>=Math.floor(start.x())+.35&&p.x()<=service.x()+.15);
            assertTrue(p.z()>=service.z()-.15&&p.z()<=start.z()+.15);
        }
        assertTrue(serviced);assertEquals(BorerCargoTrip.Stage.DONE,trip.stage());
        assertEquals(Math.floor(start.x())+.5,p.x(),.10);assertEquals(Math.floor(start.z())+.5,p.z(),.10);
        return tick;
    }
    private BorerAreaMotion.Input legacy(Command c,Pose p,float yaw){
        if(c.action()!=Action.X&&c.action()!=Action.Z)return BorerAreaMotion.of(c,p,yaw);
        boolean x=c.action()==Action.X;double error=(x?c.x()-p.x():c.z()-p.z());
        return new BorerAreaMotion.Input(x?(error>0?-90:90):(error>0?0:180),true,false,false,Math.abs(error)<.8?.005:.016);
    }
}
