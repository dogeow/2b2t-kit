package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InkAttackPolicyTest {
    @Test void onlyOrdinaryWildSquidCanSupplyBlackInk(){
        assertTrue(InkAttackPolicy.target("minecraft:squid",true,false,false,10));
        for(String type:new String[]{"minecraft:glow_squid","minecraft:player","minecraft:dolphin","minecraft:wolf","minecraft:cow"})
            assertFalse(InkAttackPolicy.target(type,true,false,false,10));
    }
    @Test void namedDeadRemovedAndInvalidHealthTargetsAreProtected(){
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,false,true,10));
        assertFalse(InkAttackPolicy.target("minecraft:squid",false,false,false,10));
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,true,false,10));
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,false,false,0));
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,false,false,Float.NaN));
    }
}
