package dev.twob2tkit.combat;

import com.google.gson.JsonParser;
import java.nio.file.*;
import java.nio.file.attribute.FileTime;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class GuardFoodLeaseTest {
    @TempDir Path dir;
    enum Mode { Health, Hunger, Any, Both }
    public static class Setting {
        Object value;
        Object rejected;
        boolean rejectAfterMutation;
        int writes;
        Runnable onWrite;
        public Setting(Object value) { this.value = value; }
        public Object get() { return value; }
        public boolean set(Object next) {
            writes++;
            if (onWrite != null) onWrite.run();
            if (Objects.equals(next, rejected) && !rejectAfterMutation) return false;
            value = next;
            return !Objects.equals(next, rejected);
        }
    }
    static class Module {
        private final Setting thresholdMode = new Setting(Mode.Both);
        private final Setting healthThreshold = new Setting(10.0);
        private final Setting hungerThreshold = new Setting(16);
        private final Setting searchInventory = new Setting(false);
        private final Setting blacklist = new Setting(List.of("rotten_flesh", "golden_apple"));
        private final Setting prioritise = new Setting("Saturation");

        // Meteor requires a satisfied trigger AND an eligible food slot. This fixture represents food only in main inventory.
        boolean canEatFromInventory(float health, int hunger) {
            boolean lowHealth = health <= (Double) healthThreshold.get();
            boolean lowHunger = hunger <= (Integer) hungerThreshold.get();
            boolean trigger = switch ((Mode) thresholdMode.get()) {
                case Health -> lowHealth;
                case Hunger -> lowHunger;
                case Any -> lowHealth || lowHunger;
                case Both -> lowHealth && lowHunger;
            };
            return trigger && hunger < 20 && (Boolean) searchInventory.get();
        }
    }
    @AfterEach void release() { GuardFoodLease.release(); }
    private Path backup() { return dir.resolve("lease.json"); }
    private void recovery(Module m, boolean owned, float health) {
        GuardFoodLease.tickRecovery(m, backup(), owned, health, 20);
    }
    private void assertOriginal(Module m) {
        assertEquals(Mode.Both, m.thresholdMode.get());
        assertEquals(10.0, m.healthThreshold.get());
        assertEquals(16, m.hungerThreshold.get());
        assertEquals(false, m.searchInventory.get());
    }

    @Test void ownedWorkLetsMeteorKeepTheUsersFoodSettings() {
        var m = new Module();
        GuardFoodLease.acquire(m, backup());
        recovery(m, false, 15.327734f);
        recovery(m, true, 20);
        assertOriginal(m);
        assertEquals(0, m.thresholdMode.writes);
        assertEquals(0, m.hungerThreshold.writes);
        assertEquals(0, m.searchInventory.writes);
        assertFalse(Files.exists(backup()));
        GuardFoodLease.release();
        assertOriginal(m);
    }

    @Test void recoveryMakesHunger17AndInventoryFoodEligibleWithoutChangingFoodChoices() throws Exception {
        var m = new Module();
        m.thresholdMode.value = Mode.Any; // Exact incident: health trigger 10, hunger trigger 16, inventory search off.
        Object blacklist = m.blacklist.get(), prioritise = m.prioritise.get();
        assertFalse(m.canEatFromInventory(15.327734f, 17));
        recovery(m, true, 15.327734f);
        assertTrue(m.canEatFromInventory(15.327734f, 17));
        assertEquals(Mode.Any, m.thresholdMode.get());
        assertEquals(19, m.hungerThreshold.get());
        assertEquals(true, m.searchInventory.get());
        assertEquals(10.0, m.healthThreshold.get());
        assertSame(blacklist, m.blacklist.get());
        assertSame(prioritise, m.prioritise.get());
        assertEquals(0, m.healthThreshold.writes);
        assertEquals(0, m.blacklist.writes);
        assertEquals(0, m.prioritise.writes);
        var record = JsonParser.parseString(Files.readString(backup())).getAsJsonObject();
        assertEquals(Set.of("hungerThreshold", "searchInventory"), record.keySet());
        assertEquals(16, record.getAsJsonObject("hungerThreshold").get("original").getAsInt());
        assertEquals(19, record.getAsJsonObject("hungerThreshold").get("written").getAsInt());
    }

    @Test void completeBackupExistsBeforeFirstSettingWrite() {
        var m = new Module();
        m.thresholdMode.onWrite = () -> {
            try {
                var record = JsonParser.parseString(Files.readString(backup())).getAsJsonObject();
                assertEquals(Set.of("thresholdMode", "hungerThreshold", "searchInventory"), record.keySet());
                assertEquals("Both", record.getAsJsonObject("thresholdMode").get("original").getAsString());
                assertEquals("Any", record.getAsJsonObject("thresholdMode").get("written").getAsString());
                assertEquals(16, record.getAsJsonObject("hungerThreshold").get("original").getAsInt());
                assertFalse(record.getAsJsonObject("searchInventory").get("original").getAsBoolean());
            } catch (Exception e) { throw new AssertionError(e); }
        };
        recovery(m, true, 15);
        m.thresholdMode.onWrite = null;
    }

    @Test void fullHealthRestoresExactOriginalSettingsAndDeletesBackup() {
        var m = new Module();
        recovery(m, true, 15);
        recovery(m, true, 19);
        assertEquals(19, m.hungerThreshold.get());
        assertTrue(Files.exists(backup()));
        recovery(m, true, 20);
        assertOriginal(m);
        assertFalse(Files.exists(backup()));
    }

    @Test void lossOfOwnedRecoveryAndDisarmBothRestore() {
        var m = new Module();
        recovery(m, true, 15);
        recovery(m, false, 15);
        assertOriginal(m);
        assertFalse(Files.exists(backup()));
        recovery(m, true, 15);
        GuardFoodLease.release();
        assertOriginal(m);
        assertFalse(Files.exists(backup()));
    }

    @Test void subsequentTicksDoNotReapplyOrRewriteTheBackup() throws Exception {
        var m = new Module();
        recovery(m, true, 15);
        var oldTime = FileTime.fromMillis(1);
        Files.setLastModifiedTime(backup(), oldTime);
        for (int i = 0; i < 40; i++) recovery(m, true, 18);
        assertEquals(1, m.thresholdMode.writes);
        assertEquals(1, m.hungerThreshold.writes);
        assertEquals(1, m.searchInventory.writes);
        assertEquals(oldTime, Files.getLastModifiedTime(backup()));
    }

    @Test void laterUserEditsAreNotOverwrittenDuringRecoveryOrOnRelease() {
        var m = new Module();
        recovery(m, true, 15);
        m.thresholdMode.set(Mode.Health);
        m.hungerThreshold.set(12);
        m.searchInventory.set(false);
        m.healthThreshold.set(17.0);
        m.blacklist.set(List.of("baked_potato"));
        recovery(m, true, 16);
        GuardFoodLease.release();
        assertEquals(Mode.Health, m.thresholdMode.get());
        assertEquals(12, m.hungerThreshold.get());
        assertEquals(false, m.searchInventory.get());
        assertEquals(17.0, m.healthThreshold.get());
        assertEquals(List.of("baked_potato"), m.blacklist.get());
        assertFalse(Files.exists(backup()));
    }

    @Test void rejectingTheSecondSettingRollsBackTheFirstAndDeletesBackup() {
        var m = new Module();
        m.hungerThreshold.rejected = 19;
        assertThrows(IllegalStateException.class, () -> recovery(m, true, 15));
        assertOriginal(m);
        assertEquals(0, m.searchInventory.writes);
        assertFalse(Files.exists(backup()));
        m.hungerThreshold.rejected = null;
        recovery(m, true, 15); // No repeated initialization after a failed attempt in the same recovery window.
        assertOriginal(m);
        recovery(m, false, 15);
        recovery(m, true, 15);
        assertEquals(19, m.hungerThreshold.get());
    }

    @Test void rejectedSettingThatMutatesBeforeReturningFalseIsAlsoRolledBack() {
        var m = new Module();
        m.searchInventory.rejected = true;
        m.searchInventory.rejectAfterMutation = true;
        assertThrows(IllegalStateException.class, () -> recovery(m, true, 15));
        assertOriginal(m);
        assertFalse(Files.exists(backup()));
    }

    @Test void backupFailureChangesNoSettingsAndIsNotRetriedEveryTick() throws Exception {
        var m = new Module();
        Path parent = dir.resolve("not-a-directory");
        Files.writeString(parent, "occupied");
        Path invalid = parent.resolve("lease.json");
        assertThrows(IllegalStateException.class,
            () -> GuardFoodLease.tickRecovery(m, invalid, true, 15, 20));
        assertOriginal(m);
        assertEquals(0, m.thresholdMode.writes);
        recovery(m, true, 15);
        assertOriginal(m);
        assertFalse(Files.exists(backup()));
    }

    @Test void failedRestoreRetainsBackupAndCanBeRetriedWithoutOverwritingOtherSettings() {
        var m = new Module();
        recovery(m, true, 15);
        m.hungerThreshold.rejected = 16;
        assertThrows(IllegalStateException.class, GuardFoodLease::release);
        assertTrue(Files.exists(backup()));
        assertEquals(Mode.Both, m.thresholdMode.get());
        assertEquals(19, m.hungerThreshold.get());
        assertEquals(false, m.searchInventory.get());
        m.hungerThreshold.rejected = null;
        GuardFoodLease.release();
        assertOriginal(m);
        assertFalse(Files.exists(backup()));
    }

    @Test void generatedCrashReceiptRestoresSettingsButPreservesLaterUserEdits() throws Exception {
        var m = new Module();
        recovery(m, true, 15);
        String receipt = Files.readString(backup());
        GuardFoodLease.release();
        Files.writeString(backup(), receipt);
        var loaded = new Module();
        loaded.thresholdMode.value = Mode.Any;
        loaded.hungerThreshold.value = 19;
        loaded.searchInventory.value = true;
        loaded.healthThreshold.value = 17.0;
        loaded.hungerThreshold.value = 13; // Persisted later manual edit survives a crash too.
        GuardFoodLease.recover(loaded, backup());
        assertEquals(Mode.Both, loaded.thresholdMode.get());
        assertEquals(13, loaded.hungerThreshold.get());
        assertEquals(false, loaded.searchInventory.get());
        assertEquals(17.0, loaded.healthThreshold.get());
        assertFalse(Files.exists(backup()));
    }

    @Test void oldReceiptStillRecoversTemporaryValuesSavedBeforeThisVersion() throws Exception {
        Files.writeString(backup(), "{\"thresholdMode\":{\"original\":\"Both\",\"written\":\"Any\"},"
            + "\"healthThreshold\":{\"original\":10.0,\"written\":19.0},"
            + "\"hungerThreshold\":{\"original\":16,\"written\":19},"
            + "\"searchInventory\":{\"original\":false,\"written\":true}}");
        var loaded = new Module();
        loaded.thresholdMode.value = Mode.Any;
        loaded.healthThreshold.value = 19.0;
        loaded.hungerThreshold.value = 19;
        loaded.searchInventory.value = true;
        GuardFoodLease.recover(loaded, backup());
        assertOriginal(loaded);
        assertFalse(Files.exists(backup()));
    }
}
