package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ScaffoldModuleLeaseTest {
    @Test void configuresOffEnablesOnlyExplicitlyAndRestoresOffBeforeOriginalSettings() {
        var module=new FakeScaffold();var original=(List<?>)module.blocks.get();var lease=new ScaffoldModuleLease();
        try{
            assertTrue(lease.acquireModule(module,"cobble"));
            assertFalse(module.isActive());assertEquals(0,module.toggles);
            assertEquals(List.of("cobble"),module.blocks.get());assertEquals(List.of("dirt","stone"),original);
            assertEquals(ListMode.Whitelist,module.blocksFilter.get());
            assertTrue((Boolean)module.airPlace.get());assertTrue((Boolean)module.autoSwitch.get());
            assertEquals(0.0,module.radius.get());assertEquals(0.0,module.aheadDistance.get());
            assertEquals(1,module.blocksPerTick.get());assertFalse((Boolean)module.fastTower.get());
            assertFalse((Boolean)module.onlyOnClick.get());assertFalse((Boolean)module.rotate.get());
            assertEquals(6.5,module.placeRange.get());
            assertTrue(lease.enableOwned());assertTrue(lease.activeOwned());assertTrue(lease.settingsCurrent());
        }finally{lease.close();}
        assertFalse(module.isActive());assertTrue(module.deactivatedWithOwnedSettings);
        assertEquals(List.of("dirt","stone"),module.blocks.get());assertEquals(ListMode.Blacklist,module.blocksFilter.get());
        assertEquals(2.5,module.radius.get());assertTrue((Boolean)module.rotate.get());assertFalse(lease.acquired());
    }
    @Test void guardPauseStopsImmediatelyAndCanResumeWithoutRestoringSettingsYet() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        try{
            assertTrue(lease.acquireModule(module,"cobble"));assertTrue(lease.enableOwned());
            assertTrue(lease.disableOwned());assertFalse(module.isActive());
            assertEquals(List.of("cobble"),module.blocks.get());assertTrue(lease.settingsCurrent());
            assertTrue(lease.enableOwned());assertTrue(module.isActive());
        }finally{lease.close();}
    }
    @Test void alreadyActiveUserScaffoldIsNeverTakenOrReconfigured() {
        var module=new FakeScaffold();module.active=true;var lease=new ScaffoldModuleLease();
        assertFalse(lease.acquireModule(module,"cobble"));lease.close();
        assertTrue(module.isActive());assertEquals(List.of("dirt","stone"),module.blocks.get());assertEquals(0,module.toggles);
    }
    @Test void rejectedSettingRollsBackPriorWritesWithoutAnyActivation() {
        var module=new FakeScaffold();module.autoSwitch.reject=true;var lease=new ScaffoldModuleLease();
        assertFalse(lease.acquireModule(module,"cobble"));
        assertFalse(module.isActive());assertEquals(0,module.toggles);assertFalse(lease.acquired());
        assertEquals(List.of("dirt","stone"),module.blocks.get());assertEquals(2.5,module.radius.get());
    }
    @Test void laterUserSettingAndInPlaceBlockListChangesAreRetained() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        assertTrue(lease.acquireModule(module,"cobble"));assertTrue(lease.enableOwned());
        ((List<Object>)module.blocks.value).add("user-block");module.radius.value=1.5;
        assertFalse(lease.settingsCurrent());lease.close();
        assertEquals(List.of("cobble","user-block"),module.blocks.get());assertEquals(1.5,module.radius.get());
        assertFalse(module.isActive());assertTrue((Boolean)module.rotate.get());
    }
    @Test void replacementSettingObjectIsNotRestoredByIdentityCoincidence() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        assertTrue(lease.acquireModule(module,"cobble"));var replacement=new FakeSetting(List.of("cobble"));module.blocks=replacement;
        assertFalse(lease.settingsCurrent());lease.close();
        assertSame(replacement,module.blocks);assertEquals(List.of("cobble"),replacement.get());
    }
    @Test void manualOffIsNeverReenabled() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        assertTrue(lease.acquireModule(module,"cobble"));assertTrue(lease.enableOwned());module.toggle();
        assertFalse(lease.enableOwned());assertFalse(lease.activeOwned());lease.close();assertFalse(module.isActive());
        assertEquals(2,module.toggles);
    }
    @Test void manualOffThenOnRoundTripRetainsTheUsersActiveChoice() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        assertTrue(lease.acquireModule(module,"cobble"));assertTrue(lease.enableOwned());module.toggle();module.toggle();
        assertTrue(module.isActive());assertFalse(lease.activeOwned());lease.close();
        assertTrue(module.isActive());assertEquals(3,module.toggles);
    }
    @Test void userEnablingDuringOwnedOffPauseIsNotDisabledOnClose() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        assertTrue(lease.acquireModule(module,"cobble"));assertTrue(lease.enableOwned());assertTrue(lease.disableOwned());
        module.toggle();assertFalse(lease.settingsCurrent());lease.close();assertTrue(module.isActive());
    }
    @Test void failedOwnedDisableCanBeRetriedBeforeSettingsAreRestored() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        assertTrue(lease.acquireModule(module,"cobble"));assertTrue(lease.enableOwned());module.rejectNextToggle=true;
        assertFalse(lease.disableOwned());assertTrue(module.isActive());assertTrue(lease.activeOwned());
        assertTrue(lease.disableOwned());assertFalse(module.isActive());lease.close();
    }
    @Test void failedCloseRetainsNarrowSettingsAndOwnershipUntilOffIsProved() {
        var module=new FakeScaffold();var lease=new ScaffoldModuleLease();
        assertTrue(lease.acquireModule(module,"cobble"));assertTrue(lease.enableOwned());module.rejectNextToggle=true;
        lease.close();assertTrue(lease.acquired());assertTrue(lease.activeOwned());
        assertEquals(List.of("cobble"),module.blocks.get());assertEquals(0.0,module.radius.get());
        lease.close();assertFalse(module.isActive());assertFalse(lease.acquired());
        assertEquals(List.of("dirt","stone"),module.blocks.get());
    }
    public enum ListMode { Whitelist,Blacklist }
    public static class FakeSetting {
        Object value;boolean reject;
        FakeSetting(Object value){this.value=value;}
        public Object get(){return value;}
        public boolean set(Object next){if(reject)return false;value=next;return true;}
    }
    public static class FakeScaffold {
        private FakeSetting blocks=new FakeSetting(new ArrayList<>(List.of("dirt","stone")));
        private final FakeSetting blocksFilter=new FakeSetting(ListMode.Blacklist);
        private final FakeSetting airPlace=new FakeSetting(false),radius=new FakeSetting(2.5),aheadDistance=new FakeSetting(1.0);
        private final FakeSetting blocksPerTick=new FakeSetting(4),autoSwitch=new FakeSetting(false),fastTower=new FakeSetting(true);
        private final FakeSetting onlyOnClick=new FakeSetting(true),rotate=new FakeSetting(true),placeRange=new FakeSetting(6.5);
        boolean active,rejectNextToggle,deactivatedWithOwnedSettings;int toggles;
        public boolean isActive(){return active;}
        public void toggle(){
            if(rejectNextToggle){rejectNextToggle=false;throw new IllegalStateException("Temporary rejection");}
            ScaffoldModuleLease.moduleToggleObserved(this);
            toggles++;if(active)deactivatedWithOwnedSettings=Boolean.TRUE.equals(airPlace.get())&&radius.get().equals(0.0);
            active=!active;
        }
    }
}
