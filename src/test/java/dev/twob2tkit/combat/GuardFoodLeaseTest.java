package dev.twob2tkit.combat;
import java.nio.file.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
class GuardFoodLeaseTest {
 @TempDir Path dir;
 enum Mode{Health,Hunger,Any,Both}
 public static class Setting {Object value;public Setting(Object value){this.value=value;}public Object get(){return value;}public boolean set(Object next){value=next;return true;}}
 static class Module {
  private final Setting thresholdMode=new Setting(Mode.Both),healthThreshold=new Setting(10.0),hungerThreshold=new Setting(16),searchInventory=new Setting(false);
 }
 @AfterEach void release(){GuardFoodLease.release();}
 @Test void ownedWorkEatsEarlyAndRestoresManualSettings(){
  var m=new Module();var p=dir.resolve("lease.json");GuardFoodLease.acquire(m,p);
  assertEquals(Mode.Any,m.thresholdMode.get());assertEquals(19.0,m.healthThreshold.get());assertEquals(19,m.hungerThreshold.get());assertEquals(true,m.searchInventory.get());
  GuardFoodLease.release();assertEquals(Mode.Both,m.thresholdMode.get());assertEquals(10.0,m.healthThreshold.get());assertEquals(16,m.hungerThreshold.get());assertEquals(false,m.searchInventory.get());
 }
 @Test void laterUserEditsAreNotOverwritten(){
  var m=new Module();GuardFoodLease.acquire(m,dir.resolve("lease.json"));m.healthThreshold.set(17.0);GuardFoodLease.release();assertEquals(17.0,m.healthThreshold.get());
 }
 @Test void receiptRecoversTemporaryValuesSavedBeforeRelease(){
  var m=new Module();var p=dir.resolve("lease.json");GuardFoodLease.acquire(m,p);GuardFoodLease.release();
  var loaded=new Module();loaded.thresholdMode.set(Mode.Any);loaded.healthThreshold.set(19.0);loaded.hungerThreshold.set(19);loaded.searchInventory.set(true);
  GuardFoodLease.recover(loaded,p);assertEquals(10.0,loaded.healthThreshold.get());assertEquals(Mode.Both,loaded.thresholdMode.get());assertFalse(Files.exists(p));
 }
}
