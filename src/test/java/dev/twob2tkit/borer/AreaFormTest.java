package dev.twob2tkit.borer;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class AreaFormTest {
	@Test void dimensionsProduceExactlyThirtyByThirtyByThirty() {
		var r = AreaForm.fromSize(new BlockPos(100, 64, 200), 30, 30, 30);
		assertEquals(new BlockPos(129, 35, 229), r.b());
	}
	@Test void validatesBothCornersAndRejectsPartialOrOversizeDrafts() {
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parse("100 64 200", "bad", -64, 320));
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parse("100 64 200 extra", "120 30 220", -64, 320));
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parse("100 64 200", "200 30 220", -64, 320));
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parse("100 400 200", "120 30 220", -64, 320));
		assertEquals(new BlockPos(100, 64, 200), AreaForm.parse("100,64,200", "129 35 229", -64, 320).a());
	}
	@Test void refusesAnAmbiguousOneLayerPreset() {
		assertThrows(IllegalArgumentException.class, () -> AreaForm.fromSize(BlockPos.ZERO, 30, 30, 1));
	}
	@Test void acceptsEitherCornerAloneOnlyForDraftSaving() {
		var a = AreaForm.parseDraft("760981 76 797823", "", -64, 320);
		assertEquals(new BlockPos(760981, 76, 797823), a.a()); assertNull(a.b());
		var b = AreaForm.parseDraft(null, "760981 76 797823", -64, 320);
		assertNull(b.a()); assertEquals(a.a(), b.b());
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parse("760981 76 797823", "", -64, 320));
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parse("", "760981 76 797823", -64, 320));
	}
	@Test void incompleteDraftStillValidatesEverySuppliedCoordinate() {
		for (String bad : new String[]{"1 64", "1 64 2 extra", "a 64 2", "1 -65 2", "1 319 2"}) {
			assertThrows(IllegalArgumentException.class, () -> AreaForm.parseDraft(bad, "", -64, 320));
			assertThrows(IllegalArgumentException.class, () -> AreaForm.parseDraft("", bad, -64, 320));
		}
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parseDraft("", "", -64, 320));
	}
	@Test void completedDraftKeepsFullAreaSpanValidation() {
		assertThrows(IllegalArgumentException.class, () -> AreaForm.parseDraft("0 64 0", "64 0 1", -64, 320));
		assertEquals(AreaForm.parse("0 64 0", "63 0 63", -64, 320), AreaForm.parseDraft("0 64 0", "63 0 63", -64, 320));
	}
}
