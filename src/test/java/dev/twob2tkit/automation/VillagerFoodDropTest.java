package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class VillagerFoodDropTest {
    @Test void breadCannotBeThrownAtStaleActorsOrFromChangedPlayerInventory(){
        assertDoesNotThrow(()->VillagerFoodDrop.require(true,false,true,true,true,true,true,6,6,2));
        for(int rejected=0;rejected<7;rejected++){
            boolean[] flags={true,false,true,true,true,true,true};flags[rejected]=!flags[rejected];
            assertThrows(IllegalStateException.class,()->VillagerFoodDrop.require(flags[0],flags[1],flags[2],flags[3],flags[4],flags[5],flags[6],6,6,2));
        }
        assertThrows(IllegalStateException.class,()->VillagerFoodDrop.require(true,false,true,true,true,true,true,5,6,2));
        assertThrows(IllegalStateException.class,()->VillagerFoodDrop.require(true,false,true,true,true,true,true,6,6,3.1));
    }
}
