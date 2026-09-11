package dev.twob2tkit.builder;
import dev.twob2tkit.automation.PlacementTravelBarrier;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BuildDepartureTest {
    @Test void completedStationCanLeaveAfterSixTicksInsteadOfOneHundred(){
        var p=new BuildDeparturePolicy();
        for(int tick=40;tick<46;tick++)assertFalse(p.observe(tick,true,false));
        assertTrue(p.observe(46,true,false));
        assertTrue(BuildDeparturePolicy.QUIET_TICKS<BuildDeparturePolicy.RETRY_TICKS);
    }
    @Test void nearbyWorkKeepsPrintingEvenWhenTheQueueMomentarilyDrains(){
        var p=new BuildDeparturePolicy();
        for(int tick=0;tick<120;tick++)assertFalse(p.observe(tick,true,true));
        assertFalse(p.observe(120,true,false));assertTrue(p.observe(126,true,false));
    }
    @Test void delayedServerConfirmationCannotBeMistakenForAnEmptyQueue(){
        var p=new BuildDeparturePolicy();var b=new PlacementTravelBarrier<String,String>();
        b.queued("wall","concrete");b.sent("wall");
        for(int t=0;t<200;t++)assertFalse(p.observe(t,b.settled(),false));
        b.serverBlock("wall","concrete");
        for(int t=200;t<206;t++)assertFalse(p.observe(t,b.settled(),false));
        assertTrue(p.observe(206,b.settled(),false));
    }
    @Test void newlyReachableTargetRestartsTheCompletionWindow(){
        var p=new BuildDeparturePolicy();p.observe(10,true,false);p.observe(14,true,false);
        assertFalse(p.observe(15,true,true));assertFalse(p.observe(16,true,false));
        assertFalse(p.observe(21,true,false));assertTrue(p.observe(22,true,false));
    }
    @Test void pauseOrNewServerGainMustRequireFreshQuietObservations(){
        var p=new BuildDeparturePolicy();p.observe(10,true,false);p.reset();
        assertFalse(p.observe(30,true,false));assertFalse(p.observe(35,true,false));assertTrue(p.observe(36,true,false));
    }
    @Test void queuedActionAtTheDeadlinePreventsTravel(){
        var p=new BuildDeparturePolicy();p.observe(0,true,false);
        assertFalse(p.observe(6,false,false));assertFalse(p.observe(7,true,false));assertTrue(p.observe(13,true,false));
    }
}
