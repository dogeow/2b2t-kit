package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class EmergencyExitWiringTest {
 private List<String> calls(String type,String name)throws Exception{
  var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+type+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}
  var m=n.methods.stream().filter(x->x.name.equals(name)).findFirst().orElseThrow();var result=new ArrayList<String>();
  for(var i:m.instructions)if(i instanceof MethodInsnNode c)result.add(c.owner+"."+c.name);return result;
 }
 @Test void physicalStopWinsThenEmergencyEscapeThenOrdinaryDefense()throws Exception{
  var c=calls("KitClient","tickNavigation");
  assertTrue(c.indexOf("dev/twob2tkit/KitClient.handleHeldKeys")<c.indexOf("dev/twob2tkit/combat/EmergencyExit.tick"));
  assertTrue(c.indexOf("dev/twob2tkit/combat/EmergencyExit.tick")<c.indexOf("dev/twob2tkit/automation/AutomationBridge.beforeGuard"));
 }
 @Test void defensePauseCannotEraseFlightOrMovement()throws Exception{
  var c=calls("builder/ProjectionBuildJob","pauseForDefense");
  assertTrue(c.stream().anyMatch(x->x.endsWith("ProfessionalPrinter.pause")));
  assertFalse(c.stream().anyMatch(x->x.endsWith(".setDown")||x.endsWith(".hover")||x.endsWith(".release")));
 }
 @Test void emergencyStopCancelsAscentAndAnyQueuedDisconnect()throws Exception{
  var c=calls("KitClient","stopAll");assertTrue(c.contains("dev/twob2tkit/combat/EmergencyExit.cancel"));assertTrue(c.contains("dev/twob2tkit/KitController.cancelPendingLogout"));
 }
 @Test void blockedZombieAscentFallsThroughToCombatRatherThanDisconnecting()throws Exception{
  var c=calls("runtime/engine/BorerRangedCombat","hoverZombie");
  assertTrue(c.indexOf("dev/twob2tkit/runtime/engine/BorerRangedCombat.clearWholeRise")<c.indexOf("dev/twob2tkit/runtime/engine/BorerAreaFlightSession.acquire"));
  assertFalse(c.stream().anyMatch(x->x.endsWith(".requestEmergencyExit")));
 }
 @Test void bothHeldAndInventoryBowsAreVerified()throws Exception{
  var c=calls("runtime/engine/BorerRangedCombat","selectBow");assertEquals(2,c.stream().filter(x->x.endsWith(".usableBow")).count());
 }
}
