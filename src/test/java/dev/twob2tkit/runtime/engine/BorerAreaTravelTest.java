package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaTravelTest {
	@Test void longerMovesAndOneBlockApproachesBothGetFasterWithoutOvershooting() {
		for(int scale:new int[]{10,15})for(boolean delayed:new boolean[]{false,true}) {
			int old=route(false,scale,delayed),now=route(true,scale,delayed);
			assertTrue(now<old*.8,"scale="+scale+" delay="+delayed+" old="+old+" new="+now);
			System.out.println("Area route scale="+scale+" delay="+delayed+": old="+old+" new="+now);
		}
	}
	private int route(boolean fast,int scale,boolean delayed) {
		Pose p=new Pose(.5,63.08,.5,0,0,0);int total=0;
		for(double goal:new double[]{1.5,2.5,18.5,17.5,.5}) {
			double min=Math.min(goal,p.x())-.09,max=Math.max(goal,p.x())+.09;
			var prior=new BorerAreaMotion.Input(0,false,false,false,0);int tick=0;
			while((Math.abs(goal-p.x())>CENTER || Math.abs(p.vx())>=.025)&&tick++<2000) {
				var command=new Command(Math.abs(goal-p.x())>CENTER?Action.X:Action.WAIT,null,goal,p.y(),p.z(),"travel");
				var next=BorerAreaMotion.of(command,p,0);
				if(!fast&&command.action()==Action.X)next=new BorerAreaMotion.Input(goal>p.x()?-90:90,true,false,false,Math.abs(goal-p.x())<.8?.005:.016);
				var applied=delayed?prior:next;prior=next;
				double dx=applied.forward()?-Math.sin(Math.toRadians(applied.yaw()))*applied.speed()*scale:0;
				p=new Pose(p.x()+dx,p.y(),p.z(),dx,0,0);
				assertTrue(p.x()>=min&&p.x()<=max,"overshoot="+p.x()+" goal="+goal);
			}
			assertTrue(tick<2000);assertEquals(goal,p.x(),CENTER);total+=tick;
		}
		return total;
	}
	@Test void brakingProbeIncludesTheNewSpeedAndIncomingMomentum() {
		for(double error:new double[]{.09,.4,1,5,30})for(double velocity:new double[]{-.4,0,.1,.8}) {
			double speed=BorerAreaMotion.horizontalSpeed(error,velocity);
			assertTrue(speed*15<=BorerAreaMotion.horizontalProbe(error,velocity)+1e-9);
			assertTrue(speed*30<=Math.max(0,error-Math.max(0,velocity))+1e-9);
		}
	}
}
