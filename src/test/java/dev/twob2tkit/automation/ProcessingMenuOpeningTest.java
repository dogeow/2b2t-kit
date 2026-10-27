package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProcessingMenuOpeningTest {
 @Test void delayedServerMenuCannotFinishAtTheOldEightTickDeadline(){
  var p=new ProcessingMenuOpening();p.begin("r","StonecutterMenu",0);
  assertFalse(p.observe("r","InventoryMenu",0,8,true));assertFalse(p.ready("r",8));
  assertTrue(p.pending("r"));assertTrue(p.observe("r","StonecutterMenu",25,23,true));
  assertFalse(p.ready("r",24));assertTrue(p.ready("r",25));
 }
 @Test void differentRequestKindOldMenuOrLostOwnerNeverClaimsProcessingMenu(){
  var p=new ProcessingMenuOpening();p.begin("r","StonecutterMenu",10);
  assertFalse(p.observe("other","StonecutterMenu",25,20,true));
  assertFalse(p.observe("r","LoomMenu",25,20,true));
  assertFalse(p.observe("r","StonecutterMenu",10,20,true));
  assertFalse(p.observe("r","StonecutterMenu",25,20,false));assertTrue(p.cancelled("r"));
  assertFalse(p.observe("r","StonecutterMenu",25,21,true));
 }
 @Test void playerClosingTheObservedMenuCannotClaimASecondLateMenu(){
  var p=new ProcessingMenuOpening();p.begin("r","LoomMenu",0);
  assertTrue(p.observe("r","LoomMenu",25,20,true));
  assertFalse(p.observe("r","InventoryMenu",0,21,true));assertTrue(p.cancelled("r"));
  assertFalse(p.observe("r","LoomMenu",26,22,true));assertFalse(p.ready("r",30));
 }
}
