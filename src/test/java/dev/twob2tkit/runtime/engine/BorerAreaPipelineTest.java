package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaPipelineTest {
	private final BlockPos a = new BlockPos(1,1,0), b = new BlockPos(1,0,0);
	@Test void secondIndependentClickCanBeSentWhileFirstAwaitsConfirmation() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		assertFalse(q.canClick(1));assertTrue(q.canClick(2));q.submitted(b,2);
		assertEquals(2,q.size());assertFalse(q.canClick(20));
		assertThrows(IllegalStateException.class,()->q.submitted(b,20));
	}
	@Test void firstConfirmationMustNotPreventSubmittingTheSecondClickInThatSameTick() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		q.update(1,p->new BorerAreaPipeline.Observation(true,false));q.update(2,p->new BorerAreaPipeline.Observation(true,false));
		assertFalse(q.active());assertTrue(q.canClick(2));q.submitted(b,2);assertTrue(q.contains(b));
	}
	@Test void secondSolidBlockRemainsTrackedForFollowupWhenFirstDelayedBlockCompletes() {
		var q=new BorerAreaPipeline();q.submitted(a,0);q.submitted(b,2);
		q.update(6,p->new BorerAreaPipeline.Observation(p.equals(a),false));
		var confirmed=q.update(7,p->new BorerAreaPipeline.Observation(p.equals(a),false));
		assertEquals(List.of(a),confirmed);assertEquals(List.of(b),q.positions());
		assertFalse(q.blocksRay(new Vec3(.5,.5,.5),new Vec3(1,.5,.5),b));
		q.update(8,p->new BorerAreaPipeline.Observation(true,false));q.update(9,p->new BorerAreaPipeline.Observation(true,false));
		assertFalse(q.active());
	}
	@Test void predictedAirIsNeverProofOfCompletionEvenAfterManyTicks() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		for(int t=1;t<=100;t++)assertTrue(q.update(t,p->new BorerAreaPipeline.Observation(true,true)).isEmpty());
		assertEquals(a,q.expired(100));assertTrue(q.active());
	}
	@Test void unacknowledgedSolidOrRejectedBreakCannotAdvanceThePlanner() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		for(int t=1;t<=100;t++)q.update(t,p->new BorerAreaPipeline.Observation(false,false));
		assertTrue(q.active());assertEquals(a,q.expired(100));
	}
	@Test void outOfOrderConfirmationsDoNotEraseTheOtherPendingBlock() {
		var q=new BorerAreaPipeline();q.submitted(a,0);q.submitted(b,2);
		for(int t=3;t<=4;t++)q.update(t,p->new BorerAreaPipeline.Observation(true,p.equals(a)));
		assertTrue(q.contains(a));assertFalse(q.contains(b));
		q.update(5,p->new BorerAreaPipeline.Observation(true,false));
		assertEquals(List.of(a),q.update(6,p->new BorerAreaPipeline.Observation(true,false)));assertFalse(q.active());
	}
	@Test void twoCallsInTheSameTickCannotCountAsTwoAirObservations() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		q.update(1,p->new BorerAreaPipeline.Observation(true,false));q.update(1,p->new BorerAreaPipeline.Observation(true,false));
		assertTrue(q.active());q.update(2,p->new BorerAreaPipeline.Observation(true,false));assertFalse(q.active());
	}
	@Test void serverRefillResetsTheAirConfirmation() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		q.update(1,p->new BorerAreaPipeline.Observation(true,false));
		q.update(2,p->new BorerAreaPipeline.Observation(false,false));
		q.update(3,p->new BorerAreaPipeline.Observation(true,false));assertTrue(q.active());
		q.update(4,p->new BorerAreaPipeline.Observation(true,false));assertFalse(q.active());
	}
	@Test void laterSuccessfulClicksCannotExtendAnEarlierFailureTimeout() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		for(int t=2;t<=100;t++){
			q.update(t,p->new BorerAreaPipeline.Observation(!p.equals(a),p.equals(a)));
			if(q.canClick(t))q.submitted(new BlockPos(t,0,0),t);
		}
		assertEquals(a,q.expired(100));
	}
	@Test void rayCannotPassThroughAnUnconfirmedBlockButCanReachAnIndependentFace() {
		var q=new BorerAreaPipeline();q.submitted(a,0);
		Vec3 eye=new Vec3(.5,1.5,.5);
		assertTrue(q.blocksRay(eye,new Vec3(3,1.5,.5)));
		assertFalse(q.blocksRay(eye,new Vec3(.5,0,.5)));
		q.update(1,p->new BorerAreaPipeline.Observation(true,false));q.update(2,p->new BorerAreaPipeline.Observation(true,false));
		assertFalse(q.blocksRay(eye,new Vec3(3,1.5,.5)));
	}
	@Test void manualStopClearsOnlyTheLocalQueueForANewSession() {
		var q=new BorerAreaPipeline();q.submitted(a,0);q.clear();assertFalse(q.active());assertTrue(q.canClick(0));
	}
	@Test void twoSlotPipelineCompletesTheSameDelayedWorkFasterThanSerialWaiting() {
		int serial=simulate(1),pipeline=simulate(2);
		assertTrue(pipeline < serial*.7,"serial="+serial+", pipeline="+pipeline);
		System.out.println("24 independent clicks with 6-tick server delay: serial="+serial+", two-slot="+pipeline);
	}
	private int simulate(int limit) {
		var q=new BorerAreaPipeline();Map<BlockPos,Integer> submitted=new HashMap<>();Set<BlockPos> completed=new HashSet<>();
		int next=0;
		for(int tick=0;tick<1000;tick++){
			int now=tick;
			completed.addAll(q.update(tick,p->new BorerAreaPipeline.Observation(true,now-submitted.get(p)<6)));
			if(completed.size()==24){assertFalse(q.active());return tick;}
			if(next<24&&q.size()<limit&&q.canClick(tick)){
				var pos=new BlockPos(next++,0,0);q.submitted(pos,tick);submitted.put(pos,tick);
			}
			assertTrue(q.size()<=limit);assertNull(q.expired(tick));
		}
		throw new AssertionError("simulation timed out");
	}
}
