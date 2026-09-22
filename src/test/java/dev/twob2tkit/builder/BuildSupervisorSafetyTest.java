package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.builder.BuildSupervisorSafety.Action.*;
class BuildSupervisorSafetyTest {
    @Test void completionDoesNotLeaveTheSingleplayerWorldRunningUnattended(){
        assertEquals(PAUSE_LOCAL,BuildSupervisorSafety.decide(true,false,true,false,true,true));
    }
    @Test void lossOfTheExternalProcessAlsoHasANativeFallback(){
        assertEquals(PAUSE_LOCAL,BuildSupervisorSafety.decide(true,false,true,true,false,true));
        assertEquals(LOGOUT,BuildSupervisorSafety.decide(true,false,false,true,false,true));
    }
    @Test void remotePreferenceIsExplicit(){
        assertEquals(LOGOUT,BuildSupervisorSafety.decide(true,false,false,false,true,true));
        assertEquals(KEEP_PVE_GUARD,BuildSupervisorSafety.decide(true,false,false,false,true,false));
    }
    @Test void manualTakeoverRevokesWithoutLoggingOutOrPausingNewUserWork(){
        assertEquals(REVOKE,BuildSupervisorSafety.decide(true,true,false,true,true,true));
        assertEquals(REVOKE,BuildSupervisorSafety.decide(false,false,true,true,true,true));
        assertEquals(NONE,BuildSupervisorSafety.decide(true,false,true,false,false,true));
    }
}
