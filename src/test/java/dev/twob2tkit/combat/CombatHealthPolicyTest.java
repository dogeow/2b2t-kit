package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class CombatHealthPolicyTest {
    @Test void naturalAbsorptionExpiryDoesNotClaimAnAttack(){
        assertTrue(CombatHealthPolicy.absorptionExpired(20,4,20,0,false,false));
    }
    @Test void actualBaseDamageOrRemainingEffectOrInjurySignalRemainDamage(){
        assertFalse(CombatHealthPolicy.absorptionExpired(20,4,19,0,false,false));
        assertFalse(CombatHealthPolicy.absorptionExpired(20,4,19.99F,0,false,false));
        assertFalse(CombatHealthPolicy.absorptionExpired(20,4,20,0,true,false));
        assertFalse(CombatHealthPolicy.absorptionExpired(20,4,20,0,false,true));
        assertFalse(CombatHealthPolicy.absorptionExpired(20,4,20,2,true,false));
    }
    @Test void unknownOrUninitializedValuesCannotSuppressProtection(){
        assertFalse(CombatHealthPolicy.absorptionExpired(-1,4,20,0,false,false));
        assertFalse(CombatHealthPolicy.absorptionExpired(20,0,20,0,false,false));
        assertFalse(CombatHealthPolicy.absorptionExpired(20,Float.NaN,20,0,false,false));
    }
}
