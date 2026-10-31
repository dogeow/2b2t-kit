package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import net.minecraft.world.phys.Vec3;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class MaterialAirDriftTerminalTest {
 @Test void onlyExhaustedRestorationDriftHasTheSpecificMotionTerminal(){
  var s=new MaterialAirArrivalPolicy.Settlement(.2);
  for(int round=0;round<3;round++){
   for(int i=0;i<8;i++)s.observe(Vec3.ZERO,Vec3.ZERO,new Vec3(0,-.0784,0));
   if(round<2)assertEquals(MaterialAirArrivalPolicy.Decision.REACQUIRE,s.observe(new Vec3(.6,0,0),Vec3.ZERO,Vec3.ZERO));
   else assertThrows(MaterialAirArrivalPolicy.RestoredFlightDrift.class,()->s.observe(new Vec3(.6,0,0),Vec3.ZERO,Vec3.ZERO));
  }assertFalse(s.done());assertEquals(3,s.restorations());
 }
 @Test void specificDriftStopsWithoutRevokingOwnershipAndGeneralFailuresStillAbort()throws Exception{
  var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){assertNotNull(in);new ClassReader(in).accept(n,0);}
  var tick=n.methods.stream().filter(m->m.name.equals("tick")).findFirst().orElseThrow();
  var handler=tick.tryCatchBlocks.stream().filter(b->"dev/twob2tkit/automation/MaterialAirArrivalPolicy$RestoredFlightDrift".equals(b.type)).findFirst().orElseThrow();
  boolean finish=false,stopped=false;
  for(var i=handler.handler.getNext();i!=null;i=i.getNext()){
   if(i instanceof MethodInsnNode c){assertNotEquals("abortOwnedRequest",c.name);finish|=c.name.equals("finish");}
   if(i instanceof LdcInsnNode l)stopped|="stopped".equals(l.cst);
   if(i instanceof JumpInsnNode j&&j.getOpcode()==Opcodes.GOTO)break;
  }assertTrue(finish);assertTrue(stopped);
  assertTrue(tick.tryCatchBlocks.stream().anyMatch(b->"java/lang/Exception".equals(b.type)));
  assertTrue(java.util.stream.StreamSupport.stream(tick.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode c&&c.name.equals("abortOwnedRequest")));
 }
}
