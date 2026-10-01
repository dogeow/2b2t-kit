package dev.twob2tkit.combat;

import org.junit.jupiter.api.Test;
import java.util.LinkedHashSet;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class MeteorCombatTargetLeaseTest {
    @Test void addsDetectedPiglinWithoutReplacingUserSelectionsAndRestoresThem() {
        FakeAura aura = new FakeAura(false);
        Set<Object> original = new LinkedHashSet<>(Set.of("skeleton", "enderman"));
        aura.entities.value = original;
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        assertEquals(Set.of("skeleton", "enderman", "piglin"), aura.entities.get());
        assertEquals(Set.of("skeleton", "enderman"), original, "The original mutable set must not be edited in place");
        assertFalse((Boolean) aura.onlyOnClick.get());
        assertFalse((Boolean) aura.onlyOnLook.get());
        assertTrue((Boolean) aura.autoSwitch.get());
        assertTrue((Boolean) aura.swapBack.get());
        assertTrue((Boolean) aura.ignorePassive.get(), "Selecting Piglin must retain Meteor's aggression filter");
        assertEquals(3.25, aura.range.get(), "Do not change combat range or unrelated user options");
        lease.release();
        assertEquals(Set.of("skeleton", "enderman"), aura.entities.get());
        assertFalse(aura.isActive());
        assertTrue((Boolean) aura.onlyOnClick.get());
        assertTrue((Boolean) aura.onlyOnLook.get());
        assertFalse((Boolean) aura.autoSwitch.get());
        assertFalse((Boolean) aura.swapBack.get());
        assertTrue(aura.deactivatedWithSwapBack, "Restore the borrowed weapon slot before resetting swap-back");
        assertFalse(lease.active());
    }

    @Test void piglinAlreadySelectedAndPreviouslyActiveAuraRemainSelectedAndActive() {
        FakeAura aura = new FakeAura(true);
        aura.entities.value = new LinkedHashSet<>(Set.of("piglin", "creeper"));
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        lease.release();
        assertTrue(aura.isActive());
        assertEquals(Set.of("piglin", "creeper"), aura.entities.get());
        assertEquals(0, aura.toggles);
    }

    @Test void sameCombatCanAddBruteAndRestoreBothAdditions() {
        FakeAura aura = new FakeAura(false);
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        assertTrue(lease.prepare(aura, "piglin_brute"));
        assertTrue(lease.prepare(aura, "piglin"));
        assertEquals(Set.of("skeleton", "piglin", "piglin_brute"), aura.entities.get());
        assertEquals(1, aura.toggles, "Repeated preparation must not toggle an active module");
        lease.release();
        assertEquals(Set.of("skeleton"), aura.entities.get());
    }

    @Test void userEntityEditIsPreservedAndNotOverwrittenByAnotherPreparation() {
        FakeAura aura = new FakeAura(false);
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        aura.entities.value = new LinkedHashSet<>(Set.of("blaze"));
        assertFalse(lease.ready());
        assertFalse(lease.prepare(aura, "piglin"));
        assertEquals(Set.of("blaze"), aura.entities.get());
        lease.release();
        assertEquals(Set.of("blaze"), aura.entities.get());
    }

    @Test void inPlaceUserEntityEditDoesNotAlterLeaseSnapshot() {
        FakeAura aura = new FakeAura(true);
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        ((Set<Object>) aura.entities.value).add("blaze");
        assertFalse(lease.ready());
        lease.release();
        assertEquals(Set.of("skeleton", "piglin", "blaze"), aura.entities.get());
    }

    @Test void userBooleanEditIsPreservedWhileOtherBorrowedSettingsRestore() {
        FakeAura aura = new FakeAura(true);
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        aura.ignorePassive.value = false;
        assertFalse(lease.prepare(aura, "piglin"));
        lease.release();
        assertFalse((Boolean) aura.ignorePassive.get());
        assertTrue((Boolean) aura.onlyOnClick.get());
        assertEquals(Set.of("skeleton"), aura.entities.get());
    }

    @Test void manuallyDisabledAuraIsNotReenabled() {
        FakeAura aura = new FakeAura(false);
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        aura.toggle();
        assertFalse(lease.prepare(aura, "piglin"));
        lease.release();
        assertFalse(aura.isActive());
        assertEquals(2, aura.toggles);
    }

    @Test void temporaryRangedPauseRestoredBeforeReleaseRetainsOriginalModuleOwnership() {
        FakeAura aura = new FakeAura(false);
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertTrue(lease.prepare(aura, "piglin"));
        aura.toggle(); // Host temporarily borrows KillAura for the bow or normal attack fallback.
        assertFalse(lease.ready());
        aura.toggle(); // Host restores its paused modules before releasing the melee lease.
        lease.release();
        assertFalse(aura.isActive(), "The originally disabled module must stay disabled after both leases release");
        assertEquals(Set.of("skeleton"), aura.entities.get());
    }

    @Test void rejectedSettingRollsBackPriorWritesAndDoesNotEnableAura() {
        FakeAura aura = new FakeAura(false);
        aura.onlyOnLook.reject = true;
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertFalse(lease.prepare(aura, "piglin"));
        assertEquals(Set.of("skeleton"), aura.entities.get());
        assertTrue((Boolean) aura.onlyOnClick.get());
        assertFalse(aura.isActive());
        assertFalse(lease.active());
        assertEquals(0, aura.toggles);
    }

    @Test void unavailableMeteorReturnsFalseForNormalAttackFallback() {
        MeteorCombatTargetLease lease = new MeteorCombatTargetLease();
        assertFalse(lease.prepare(null, "piglin"));
        assertFalse(lease.prepare(new Object(), "piglin"));
        assertFalse(lease.active());
    }

    public static class FakeSetting {
        Object value;
        boolean reject;
        FakeSetting(Object value) { this.value = value; }
        public Object get() { return value; }
        public boolean set(Object value) { if (reject) return false; this.value = value; return true; }
    }
    public static class FakeAura {
        private final FakeSetting entities = new FakeSetting(new LinkedHashSet<>(Set.of("skeleton")));
        private final FakeSetting onlyOnClick = new FakeSetting(true);
        private final FakeSetting onlyOnLook = new FakeSetting(true);
        private final FakeSetting autoSwitch = new FakeSetting(false);
        private final FakeSetting swapBack = new FakeSetting(false);
        private final FakeSetting ignorePassive = new FakeSetting(true);
        private final FakeSetting range = new FakeSetting(3.25);
        private boolean active;
        int toggles;
        boolean deactivatedWithSwapBack;
        FakeAura(boolean active) { this.active = active; }
        public boolean isActive() { return active; }
        public void toggle() {
            toggles++;
            if (active) deactivatedWithSwapBack = Boolean.TRUE.equals(swapBack.get());
            active = !active;
        }
    }
}
