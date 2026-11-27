package dev.twob2tkit.logreview;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RepeatLogGateTest {
    @Test void sameTargetIsLoggedOncePerWindowWhileNewTargetsPassAtOnce() {
        var gate = new RepeatLogGate(5_000);
        assertTrue(gate.allow("761009,64,797851|761008,64,797851", 0));
        for (long t = 50; t < 5_000; t += 50) assertFalse(gate.allow("761009,64,797851|761008,64,797851", t));
        assertTrue(gate.allow("761009,64,797851|761008,64,797851", 5_000), "a long stall still shows up again");
        assertTrue(gate.allow("761010,64,797857|-", 5_050));
        assertTrue(gate.allow("761009,64,797851|761008,64,797851", 5_100), "switching back is a new event");
    }

    @Test void resetLetsTheNextSessionLogImmediately() {
        var gate = new RepeatLogGate(5_000);
        assertTrue(gate.allow("a", 100));
        gate.reset();
        assertTrue(gate.allow("a", 200));
    }
}
