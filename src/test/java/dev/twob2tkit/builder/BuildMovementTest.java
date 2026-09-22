package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BuildMovementTest {
    private final dev.twob2tkit.runtime.api.BuildNavigation nav=new dev.twob2tkit.runtime.engine.DefaultBuildNavigation();
    private boolean vertical(double dy){return nav.motion(new net.minecraft.world.phys.Vec3(0,dy,0)).vertical();}
    private boolean arrived(double x,double y,double z){return nav.motion(new net.minecraft.world.phys.Vec3(x,y,z)).arrived();}
    private double horizontalSpeed(double d){return nav.motion(new net.minecraft.world.phys.Vec3(d,0,0)).speed();}
    private double verticalSpeed(double d){return nav.motion(new net.minecraft.world.phys.Vec3(0,d,0)).speed();}
    @Test void floorLipRequiresRaisingBeforeHorizontalTravel(){
        double dy=71.02-70.9589734837838;
        assertTrue(vertical(dy));assertFalse(arrived(0,dy,0));
    }
    @Test void recordedNarrowDoorOffsetIsNotConsideredArrived(){
        assertFalse(arrived(.5-.4162594659,.02-.04948674189237,.5-.551096041));
        assertFalse(arrived(.02,0,0));
        assertTrue(arrived(.002,.002,.002));
    }
    @Test void proportionalApproachDoesNotOscillateAcrossTarget(){
        for(double initial:new double[]{.02948674189237,.08,.5,1}){
            double x=initial,y=initial;
            for(int i=0;i<100;i++){
                double dx=horizontalSpeed(x)*10,dy=verticalSpeed(y)*5;
                assertTrue(dx<=x&&dy<=y);x-=dx;y-=dy;
            }
            assertTrue(arrived(x,0,0));assertTrue(arrived(0,y,0));assertTrue(x<.006&&y<.006);
        }
        assertEquals(.012,horizontalSpeed(10));assertEquals(.024,verticalSpeed(-10));
    }
}
