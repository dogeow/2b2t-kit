package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.io.IOException;
import static org.junit.jupiter.api.Assertions.*;

class SceneryProgressTest {
	@TempDir Path temp;
	@Test void resumeKeepsOriginalCentreRadiusAndOnlyCommittedChunks() throws Exception {
		var plan = new SceneryCoverage(-27.25, 31.8, 256); var first = plan.next();
		plan.accepted(first.x(), first.z()); plan.commitBatch(); var second = plan.next(); plan.accepted(second.x(), second.z());
		var file = temp.resolve("progress.json"); SceneryProgress.write(file, "server|world", "voxy-cache", plan);
		var resumed = SceneryProgress.read(file, "server|world", "voxy-cache");
		assertEquals(-27.25, resumed.centreX); assertEquals(256, resumed.radius); assertEquals(1, resumed.confirmed()); assertEquals(second, resumed.next());
		assertThrows(IOException.class, () -> SceneryProgress.read(file, "other|world", "voxy-cache"));
		assertThrows(IOException.class, () -> SceneryProgress.read(file, "server|nether", "voxy-cache"));
		assertThrows(IOException.class, () -> SceneryProgress.read(file, "server|world", "other-cache"));
	}
	@Test void missingOrMalformedProgressIsReportedWithoutOverwritingIt() throws Exception {
		var file = temp.resolve("progress.json");
		assertThrows(IOException.class, () -> SceneryProgress.read(file, "a", "b"));
		Files.writeString(file, "bad["); assertThrows(IOException.class, () -> SceneryProgress.read(file, "a", "b"));
		assertEquals("bad[", Files.readString(file));
	}
}
