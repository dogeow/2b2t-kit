package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GravelFootingPolicyTest {
    @Test void acceptsOnlyNearbyStableFootingWithEnoughAir() {
        assertTrue(GravelFootingPolicy.mayStand(true,true,1,2,300,260));
        assertFalse(GravelFootingPolicy.mayStand(false,true,1,2,300,260));
        assertFalse(GravelFootingPolicy.mayStand(true,false,1,2,300,260));
        assertFalse(GravelFootingPolicy.mayStand(true,true,1.4,2,300,260));
        assertFalse(GravelFootingPolicy.mayStand(true,true,1,5.1,300,260));
        assertFalse(GravelFootingPolicy.mayStand(true,true,1,2,259,260));
    }

    @Test void miningTheBlockUnderfootRequiresOwnedSafeUnderwaterGravel() {
        assertTrue(GravelFootingPolicy.mayMineUnderfoot(true,true,true,true,true,20,300,260));
        assertFalse(GravelFootingPolicy.mayMineUnderfoot(false,true,true,true,true,20,300,260));
        assertFalse(GravelFootingPolicy.mayMineUnderfoot(true,false,true,true,true,20,300,260));
        assertFalse(GravelFootingPolicy.mayMineUnderfoot(true,true,false,true,true,20,300,260));
        assertFalse(GravelFootingPolicy.mayMineUnderfoot(true,true,true,false,true,20,300,260));
        assertFalse(GravelFootingPolicy.mayMineUnderfoot(true,true,true,true,false,20,300,260));
        assertFalse(GravelFootingPolicy.mayMineUnderfoot(true,true,true,true,true,18,300,260));
        assertFalse(GravelFootingPolicy.mayMineUnderfoot(true,true,true,true,true,20,259,260));
    }
}
