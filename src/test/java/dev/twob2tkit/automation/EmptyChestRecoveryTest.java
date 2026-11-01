package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class EmptyChestRecoveryTest {
 private boolean allow(boolean[] g,long remaining){return EmptyChestRecovery.allowed(g[0],g[1],g[2],g[3],g[4],g[5],g[6],g[7],g[8],g[9],g[10],g[11],remaining);}
 private boolean[] good(){return new boolean[]{true,true,true,true,true,true,true,true,true,true,true,false};}
 @Test void onlyCurrentServerEmptyOwnedSingleProjectionPairMayBeRecovered(){assertTrue(allow(good(),1));assertTrue(allow(good(),30_000));}
 @Test void nonemptyStaleForeignUnhealthyAutomatedWetOrOccupiedContextsStayProtected(){for(int i=0;i<12;i++){var g=good();g[i]=!g[i];assertFalse(allow(g,100),"gate"+i);}}
 @Test void expiryAndBadClockNeverAuthorizeContainerBreak(){for(long n:new long[]{0,-1,30_001,Long.MAX_VALUE})assertFalse(allow(good(),n));}
 @Test void actualHostUsesServerCallbacksOpeningPrepareAndMiningRecheck()throws Exception{
  var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("AutomationBridge.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}var expected=new java.util.HashSet<>(java.util.Set.of("serverFurnaceContent:content","serverFurnaceSlot:slot","start:opening","start:prepare","beforeInput:validateMining"));
  for(var m:node.methods)for(var ins:m.instructions)if(ins instanceof org.objectweb.asm.tree.MethodInsnNode call&&call.owner.endsWith("EmptyChestRecovery")){expected.remove(m.name+":"+call.name);if(call.name.equals("opening")||call.name.equals("prepare"))expected.remove("start:"+call.name);}
  assertTrue(expected.isEmpty(),expected.toString());
 }
}
