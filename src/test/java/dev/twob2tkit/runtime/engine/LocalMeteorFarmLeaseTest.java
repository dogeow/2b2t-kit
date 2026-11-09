package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;import static org.junit.jupiter.api.Assertions.*;import java.util.*;
class LocalMeteorFarmLeaseTest {
 public static class Setting{Object v;Setting(Object v){this.v=v;}public Object get(){return v;}public boolean set(Object n){v=n;return true;}}
 public static class Aura{Setting entities=new Setting(new LinkedHashSet<>(Set.of("zombie"))),ignorePassive=new Setting(true),onlyOnClick=new Setting(true),onlyOnLook=new Setting(true),range=new Setting(4.5),wallsRange=new Setting(0.0),maxTargets=new Setting(3),customDelay=new Setting(true);boolean active=true;public boolean isActive(){return active;}}
 @Test void meteorGetsOnlyTheRequestedPiglinAndNoClickRequirement(){var a=new Aura();var l=new LocalMeteorFarmLease();assertTrue(l.acquire(a,"zombified_piglin"));assertEquals(Set.of("zombified_piglin"),a.entities.v);assertEquals(false,a.ignorePassive.v);assertEquals(false,a.onlyOnClick.v);assertEquals(3.0,a.wallsRange.v);l.close();assertEquals(Set.of("zombie"),a.entities.v);assertEquals(true,a.ignorePassive.v);assertEquals(0.0,a.wallsRange.v);}
 @Test void laterUserSettingsArePreservedAndStopTheLease(){var a=new Aura();var l=new LocalMeteorFarmLease();assertTrue(l.acquire(a,"zombified_piglin"));a.range.v=2.5;assertFalse(l.ready());l.close();assertEquals(2.5,a.range.v);assertEquals(true,a.ignorePassive.v);}
 @Test void manualModuleDisableNeverReenablesIt(){var a=new Aura();var l=new LocalMeteorFarmLease();assertTrue(l.acquire(a,"zombified_piglin"));a.active=false;assertFalse(l.ready());l.close();assertFalse(a.active);}
 @Test void missingModuleRefusesWithoutAffectingSettings(){var l=new LocalMeteorFarmLease();assertFalse(l.acquire(new Object(),"zombified_piglin"));l.close();}
}
