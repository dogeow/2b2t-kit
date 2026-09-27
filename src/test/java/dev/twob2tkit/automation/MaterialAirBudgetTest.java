package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class MaterialAirBudgetTest {
    @Test void noThreeGoodAscentsMeansOldMaterialFloors() {
        var sample=new MaterialAirBudget.Sample(13,15,1200);
        assertEquals("fallback",MaterialAirBudget.estimate(300,13,List.of(sample,sample)).source());
        assertEquals(240,MaterialAirBudget.estimate(300,13,List.of(sample,sample)).returnFloor());
        assertEquals(260,MaterialAirBudget.estimate(300,13,List.of(sample,sample)).workFloor());
    }

    @Test void recentObservedReturnHasBubbleAndDelayReserve() {
        var samples=List.of(new MaterialAirBudget.Sample(13,15,1200),
            new MaterialAirBudget.Sample(13,18,1450),
            new MaterialAirBudget.Sample(14,19,1500));
        var shallow=MaterialAirBudget.estimate(300,5,samples);
        var deep=MaterialAirBudget.estimate(300,14,samples);
        assertEquals("observed",deep.source());
        assertTrue(deep.returnFloor()>=30+deep.estimatedLoss()+15);
        assertTrue(deep.workFloor()>=deep.returnFloor()+20);
        assertTrue(deep.pickupFloor()>=deep.returnFloor()+15);
        assertTrue(deep.workFloor()>deep.pickupFloor());
        assertTrue(shallow.returnFloor()<deep.returnFloor());
        assertTrue(deep.workFloor()<=300);
    }

    @Test void delayedOrInvalidSamplesRestoreConservativeLimit() {
        var good=new MaterialAirBudget.Sample(13,15,1200);
        var delayed=new MaterialAirBudget.Sample(13,80,18200);
        var estimate=MaterialAirBudget.estimate(300,13,List.of(good,good,delayed));
        assertEquals("fallback_bad_sample",estimate.source());
        assertEquals(240,estimate.returnFloor());
        assertEquals(260,estimate.workFloor());
    }

    @Test void excessiveObservedCostIsNeverClampedToAnUnsafeOldThreshold() {
        var slow=new MaterialAirBudget.Sample(2,150,7000);
        var estimate=MaterialAirBudget.estimate(300,13,List.of(slow,slow,slow));
        assertEquals("observed",estimate.source());
        assertTrue(estimate.returnFloor()>300);
        assertTrue(estimate.workFloor()>estimate.returnFloor());
    }

    @Test void deeperSeafloorStillUsesObservedAscentTime() {
        var samples=List.of(new MaterialAirBudget.Sample(13,15,1200),
            new MaterialAirBudget.Sample(14,17,1300),
            new MaterialAirBudget.Sample(13,16,1250));
        var deep=MaterialAirBudget.estimate(300,33,samples);
        assertEquals("observed",deep.source());
        assertTrue(deep.returnFloor()>=30+deep.estimatedLoss()+15);
    }
}
