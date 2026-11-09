package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;import static org.junit.jupiter.api.Assertions.*;
class LocalFarmConflictLeaseTest {
 public static final class FakeCriticals {boolean active;int toggles;FakeCriticals(boolean a){active=a;}public boolean isActive(){return active;}public void toggle(){active=!active;toggles++;}}
 @Test void restoresOnlyOriginallyActiveModule()throws Exception{var m=new FakeCriticals(true);var lease=new BorerCargoModules();lease.pause(m);assertFalse(m.active);lease.close();assertTrue(m.active);assertEquals(2,m.toggles);lease.close();assertEquals(2,m.toggles);}
 @Test void originallyInactiveModuleStaysInactive()throws Exception{var m=new FakeCriticals(false);var lease=new BorerCargoModules();lease.pause(m);lease.close();assertFalse(m.active);assertEquals(0,m.toggles);}
 @Test void laterUserReenableIsNotToggledAgain()throws Exception{var m=new FakeCriticals(true);var lease=new BorerCargoModules();lease.pause(m);m.toggle();lease.close();assertTrue(m.active);assertEquals(2,m.toggles);}
}
