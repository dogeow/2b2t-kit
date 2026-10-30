package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BorrowedPacketSneakTest {
 static class Fake implements BorrowedPacketSneak.Access {
  boolean active,possible=true;Object mode="Vanilla";int writes;
  public boolean active(){return active;}public Object mode(){return mode;}public Object packet(){return "Packet";}
  public void mode(Object value){mode=value;writes++;}public void active(boolean value){active=value;writes++;}
  public boolean eligible(){return active&&possible&&mode.equals("Packet");}
 }
 @Test void borrowsPacketOnlyForHazardAndRestoresOriginal()throws Exception{
  var f=new Fake();var l=new BorrowedPacketSneak();assertTrue(l.update(true,f));assertTrue(l.owned());
  assertEquals("Packet",f.mode);assertTrue(f.active);l.update(false,f);assertFalse(f.active);assertEquals("Vanilla",f.mode);
 }
 @Test void existingUserModuleIsNeverChanged()throws Exception{
  var f=new Fake();f.active=true;var l=new BorrowedPacketSneak();assertFalse(l.update(true,f));l.close();assertEquals(0,f.writes);assertTrue(f.active);
 }
 @Test void userModeChangeYieldsWithoutRestoringOverIt()throws Exception{
  var f=new Fake();var l=new BorrowedPacketSneak();l.update(true,f);f.mode="Vanilla";
  l.update(true,f);int writes=f.writes;l.close();assertEquals(writes,f.writes);assertEquals("Vanilla",f.mode);assertTrue(f.active);
 }
 @Test void userDisableIsNotReenabledUntilHazardScopeEnds()throws Exception{
  var f=new Fake();var l=new BorrowedPacketSneak();l.update(true,f);f.active=false;int writes=f.writes;
  l.update(true,f);l.update(true,f);assertEquals(writes,f.writes);l.update(false,f);assertTrue(l.update(true,f));
 }
 @Test void unsupportedPacketStateIsNotReportedAsProtection()throws Exception{
  var f=new Fake();f.possible=false;var l=new BorrowedPacketSneak();assertFalse(l.update(true,f));assertFalse(l.owned());assertFalse(f.active);assertEquals("Vanilla",f.mode);
 }
 @Test void failedActivationRollsBackBothModeAndModule()throws Exception{
  class Failing extends Fake {public void active(boolean value){active=value;if(value)throw new IllegalStateException("activation failed");}}
  var f=new Failing();var l=new BorrowedPacketSneak();assertThrows(IllegalStateException.class,()->l.update(true,f));assertFalse(f.active);assertEquals("Vanilla",f.mode);assertFalse(l.owned());
 }
 @Test void closeIsIdempotent()throws Exception{
  var f=new Fake();var l=new BorrowedPacketSneak();l.update(true,f);l.close();int writes=f.writes;l.close();assertEquals(writes,f.writes);
 }
}
