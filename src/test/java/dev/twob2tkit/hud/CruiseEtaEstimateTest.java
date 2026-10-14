package dev.twob2tkit.hud;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CruiseEtaEstimateTest {
    @Test void predictsFromObservedDistanceClosure(){
        var e=new CruiseEtaEstimate();assertEquals(-1,e.observe("a",100,0));
        assertEquals(9,e.observe("a",90,1000),.001);
        assertEquals(8,e.observe("a",80,2000),.001);
    }
    @Test void stoppedMovementCannotKeepCountingDown(){
        var e=new CruiseEtaEstimate();e.observe("a",100,0);e.observe("a",90,1000);
        assertEquals(-1,e.observe("a",90,2501));
    }
    @Test void targetChangesAndBackwardTravelResetTheEstimate(){
        var e=new CruiseEtaEstimate();e.observe("a",100,0);e.observe("a",90,1000);
        assertEquals(-1,e.observe("b",20,1100));
        e.observe("b",10,2100);assertEquals(-1,e.observe("b",15,2200));
    }
    @Test void invalidClockAndUnknownOrInvalidDistanceDoNotMakeAnEta(){
        var e=new CruiseEtaEstimate();e.observe("a",100,1000);e.observe("a",90,2000);
        assertEquals(-1,e.observe("a",80,1500));
        for(double d:new double[]{Double.NaN,Double.POSITIVE_INFINITY,-1})assertEquals(-1,e.observe("a",d,3000));
        assertEquals(-1,e.observe("",1,3000));
    }
    @Test void longObservationGapRequiresFreshMotionSamples(){
        var e=new CruiseEtaEstimate();e.observe("a",100,0);e.observe("a",90,1000);
        assertEquals(-1,e.observe("a",50,4000));
        assertEquals(4,e.observe("a",40,5000),.001);
    }
}
