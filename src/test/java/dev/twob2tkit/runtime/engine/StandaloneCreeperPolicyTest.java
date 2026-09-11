package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class StandaloneCreeperPolicyTest {
    @Test void hoveringDoesNotHideANearbyCreeperBehindTheGenericHeightGate(){
        assertTrue(StandaloneCreeperPolicy.alert(true,false,false,7));
        assertFalse(StandaloneCreeperPolicy.alert(true,false,false,9));
    }
    @Test void closeCornerThreatsAndSwellingThreatsRemainActionable(){
        assertTrue(StandaloneCreeperPolicy.alert(false,false,false,3));
        assertTrue(StandaloneCreeperPolicy.alert(false,true,false,7));
        assertFalse(StandaloneCreeperPolicy.alert(false,false,false,7));
    }
    @Test void dangerousRangeEvadesBeforeChoosingAnArrow(){
        assertTrue(StandaloneCreeperPolicy.evade(false,false,5,false));
        assertTrue(StandaloneCreeperPolicy.evade(true,false,7,false));
        assertFalse(StandaloneCreeperPolicy.evade(false,false,7,false));
    }
    @Test void hysteresisPreventsStoppingEscapeAtTheEdgeOfDanger(){
        assertTrue(StandaloneCreeperPolicy.evade(false,false,7.9,true));
        assertFalse(StandaloneCreeperPolicy.evade(false,false,8.1,true));
    }
    @Test void chargedCreepersUseAWiderMargin(){
        assertTrue(StandaloneCreeperPolicy.alert(false,true,true,13));
        assertTrue(StandaloneCreeperPolicy.evade(false,true,9,false));
        assertTrue(StandaloneCreeperPolicy.evade(false,true,11.9,true));
        assertFalse(StandaloneCreeperPolicy.evade(false,true,12.1,true));
    }
    @Test void ascentMustNotMoveTowardACreeperAboveUs(){
        assertTrue(StandaloneCreeperPolicy.riseMovesAway(68,64));
        assertTrue(StandaloneCreeperPolicy.riseMovesAway(64,64));
        assertFalse(StandaloneCreeperPolicy.riseMovesAway(64,66));
    }
}
