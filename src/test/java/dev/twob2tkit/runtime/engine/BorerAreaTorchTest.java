package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BorerAreaTorchTest {
	@Test void onlyTriesWhenDimAndTorchesAvailable() {
		assertTrue(BorerAreaTorch.needsLight(0, true));
		assertTrue(BorerAreaTorch.needsLight(7, true));
		assertFalse(BorerAreaTorch.needsLight(0, false));
		assertFalse(BorerAreaTorch.needsLight(12, true));
	}
}
