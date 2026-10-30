package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class MinorThermalWorkPolicyTest {
    @Test void recordedRegeneratingContactCanContinueWithoutMovingOffSource(){
        assertTrue(MinorThermalWorkPolicy.allow(true,19.84448,20,true,false,false));
        assertTrue(MinorThermalWorkPolicy.allow(true,18,16,true,false,false));
        assertTrue(MinorThermalWorkPolicy.allow(true,20,20,false,false,false));
    }
    @Test void lowHealthNoFoodAndUnknownOrOtherHazardsRetainProtection(){
        assertFalse(MinorThermalWorkPolicy.allow(true,17.99,20,true,false,false));
        assertFalse(MinorThermalWorkPolicy.allow(true,19.8,15,true,false,false));
        assertFalse(MinorThermalWorkPolicy.allow(true,19.8,16,false,false,false));
        assertFalse(MinorThermalWorkPolicy.allow(false,20,20,true,false,false));
        assertFalse(MinorThermalWorkPolicy.allow(true,20,20,true,true,false));
        assertFalse(MinorThermalWorkPolicy.allow(true,20,20,true,false,true));
        assertFalse(MinorThermalWorkPolicy.allow(true,Double.NaN,20,true,false,false));
    }
}
