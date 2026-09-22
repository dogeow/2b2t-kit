package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class HealthRecoveryWindowTest {
 @Test void workDoesNotResumeImmediatelyAfterKillingTheAttacker(){
  var window=new HealthRecoveryWindow();assertFalse(window.hold(true,20,false));
  assertFalse(window.hold(true,16.6,true));assertTrue(window.hold(true,16.6,false));
  assertTrue(window.hold(true,18.5,false));assertFalse(window.hold(true,19,false));
 }
 @Test void combatKeepsPriorityWhileRecovering(){var window=new HealthRecoveryWindow();assertTrue(window.hold(true,17,false));assertFalse(window.hold(true,17,true));assertTrue(window.hold(true,18,false));}
 @Test void manualDisarmClearsRecoveryWithoutHoldingThePlayer(){var window=new HealthRecoveryWindow();window.hold(true,17,false);assertFalse(window.hold(false,17,false));assertFalse(window.hold(true,18.5,false));}
}
