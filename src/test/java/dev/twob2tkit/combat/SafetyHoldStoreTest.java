package dev.twob2tkit.combat;
import com.google.gson.*;
import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
class SafetyHoldStoreTest {
 @TempDir Path dir;
 @Test void restartDoesNotReleaseLowHealthLock()throws Exception{
  var path=dir.resolve("safety.json");var j=new JsonObject();j.addProperty("active",true);j.addProperty("health",10);
  new SafetyHoldStore(path).write(j);assertTrue(new SafetyHoldStore(path).active());
 }
 @Test void malformedExistingRecordsFailClosed()throws Exception{
  var p=dir.resolve("safety.json");for(String text:new String[]{"{bad","{}","{\"active\":\"false\"}","null"}){Files.writeString(p,text);assertTrue(new SafetyHoldStore(p).active(),text);}
 }
 @Test void OnlyExplicitAcknowledgementReleasesAcrossRestart()throws Exception{
  var p=dir.resolve("safety.json");var s=new SafetyHoldStore(p);assertFalse(s.active());var j=new JsonObject();j.addProperty("active",true);s.write(j);
  assertTrue(s.active());s.clearByUser();assertFalse(new SafetyHoldStore(p).active());assertEquals("game_ui",new SafetyHoldStore(p).read().get("cleared_by").getAsString());
 }
 @Test void aDoorRouteMustNotMoveCloserToANearbyHostile(){
  assertFalse(EmergencyExitPolicy.safeStep(0,64,0,1,64,0,2,64,0,3.5));
  assertTrue(EmergencyExitPolicy.safeStep(0,64,0,-1,64,0,2,64,0,3.5));
  assertTrue(EmergencyExitPolicy.safeStep(0,64,0,0,65,0,2,64,0,3.5));
  assertFalse(EmergencyExitPolicy.safeStep(0,64,0,0,65,0,0,66,0,3.5));
 }
 @Test void navigationCompletionNeverWaitsForFullHeightWhenCriticalOrBlocked(){
  assertEquals(EmergencyExitPolicy.Decision.CLIMB,EmergencyExitPolicy.decide(12,2,500,true));
  assertEquals(EmergencyExitPolicy.Decision.DISCONNECT,EmergencyExitPolicy.decide(6,2,500,true));
  assertEquals(EmergencyExitPolicy.Decision.DISCONNECT,EmergencyExitPolicy.decide(12,2,500,false));
  assertEquals(EmergencyExitPolicy.Decision.DISCONNECT,EmergencyExitPolicy.decide(18,12,500,true));
  assertEquals(EmergencyExitPolicy.Decision.DISCONNECT,EmergencyExitPolicy.decide(18,2,8000,true));
 }
}
