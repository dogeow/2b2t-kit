package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class ManualInputPolicyTest {
    @Test void ignoresSmallMouseNoiseAndSyntheticCameraChanges() {
        assertFalse(ManualInputPolicy.mouseMoved(.2,.3));
        assertTrue(ManualInputPolicy.mouseMoved(2,0));
        assertFalse(ManualInputPolicy.mouseMoved(Double.NaN,2));
    }

    @Test void onlyRecentForegroundGameplayInputHandsOff() {
        assertTrue(ManualInputPolicy.recent(1500,1100,true,false));
        assertFalse(ManualInputPolicy.recent(2000,1100,true,false));
        assertFalse(ManualInputPolicy.recent(1500,1100,false,false));
        assertFalse(ManualInputPolicy.recent(1500,1100,true,true));
    }
}
