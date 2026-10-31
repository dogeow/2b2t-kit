package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import com.google.gson.JsonObject;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;
class MaterialAirTraceTest {
 @Test void boundedFramesRetainNewestEvidenceAndCopiesCannotAlterTheTrace(){
  var trace=new MaterialAirTrace();var frame=new JsonObject();
  for(int i=0;i<150;i++){frame.addProperty("tick",i);trace.add(frame);}
  var rows=trace.snapshot();assertEquals(128,rows.size());assertEquals(22,rows.get(0).getAsJsonObject().get("tick").getAsInt());
  assertEquals(149,rows.get(127).getAsJsonObject().get("tick").getAsInt());
  frame.addProperty("tick",999);rows.get(127).getAsJsonObject().addProperty("tick",888);
  assertEquals(149,trace.snapshot().get(127).getAsJsonObject().get("tick").getAsInt());
 }
 @Test void sampledInputAndSyntheticKeyStateUseDistinctStableBitFlags(){
  assertEquals(0,MaterialAirTrace.bits(false,false,false,false,false,false,false));
  assertEquals(127,MaterialAirTrace.bits(true,true,true,true,true,true,true));
  assertEquals(65,MaterialAirTrace.bits(true,false,false,false,false,false,true));
  assertEquals(40,MaterialAirTrace.bits(false,false,false,true,false,true,false));
 }
 public enum Mode { Velocity, Packet }
 public static class Setting {private final Object value;Setting(Object v){value=v;}public Object get(){return value;}}
 public static class Flight {
  private final Setting mode=new Setting(Mode.Velocity),speed=new Setting(.038411676985814276),verticalSpeedMatch=new Setting(false),noSneak=new Setting(true),antiKickMode=new Setting(Mode.Packet);
  private int delayLeft=17,offLeft=2;public boolean isActive(){return true;}
 }
 @Test void readsTheActualFlightFieldsWithoutChangingAnySetting(){
  var flight=new Flight();var row=MaterialAirTrace.flightState(flight);
  assertTrue(row.get("available").getAsBoolean());assertTrue(row.get("active").getAsBoolean());
  assertEquals("Velocity",row.get("mode").getAsString());assertEquals(.038411676985814276,row.get("speed").getAsDouble());
  assertEquals(17,row.get("delayLeft").getAsInt());assertEquals(2,row.get("offLeft").getAsInt());
  assertEquals(.038411676985814276,flight.speed.get());assertEquals(17,flight.delayLeft);
 }
 @Test void absentOrChangedOptionalMeteorCannotBreakNavigationDiagnostics(){
  assertFalse(MaterialAirTrace.flightState(null).get("available").getAsBoolean());
  var row=MaterialAirTrace.flightState(new Object());assertEquals("unavailable",row.get("speed").getAsString());
 }
 private ClassNode code(String name)throws Exception{var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/"+name+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n;}
 @Test void tracingCannotWritePlayerStateOrSettingsAndOrdinarySnapshotsDoNotDumpTheRing()throws Exception{
  for(var m:code("MaterialAirTrace").methods)for(var i:m.instructions){
   if(i instanceof MethodInsnNode call)assertFalse(Set.of("setDown","setPos","teleportTo","setDeltaMovement","toggle","enable","disable","useItem","useItemOn","set","setDouble","setBoolean").contains(call.name),call.owner+"."+call.name);
   if(i instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTFIELD)assertEquals("dev/twob2tkit/automation/MaterialAirTrace",f.owner);
  }
  var nav=code("MaterialAirNavigation");
  for(var m:nav.methods)if(m.name.equals("snapshot"))for(var i:m.instructions)if(i instanceof MethodInsnNode call)assertFalse(call.owner.endsWith("MaterialAirTrace")&&call.name.equals("snapshot"));
  assertTrue(nav.methods.stream().filter(m->m.name.equals("terminalSnapshot")).anyMatch(m->java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode call&&call.owner.endsWith("MaterialAirTrace")&&call.name.equals("snapshot"))));
 }
}
