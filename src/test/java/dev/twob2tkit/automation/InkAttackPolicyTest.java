package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InkAttackPolicyTest {
    @Test void typedWildSquidSpeciesCanBeAttackedWithoutClaimingTheirLoot(){
        assertTrue(InkAttackPolicy.target("minecraft:squid",true,false,false,10));
        assertTrue(InkAttackPolicy.target("minecraft:glow_squid",true,false,false,10));
        assertFalse(InkAttackPolicy.target("minecraft:glow_squid",true,false,true,10));
        for(String type:new String[]{"minecraft:player","minecraft:dolphin","minecraft:wolf","minecraft:cow"})
            assertFalse(InkAttackPolicy.target(type,true,false,false,10));
    }
    @Test void namedDeadRemovedAndInvalidHealthTargetsAreProtected(){
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,false,true,10));
        assertFalse(InkAttackPolicy.target("minecraft:squid",false,false,false,10));
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,true,false,10));
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,false,false,0));
        assertFalse(InkAttackPolicy.target("minecraft:squid",true,false,false,Float.NaN));
    }
    @Test void waterAttackRequiresCurrentWorkAirReserve(){
        assertTrue(InkAttackPolicy.environment(true,false,300,260));
        assertTrue(InkAttackPolicy.environment(true,false,260,260));
        assertFalse(InkAttackPolicy.environment(true,false,259,260));
        assertTrue(InkAttackPolicy.environment(true,false,120,110));
        assertFalse(InkAttackPolicy.environment(true,false,109,110));
    }
    @Test void missingOrUnreachableAirBudgetCannotAuthorizeWaterAttack(){
        assertFalse(InkAttackPolicy.environment(true,false,300,0));
        assertFalse(InkAttackPolicy.environment(true,false,300,301));
        assertFalse(InkAttackPolicy.environment(true,false,300,-1));
    }
    @Test void dryAttackRemainsAvailableButFireIsNeverAllowed(){
        assertTrue(InkAttackPolicy.environment(false,false,300,260));
        assertFalse(InkAttackPolicy.environment(false,true,300,260));
        assertFalse(InkAttackPolicy.environment(true,true,300,260));
    }
}
