package dev.twob2tkit.runtime.engine;
import com.google.gson.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BorerCombatContinuationTest {
 private JsonObject record(){return JsonParser.parseString("{\"time\":1000,\"player\":\"p\",\"server\":\"s\",\"dimension\":\"overworld\",\"targets\":[\"00000000-0000-0000-0000-000000000001\"]}").getAsJsonObject();}
 @Test void onlyRecentSamePlayerAndWorldCanRestore(){
  assertTrue(BorerCombatContinuation.matches(record(),2000,"p","s","overworld"));
  assertFalse(BorerCombatContinuation.matches(record(),2000,"other","s","overworld"));
  assertFalse(BorerCombatContinuation.matches(record(),2000,"p","s","nether"));
  assertFalse(BorerCombatContinuation.matches(record(),2000,"p","other","overworld"));
  assertFalse(BorerCombatContinuation.matches(record(),400000,"p","s","overworld"));
  assertFalse(BorerCombatContinuation.matches(record(),0,"p","s","overworld"));
 }
}
