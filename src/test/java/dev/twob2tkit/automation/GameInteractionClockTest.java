package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class GameInteractionClockTest {
 @Test void realInteractionInvalidatesAnEarlierProofEvenWithinOneMillisecond(){var s=new GameInteractionClock.State();s.interaction(10);long proof=s.serial();s.interaction(10);assertNotEquals(proof,s.serial());assertEquals(0,s.idle(10));}
 @Test void uiHoverDelaysIdleButCannotPretendToBeAContainerClick(){var s=new GameInteractionClock.State();s.interaction(10);long proof=s.serial();s.uiMotion(100);assertEquals(proof,s.serial());assertEquals(5,s.idle(105));}
 @Test void staleClockUpdatesCannotAuthorizeEarlyIdle(){var s=new GameInteractionClock.State();s.interaction(100);s.interaction(50);s.uiMotion(90);assertEquals(0,s.idle(99));assertEquals(0,s.idle(100));assertEquals(5,s.idle(105));}
 @Test void telemetryStoresOnlyCountsAndTimes(){var s=new GameInteractionClock.State();s.interaction(10);s.uiMotion(20);var j=s.snapshot(25);assertEquals(java.util.Set.of("interaction_serial","last_interaction_at","last_ui_motion_at","idle_ms"),j.keySet());assertEquals(5,j.get("idle_ms").getAsLong());}
 @Test void actualInputHooksUseCurrent26_2CallbackSignatures()throws Exception{
  var k=Class.forName("net.minecraft.client.KeyboardHandler",false,getClass().getClassLoader());assertNotNull(k.getDeclaredMethod("keyPress",long.class,int.class,Class.forName("net.minecraft.client.input.KeyEvent")));assertNotNull(k.getDeclaredMethod("charTyped",long.class,Class.forName("net.minecraft.client.input.CharacterEvent")));
  var m=Class.forName("net.minecraft.client.MouseHandler",false,getClass().getClassLoader());assertNotNull(m.getDeclaredMethod("onButton",long.class,Class.forName("net.minecraft.client.input.MouseButtonInfo"),int.class));assertNotNull(m.getDeclaredMethod("onScroll",long.class,double.class,double.class));assertNotNull(m.getDeclaredMethod("onMove",long.class,double.class,double.class));
 }
 @Test void candidateHooksCoverTypingClicksScrollAndUiMotionWithoutReplacingMovementTakeover()throws Exception{
  int interactions=0,motion=0,movement=0;
  for(String name:new String[]{"KeyboardHandlerMixin","MouseHandlerMixin"}){var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/mixin/"+name+".class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}for(var m:node.methods)for(var ins:m.instructions)if(ins instanceof org.objectweb.asm.tree.MethodInsnNode call){if(call.owner.endsWith("GameInteractionClock")&&call.name.equals("interaction"))interactions++;if(call.owner.endsWith("GameInteractionClock")&&call.name.equals("guiMotion"))motion++;if(call.owner.endsWith("KitKeys")&&call.name.equals("notePhysicalKey"))movement++;}}
  assertEquals(4,interactions);assertEquals(1,motion);assertEquals(1,movement);
 }
 @Test void actualRecoveryProofsCaptureAndRecheckInteractionSerial()throws Exception{
  var expected=new java.util.HashSet<>(java.util.Set.of("EmptyChestRecovery:opening","EmptyChestRecovery:current","EmptyChestRecovery:prepare","EmptyChestRecovery:validateMining","OwnedBlankSignEditor:arm","OwnedBlankSignEditor:closeIfOwned"));
  for(String name:new String[]{"EmptyChestRecovery","OwnedBlankSignEditor"}){var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream(name+".class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}for(var m:node.methods)for(var ins:m.instructions)if(ins instanceof org.objectweb.asm.tree.MethodInsnNode call&&call.owner.endsWith("GameInteractionClock")&&call.name.equals("serial"))expected.remove(name+":"+m.name);}
  assertTrue(expected.isEmpty(),expected.toString());
 }
}
