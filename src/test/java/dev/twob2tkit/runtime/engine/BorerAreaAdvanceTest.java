package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;

class BorerAreaAdvanceTest {
	private Pose pose(double x) { return new Pose(x,.08,.5,0,-.0784,0); }
	private BorerAreaAdvance.World room(int wall, boolean floor) {
		return new BorerAreaAdvance.World() {
			public boolean air(BlockPos p) { return p.getX()<wall && p.getY()>=0 && p.getY()<=1; }
			public boolean floor(BlockPos p) { return floor; }
		};
	}
	@Test void canWalkThroughConfirmedCorridorWhileTheNextBlockIsStillBeingMined() {
		Pose p=pose(.5);int moving=0;
		for(int tick=0;tick<15;tick++) {
			var input=BorerAreaAdvance.input(p,new BlockPos(3,0,0),-90);
			boolean allowed=BorerAreaAdvance.safe(room(3,true),p,0,input);
			double dx=allowed?input.dx()*.215:0,dz=allowed?input.dz()*.215:0;
			if(allowed)moving++;
			p=new Pose(p.x()+dx,p.y(),p.z()+dz,dx,0,dz);
			assertTrue(p.x()+.299<3,"Never enter the not-yet-broken front block");
		}
		assertTrue(moving>=3);assertTrue(p.x()>1,"Actual walking happened before the wall was mined");
	}
	@Test void unknownOrPredictedAirStopsTheWholeBodyBeforeItsBoundary() {
		var input=BorerAreaAdvance.input(pose(.5),new BlockPos(2,0,0),-90);
		assertFalse(BorerAreaAdvance.safe(room(1,true),pose(.5),0,input));
		assertFalse(BorerAreaAdvance.safe(room(9,false),pose(.5),0,input));
	}
	@Test void aHoleBesideTheFeetBlocksDiagonalWalkingEvenWithClearHeadroom() {
		var world=new BorerAreaAdvance.World(){
			public boolean air(BlockPos p){return true;}
			public boolean floor(BlockPos p){return p.getZ()==0;}
		};
		var input=BorerAreaAdvance.input(pose(.5),new BlockPos(2,0,2),-45);
		assertFalse(BorerAreaAdvance.safe(world,pose(.5),0,input));
	}
	@Test void movementFollowsTheGoalWithoutChangingTheMiningCamera() {
		for(int yaw=0;yaw<360;yaw+=15) {
			var input=BorerAreaAdvance.input(pose(.5),new BlockPos(3,0,0),yaw);
			assertTrue(input.moving());assertTrue(input.dx()>.9,"yaw="+yaw);
			assertEquals(1,Math.hypot(input.dx(),input.dz()),1e-9);
		}
		assertTrue(BorerAreaAdvance.input(pose(.5),new BlockPos(3,0,0),90).back());
	}
	@Test void nearGoalOrFallingDoesNotProduceMoreMovement() {
		assertFalse(BorerAreaAdvance.input(pose(3.4),new BlockPos(3,0,0),-90).moving());
		var p=new Pose(.5,2,.5,0,-.4,0);
		assertFalse(BorerAreaAdvance.safe(room(10,true),p,0,BorerAreaAdvance.input(p,new BlockPos(2,0,0),-90)));
	}
	@Test void oppositeInputCannotHideMomentumTowardABlocker() {
		var p=new Pose(1.8,.08,.5,-.8,0,0);
		var world=new BorerAreaAdvance.World(){
			public boolean air(BlockPos b){return b.getX()>=1;}
			public boolean floor(BlockPos b){return true;}
		};
		assertFalse(BorerAreaAdvance.safe(world,p,0,BorerAreaAdvance.input(p,new BlockPos(4,0,0),-90)));
	}
}
