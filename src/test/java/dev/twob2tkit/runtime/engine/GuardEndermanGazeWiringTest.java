package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class GuardEndermanGazeWiringTest {
 private List<String> calls(String type,String method)throws Exception{
  var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/"+type+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
  var names=new ArrayList<String>();for(var n:node.methods.stream().filter(m->m.name.equals(method)).findFirst().orElseThrow().instructions)
   if(n instanceof MethodInsnNode m)names.add(m.owner.substring(m.owner.lastIndexOf('/')+1)+"."+m.name);
  return names;
 }
 @Test void defaultHoldLooksAwayOnlyAfterExistingEmergencyAndRiseChecks()throws Exception{
  var c=calls("BorerRangedCombat","tick");assertTrue(c.indexOf("BorerRangedCombat.evadeCreeper")<c.indexOf("GuardEndermanGaze.apply"));
  assertTrue(c.indexOf("BorerRangedCombat.safetyRise")<c.indexOf("GuardEndermanGaze.apply"));
  int gaze=c.indexOf("GuardEndermanGaze.apply");assertTrue(gaze>=0);
  assertTrue(java.util.stream.IntStream.range(0,gaze).anyMatch(i->c.get(i).endsWith(".raiseShield")));
 }
 @Test void nearEndermanHoldUsesTheSameThreeDimensionalGaze()throws Exception{
  assertTrue(calls("BorerRangedCombat","defendEnderman").contains("GuardEndermanGaze.away"));
 }
 @Test void gazeHelperCannotAttackMoveOrClearCombatTargets()throws Exception{
  var c=new ArrayList<String>();c.addAll(calls("GuardEndermanGaze","away"));c.addAll(calls("GuardEndermanGaze","apply"));
  assertFalse(c.stream().anyMatch(n->n.endsWith(".attack")||n.endsWith(".clear")||n.contains("navigate")||n.contains("setDown")));
 }
}
