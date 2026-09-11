package dev.twob2tkit.concrete;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
class ConcretePolicyTest {
    @Test void supportsEveryVanillaColorAndRejectsOtherMaterials(){
        for(String color:List.of("white","orange","magenta","light_blue","yellow","lime","pink","gray","light_gray","cyan","purple","blue","brown","green","red","black"))
            assertEquals("minecraft:"+color+"_concrete",ConcretePolicy.solidId("minecraft:"+color+"_concrete_powder"));
        for(String other:List.of("minecraft:sand","minecraft:hopper","minecraft:white_concrete","mod:white_concrete_powder","minecraft:unknown_concrete_powder"))assertNull(ConcretePolicy.solidId(other));
        assertNull(ConcretePolicy.solidId(null));
    }
    @Test void dryPowderIsNeverMinedAndAReplacedContainerAlwaysStops(){
        for(boolean mining:List.of(false,true))for(boolean sent:List.of(false,true)){
            assertEquals(ConcretePolicy.Action.WAIT_WATER,ConcretePolicy.action(ConcretePolicy.Cell.POWDER,mining,sent));
            assertEquals(ConcretePolicy.Action.STOP,ConcretePolicy.action(ConcretePolicy.Cell.FOREIGN,mining,sent));
        }
    }
    @Test void breakMustBeVerifiedBeforeAnotherPlacement(){
        assertEquals(ConcretePolicy.Action.PLACE,ConcretePolicy.action(ConcretePolicy.Cell.EMPTY,false,false));
        assertEquals(ConcretePolicy.Action.WAIT_WATER,ConcretePolicy.action(ConcretePolicy.Cell.EMPTY,false,true));
        assertEquals(ConcretePolicy.Action.MINE,ConcretePolicy.action(ConcretePolicy.Cell.CONCRETE,false,true));
        assertEquals(ConcretePolicy.Action.VERIFY_BREAK,ConcretePolicy.action(ConcretePolicy.Cell.EMPTY,true,true));
    }
    @Test void toolThresholdAndDropRequirementsProtectThePickaxe(){
        assertTrue(ConcretePolicy.usableTool(true,true,1000,900,10));
        assertFalse(ConcretePolicy.usableTool(true,true,1000,901,10));
        assertFalse(ConcretePolicy.usableTool(true,true,100,92,1));
        assertFalse(ConcretePolicy.usableTool(false,false,0,0,10));
        assertTrue(ConcretePolicy.usableTool(true,false,0,0,10));
    }
    @Test void zeroIsUnlimitedAndPositiveLimitsStopExactly(){
        assertFalse(ConcretePolicy.reached(10000,0));assertFalse(ConcretePolicy.reached(15,16));
        assertTrue(ConcretePolicy.reached(16,16));assertTrue(ConcretePolicy.reached(17,16));
    }
}
