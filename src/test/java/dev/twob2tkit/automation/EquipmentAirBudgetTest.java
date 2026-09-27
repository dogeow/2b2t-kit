package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EquipmentAirBudgetTest {
    @Test void respirationThreeHasSixtySecondMeanButKeepsReturnReserve(){
        assertEquals(60,EquipmentAirBudget.expectedSeconds(300,3));
        var estimate=EquipmentAirBudget.estimate(300,15,3);
        assertEquals("equipment",estimate.source());
        assertTrue(estimate.returnFloor()>30+15*5);
        assertTrue(estimate.workFloor()>estimate.pickupFloor());
        assertTrue(estimate.workFloor()<300);
    }

    @Test void deeperWaterOrWeakerGearCannotIncreaseTheDiveAllowance(){
        var shallow=EquipmentAirBudget.estimate(300,10,3);
        var deep=EquipmentAirBudget.estimate(300,24,3);
        var noBonus=EquipmentAirBudget.estimate(300,10,0);
        assertTrue(deep.workFloor()>shallow.workFloor());
        assertTrue(noBonus.workFloor()>shallow.workFloor());
        assertTrue(EquipmentAirBudget.estimate(300,39,3).workFloor()>300);
    }
}
