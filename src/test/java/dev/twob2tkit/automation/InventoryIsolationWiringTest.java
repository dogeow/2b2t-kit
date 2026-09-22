package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class InventoryIsolationWiringTest {
 private MethodNode method(String type,String name)throws Exception{
  var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+type+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
  return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
 }
 private List<String> calls(MethodNode method){var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode m)result.add(m.owner+"."+m.name);return result;}
 @Test void ipnRefillAndCraftCallbacksBothHonorKitOwnership()throws Exception{
  for(String name:List.of("kit$ownedTick","kit$ownedCraft")){
   var c=calls(method("mixin/InventoryProfilesCraftingGuardMixin",name));
   assertTrue(c.indexOf("dev/twob2tkit/automation/AutomationBridge.ownsMaterialInventory")<c.indexOf("org/spongepowered/asm/mixin/injection/callback/CallbackInfo.cancel"));
  }
  assertTrue(calls(method("mixin/InventoryProfilesCraftingGuardMixin","kit$ownedTick")).contains("dev/twob2tkit/automation/CraftingCompatibility.tickHookSeen"));
 }
 @Test void externalPrinterCannotBypassInventoryOwnershipByBeingUnowned()throws Exception{
  var m=method("automation/ProfessionalPrinter","allowNativeProposal");
  var first=m.instructions.getFirst();while(!(first instanceof MethodInsnNode))first=first.getNext();
  assertEquals("ownsMaterialInventory",((MethodInsnNode)first).name);
 }
 @Test void craftingMenuOwnershipIsObservedEvenForAllowedSurvivalMenus()throws Exception{
  var c=calls(method("automation/AutomationBridge","beforeInput"));
  assertTrue(c.indexOf("dev/twob2tkit/automation/AutomationBridge.ownsMaterialMenu")<c.indexOf("dev/twob2tkit/automation/AutomationBridge.survivalMenu"));
 }
 @Test void emergencyStopIncludesTheExternalPrinter()throws Exception{
  var c=calls(method("automation/AutomationBridge","cancel"));
  assertTrue(c.indexOf("dev/twob2tkit/automation/ProfessionalPrinter.stop")<c.indexOf("dev/twob2tkit/automation/AutomationBridge.disarmGuard"));
 }
}
