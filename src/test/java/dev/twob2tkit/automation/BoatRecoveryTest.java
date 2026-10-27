package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BoatRecoveryTest {
    @Test void healthyFoodAnimalRecoveryIsExplicitAndNeverIncludesPetsBabiesOrWoundedAnimals(){
        assertTrue(BoatRecovery.foodPassenger("minecraft:pig",true,false,false,10,10));
        assertTrue(BoatRecovery.foodPassenger("minecraft:chicken",true,false,false,4,4));
        assertFalse(BoatRecovery.foodPassenger("minecraft:pig",false,false,false,10,10));
        assertFalse(BoatRecovery.foodPassenger("minecraft:pig",true,true,false,10,10));
        assertFalse(BoatRecovery.foodPassenger("minecraft:pig",true,false,true,10,10));
        assertFalse(BoatRecovery.foodPassenger("minecraft:pig",true,false,false,9,10));
        assertFalse(BoatRecovery.foodPassenger("minecraft:horse",true,false,false,20,20));
        assertFalse(BoatRecovery.foodPassenger("minecraft:player",true,false,false,20,20));
    }
    @Test void wrongBoatPassengerLandingOrOwnerCannotReceiveAnAttack(){
        assertDoesNotThrow(()->BoatRecovery.require(true,false,true,true,true,true,true,true,true,2,3));
        for(int rejected=0;rejected<9;rejected++){
            boolean[] flags={true,false,true,true,true,true,true,true,true};flags[rejected]=!flags[rejected];
            assertThrows(IllegalStateException.class,()->BoatRecovery.require(flags[0],flags[1],flags[2],flags[3],flags[4],flags[5],flags[6],flags[7],flags[8],2,3));
        }
        assertThrows(IllegalStateException.class,()->BoatRecovery.require(true,false,true,true,true,true,true,true,true,2.9,3));
        assertThrows(IllegalStateException.class,()->BoatRecovery.require(true,false,true,true,true,true,true,true,true,Double.NaN,3));
    }
}
