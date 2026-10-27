package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class BorerBlockedShotCounterTest {
    private final List<BorerDefensePolicy.Candidate> threats=List.of(
        new BorerDefensePolicy.Candidate(1,0,7,false),
        new BorerDefensePolicy.Candidate(2,1,11,true),
        new BorerDefensePolicy.Candidate(3,1,9,true),
        new BorerDefensePolicy.Candidate(4,1,3,false));
    @Test void observedBlockedCreeperAllowsAnIncomingArcherCounter(){
        var policy=new BorerBlockedShotCounter();
        assertEquals(-1,policy.choose(threats,1,10));
        policy.blocked(true,9,10);assertEquals(-1,policy.choose(threats,1,10));
        policy.blocked(true,10,11);assertEquals(3,policy.choose(threats,1,12));
        assertEquals(1,BorerDefensePolicy.choose(threats,3));
    }
    @Test void targetSwitchRetainsTheCounterDrawInsteadOfOscillatingBack(){
        var policy=new BorerBlockedShotCounter();policy.blocked(true,10,10);
        assertEquals(2,policy.choose(threats,2,11));
        assertEquals(2,policy.choose(threats,2,12));
        assertEquals(2,policy.choose(threats,2,30));
    }
    @Test void deadOrUnobservedShooterIsNeverRetained(){
        var policy=new BorerBlockedShotCounter();policy.blocked(true,10,10);
        assertEquals(-1,policy.choose(List.of(threats.get(0),threats.get(3)),2,12));
    }
    @Test void expiryAndNewCombatClearTheCounterWindow(){
        var policy=new BorerBlockedShotCounter();policy.blocked(true,10,10);
        assertEquals(-1,policy.choose(threats,2,110));
        policy.blocked(true,10,120);policy.clear();assertEquals(-1,policy.choose(threats,2,121));
    }
    @Test void blockedCounterShotReturnsToNormalDefense(){
        var policy=new BorerBlockedShotCounter();policy.blocked(true,10,10);
        policy.blocked(false,10,20);assertEquals(-1,policy.choose(threats,2,21));
    }
}
