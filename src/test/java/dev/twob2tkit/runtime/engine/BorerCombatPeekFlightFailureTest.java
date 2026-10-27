package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerCombatPeekFlightFailureTest {
 @Test void anUnavailableOrChangedSpeedStopsThePeekWithoutCrashingTheClient(){
  var session=new BorerAreaFlightSession(); // Not acquired: speed() must reject safely.
  assertFalse(assertDoesNotThrow(()->BorerCombatPeek.applyFlightSpeed(session,.03)));
 }
}
