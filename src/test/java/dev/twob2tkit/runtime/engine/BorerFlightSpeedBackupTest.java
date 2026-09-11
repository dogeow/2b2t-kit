package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import static org.junit.jupiter.api.Assertions.*;

class BorerFlightSpeedBackupTest {
	@TempDir Path temp;
	@Test void journalCoversInterruptionBeforeAndAfterSettingWrite() throws Exception {
		var backup = new BorerFlightSpeedBackup(temp.resolve("speed.bak"));
		backup.beforeWrite(0.37, 0.0, 0.02);
		assertEquals(0.37, backup.read().restore(0));
		assertEquals(0.37, backup.read().restore(0.02));
		assertEquals(0.5, backup.read().restore(0.5));
		backup.clear(); assertNull(backup.read());
	}
	@Test void corruptBackupIsNotDeletedOrApplied() throws Exception {
		Path path = temp.resolve("speed.bak");
		Files.writeString(path, "NaN 0 0.02");
		assertThrows(java.io.IOException.class, () -> new BorerFlightSpeedBackup(path).read());
		assertEquals("NaN 0 0.02", Files.readString(path));
	}
}
