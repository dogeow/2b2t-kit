package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class ManualInputPolicyTest {
    @Test void onlyRecentForegroundDirectionalInputHandsOff() {
        assertTrue(ManualInputPolicy.recent(1500,1100,true,false));
        assertFalse(ManualInputPolicy.recent(2000,1100,true,false));
        assertFalse(ManualInputPolicy.recent(1500,1100,false,false));
        assertFalse(ManualInputPolicy.recent(1500,1100,true,true));
    }
}
