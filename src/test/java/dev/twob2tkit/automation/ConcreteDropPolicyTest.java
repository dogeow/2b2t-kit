package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ConcreteDropPolicyTest {
    @Test void onlyNewNearbyExactDropsMayCloseAnInventoryDeficit() {
        assertTrue(ConcreteDropPolicy.eligible(true,false,true,25,25,9,4));
        assertFalse(ConcreteDropPolicy.eligible(true,true,true,25,25,9,4));
        assertFalse(ConcreteDropPolicy.eligible(true,false,false,25,25,9,4));
        assertFalse(ConcreteDropPolicy.eligible(true,false,true,26,25,9,4));
        assertFalse(ConcreteDropPolicy.eligible(true,false,true,25,25,100,4));
        assertFalse(ConcreteDropPolicy.eligible(true,false,true,25,25,9,32));
        assertFalse(ConcreteDropPolicy.eligible(false,false,true,25,25,9,4));
    }
    @Test void inaccessibleDropWaitsForObservedDriftOrOneSecond() {
        assertFalse(ConcreteDropPolicy.shouldRetry(true,.1,19));
        assertTrue(ConcreteDropPolicy.shouldRetry(true,.25,1));
        assertTrue(ConcreteDropPolicy.shouldRetry(true,0,20));
        assertTrue(ConcreteDropPolicy.shouldRetry(false,0,1));
    }
}
