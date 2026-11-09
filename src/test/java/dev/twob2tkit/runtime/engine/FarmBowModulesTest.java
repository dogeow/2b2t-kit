package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;import static org.junit.jupiter.api.Assertions.*;
class FarmBowModulesTest {
 public static class Setting{Object value;Setting(Object v){value=v;}public Object get(){return value;}public boolean set(Object v){value=v;return true;}}
 public static class Aura{Setting autoSwitch=new Setting(true),pauseOnUse=new Setting(false);boolean active=true;public boolean isActive(){return active;}public void toggle(){throw new AssertionError("KillAura must never be disabled");}}
 @Test void bowSetupNeverDisablesMeleeModule()throws Exception{var a=new Aura();var l=new FarmBowModules();l.borrow(a,"autoSwitch",false);l.borrow(a,"pauseOnUse",true);assertTrue(a.active);assertTrue(l.ready());l.close();assertTrue(a.active);assertEquals(true,a.autoSwitch.value);assertEquals(false,a.pauseOnUse.value);}
 @Test void laterUserSettingsAreNotOverwritten()throws Exception{var a=new Aura();var l=new FarmBowModules();l.borrow(a,"autoSwitch",false);a.autoSwitch.value=true;assertFalse(l.ready());l.close();assertEquals(true,a.autoSwitch.value);}
 @Test void partialConfigurationRestoresItsAcceptedWrites()throws Exception{var a=new Aura();var l=new FarmBowModules();l.borrow(a,"pauseOnUse",true);assertThrows(ReflectiveOperationException.class,()->l.borrow(a,"missingOption",false));l.close();assertEquals(false,a.pauseOnUse.value);assertTrue(a.active);}
}
