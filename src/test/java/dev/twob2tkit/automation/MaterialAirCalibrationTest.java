package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MaterialAirCalibrationTest {
    @Test void expiryBetweenMiningAndPickupKeepsOneDiveBudgetThenRefreshesOnAir() {
        var calibration=new MaterialAirCalibration();
        var sample=new MaterialAirBudget.Sample(13,15,1200);
        calibration.add(sample,0);calibration.add(sample,1000);calibration.add(sample,2000);
        calibration.enterDive("world","job","gear",119000,300,13);
        assertTrue(calibration.isPinned("world","job","gear"));
        var duringMine=calibration.samples("world","job","gear",true,119000);
        var duringPickup=calibration.samples("world","job","gear",true,123000);
        assertEquals(3,duringMine.size());
        assertEquals(3,duringPickup.size(),"The first expired sample must not revoke pickup mid-dive");
        assertEquals("observed",MaterialAirBudget.estimate(300,13,duringPickup).source());
        assertTrue(calibration.returnDue("world","job","gear",234000));
        calibration.samples("world","job","gear",false,234500);
        assertFalse(calibration.isPinned("world","job","gear"));
        assertEquals(0,calibration.samples("world","job","gear",false,234500).size());
    }

    @Test void changingWorldJobOrGearNeverKeepsPinnedBudget() {
        var calibration=new MaterialAirCalibration();
        var sample=new MaterialAirBudget.Sample(13,15,1200);
        for(int i=0;i<3;i++)calibration.add(sample,1000+i);
        calibration.enterDive("world","job","gear",2000,300,13);
        assertEquals(0,calibration.samples("another","job","gear",true,2000).size());
        calibration.enterDive("world","job","gear",2001,300,13);
        assertEquals(0,calibration.samples("world","another","gear",true,2001).size());
        calibration.enterDive("world","job","gear",2002,300,13);
        assertEquals(0,calibration.samples("world","job","other",true,2002).size());
    }
}
