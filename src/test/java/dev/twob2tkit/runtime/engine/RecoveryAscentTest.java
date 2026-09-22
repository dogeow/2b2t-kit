package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class RecoveryAscentTest {
    @Test void onlyNearTheDeclaredStart(){assertTrue(RecoveryAscent.inScope(0,70,0,0,70,0,80,2000,1000));assertFalse(RecoveryAscent.inScope(5,70,0,0,70,0,80,2000,1000));assertFalse(RecoveryAscent.inScope(0,60,0,0,70,0,80,2000,1000));}
    @Test void boundedTimeAndHeight(){assertFalse(RecoveryAscent.inScope(0,70,0,0,70,0,90,2000,1000));assertFalse(RecoveryAscent.inScope(0,70,0,0,70,0,80,900,1000));assertFalse(RecoveryAscent.inScope(0,70,0,0,70,0,80,200000,1000));assertFalse(RecoveryAscent.inScope(0,70,0,0,70,0,Double.NaN,2000,1000));}
}
