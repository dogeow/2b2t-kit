package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MaterialMiningLeaseTest {
    @Test void absentOptionalModuleNeedsNoIsolation() {
        var lease = MaterialMiningLease.acquireModule(null);
        assertFalse(lease.available());
        assertTrue(lease.ready());
        assertDoesNotThrow(lease::close);
        assertDoesNotThrow(lease::close);
    }

    @Test void nestedLeasesPauseOnceAndOnlyLastCloseRestores() {
        var module = new FakeModule(true);
        var first = MaterialMiningLease.acquireModule(module);
        var second = MaterialMiningLease.acquireModule(module);
        try {
            assertTrue(first.available());
            assertTrue(first.ready());
            assertTrue(second.ready());
            assertFalse(module.active);
            assertEquals(1, module.toggles);
            first.close();
            first.close();
            assertFalse(module.active);
            assertEquals(1, module.toggles);
            assertTrue(second.ready());
            second.close();
            assertTrue(module.active);
            assertEquals(2, module.toggles);
            second.close();
            assertEquals(2, module.toggles);
        } finally {
            first.close();
            second.close();
        }
    }

    @Test void originallyInactiveModuleIsNeverEnabledOnRelease() {
        var module = new FakeModule(false);
        var first = MaterialMiningLease.acquireModule(module);
        var second = MaterialMiningLease.acquireModule(module);
        try {
            assertTrue(first.ready());
            assertTrue(second.ready());
            assertEquals(0, module.toggles);
        } finally {
            first.close();
            second.close();
        }
        assertFalse(module.active);
        assertEquals(0, module.toggles);
    }

    @Test void manualOffOnOffRoundTripPermanentlyRevokesBothLeases() {
        var module = new FakeModule(true);
        var first = MaterialMiningLease.acquireModule(module);
        var second = MaterialMiningLease.acquireModule(module);
        try {
            module.toggle();
            module.toggle();
            assertFalse(module.active);
            assertFalse(first.ready());
            assertFalse(second.ready());
            assertFalse(first.ready());
            assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(module));
        } finally {
            first.close();
            second.close();
        }
        assertFalse(module.active);
        assertEquals(3, module.toggles);
    }

    @Test void manualEnableIsPreservedWhenAllLeasesClose() {
        var module = new FakeModule(true);
        var lease = MaterialMiningLease.acquireModule(module);
        try {
            module.toggle();
            assertTrue(module.active);
            assertFalse(lease.ready());
        } finally {
            lease.close();
        }
        assertTrue(module.active);
        assertEquals(2, module.toggles);
    }

    @Test void replacementModuleInvalidatesStaleRestoreOwnership() {
        var oldModule = new FakeModule(true);
        var replacement = new FakeModule(true);
        var stale = MaterialMiningLease.acquireModule(oldModule);
        var current = MaterialMiningLease.acquireModule(replacement);
        try {
            assertFalse(stale.ready());
            assertTrue(current.ready());
            stale.close();
            assertFalse(oldModule.active);
            assertEquals(1, oldModule.toggles);
            assertFalse(replacement.active);
            assertTrue(current.ready());
        } finally {
            stale.close();
            current.close();
        }
        assertTrue(replacement.active);
        assertEquals(2, replacement.toggles);
        assertFalse(oldModule.active);
    }

    @Test void unsupportedOrRejectedAcquisitionCannotClaimReadyOwnership() {
        var unreadable = new FakeModule(true);
        unreadable.rejectReads = true;
        var rejected = new FakeModule(true);
        rejected.rejectToggle = true;
        var ineffective = new FakeModule(true);
        ineffective.ignoreToggle = true;
        assertAll(
            () -> assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(new Object())),
            () -> assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(new MissingToggle(true))),
            () -> assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(new MissingToggle(false))),
            () -> assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(new InvalidActiveState())),
            () -> assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(unreadable)),
            () -> assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(rejected)),
            () -> assertThrows(IllegalStateException.class,
                () -> MaterialMiningLease.acquireModule(ineffective))
        );
        assertTrue(unreadable.active);
        assertTrue(rejected.active);
        assertTrue(ineffective.active);
    }

    @Test void laterReadFailurePermanentlyLosesRestorationPermission() {
        var module = new FakeModule(true);
        var lease = MaterialMiningLease.acquireModule(module);
        try {
            module.rejectReads = true;
            assertFalse(lease.ready());
            module.rejectReads = false;
            assertFalse(lease.ready());
        } finally {
            module.rejectReads = false;
            lease.close();
        }
        assertFalse(module.active);
        assertEquals(1, module.toggles);
    }

    @Test void queuedPacketsRemainBlockedOnlyForTheCurrentOpenScope() {
        var module = new FakeModule(true);
        var lease = MaterialMiningLease.acquireModule(module);
        try {
            assertFalse(lease.packetBlocked(false));
            assertTrue(lease.packetBlocked(true));
            module.toggle();
            assertFalse(lease.ready());
            assertTrue(lease.packetBlocked(true));
            assertFalse(lease.packetBlocked(false));
        } finally {
            lease.close();
        }
        assertFalse(lease.packetBlocked(true));
        assertFalse(lease.packetBlocked(false));
    }

    @Test void snapshotObservesRealPauseAndPostReleaseRestoreWithoutReconfiguring() {
        var module=new FakeModule(true);var lease=MaterialMiningLease.acquireModule(module);
        try{
            var paused=MaterialMiningLease.snapshot(lease,true,module);
            assertTrue(paused.get("active_scope").getAsBoolean());
            assertTrue(paused.get("module_available").getAsBoolean());
            assertFalse(paused.get("module_active").getAsBoolean());
            assertTrue(paused.get("restore_owned").getAsBoolean());
            long generation=paused.get("generation").getAsLong();
            assertEquals(1,module.toggles);
            lease.close();
            var released=MaterialMiningLease.snapshot(null,false,module);
            assertFalse(released.get("active_scope").getAsBoolean());
            assertTrue(released.get("module_active").getAsBoolean());
            assertFalse(released.get("restore_owned").getAsBoolean());
            assertEquals(generation,released.get("generation").getAsLong());
            assertEquals(2,module.toggles);
        }finally{lease.close();}
    }
    @Test void snapshotDoesNotClaimRestoreAfterAnExternalToggleRoundTrip() {
        var module=new FakeModule(true);var lease=MaterialMiningLease.acquireModule(module);
        try{
            module.toggle();module.toggle();
            var observed=MaterialMiningLease.snapshot(lease,true,module);
            assertTrue(observed.get("active_scope").getAsBoolean());
            assertFalse(observed.get("module_active").getAsBoolean());
            assertFalse(observed.get("restore_owned").getAsBoolean());
            assertEquals(3,module.toggles);
        }finally{lease.close();}
        assertFalse(module.active);
    }
    @Test void unknownSnapshotValuesRemainNullAndRestorationFailureIsReportedWithoutRetry() {
        var absent=MaterialMiningLease.snapshot(null,false,null);
        assertFalse(absent.get("module_available").getAsBoolean());
        assertTrue(absent.get("module_active").isJsonNull());
        var module=new FakeModule(true);var lease=MaterialMiningLease.acquireModule(module);
        module.rejectReads=true;
        var unreadable=MaterialMiningLease.snapshot(lease,true,module);
        assertTrue(unreadable.get("module_available").getAsBoolean());
        assertTrue(unreadable.get("module_active").isJsonNull());
        assertFalse(unreadable.get("restore_owned").getAsBoolean());
        module.rejectReads=false;module.ignoreToggle=true;
        lease.close();
        assertFalse(module.active);assertFalse(lease.failure().isEmpty());
        int attempts=module.toggles;lease.close();assertEquals(attempts,module.toggles);
    }

    public static class FakeModule {
        boolean active, rejectReads, rejectToggle, ignoreToggle;
        int toggles;
        FakeModule(boolean active) { this.active = active; }
        public boolean isActive() {
            if (rejectReads) throw new IllegalStateException("Read rejected");
            return active;
        }
        public void toggle() {
            if (rejectToggle) throw new IllegalStateException("Toggle rejected");
            // Mirrors the production Module.toggle HEAD lifecycle observation.
            MaterialMiningLease.moduleToggleObserved(this);
            toggles++;
            if (!ignoreToggle) active = !active;
        }
    }

    public static class MissingToggle {
        final boolean active;
        MissingToggle(boolean active) { this.active = active; }
        public boolean isActive() { return active; }
    }

    public static class InvalidActiveState {
        public String isActive() { return "false"; }
        public void toggle() { fail("Invalid state must be rejected before mutation"); }
    }
}
