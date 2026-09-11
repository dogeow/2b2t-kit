package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaSurveyTest {
	@Test void scanOfThirtyCubeIsBoundedAndFinishesInLessThanTwoSeconds() {
		var survey = new BorerAreaSurvey(BlockPos.ZERO, new BlockPos(29, 29, 29));
		var reads = new AtomicInteger();
		BorerAreaPlan.World world = p -> { reads.incrementAndGet(); return BorerAreaPlan.Cell.AIR; };
		int ticks = 0;
		boolean done;
		do {
			reads.set(0); done = survey.step(world); ticks++;
			assertTrue(reads.get() <= BorerAreaSurvey.READS_PER_TICK);
			assertTrue(ticks < 40);
		} while (!done);
		assertEquals(54000, survey.progress());
		for (int i = 0; i < 900; i++) assertTrue(survey.clear(i));
	}
	@Test void twoClearConfirmationsCannotOccurInTheSameTick() {
		var survey = new BorerAreaSurvey(BlockPos.ZERO, BlockPos.ZERO);
		assertFalse(survey.step(p -> BorerAreaPlan.Cell.AIR));
		assertTrue(survey.step(p -> BorerAreaPlan.Cell.SOLID));
		assertFalse(survey.clear(0));
	}
	@Test void liquidProtectedAndUnloadedAreNotAir() {
		for (var cell : new BorerAreaPlan.Cell[]{BorerAreaPlan.Cell.LIQUID, BorerAreaPlan.Cell.BEDROCK, BorerAreaPlan.Cell.PROTECTED, BorerAreaPlan.Cell.UNLOADED}) {
			var survey = new BorerAreaSurvey(BlockPos.ZERO, BlockPos.ZERO);
			survey.step(p -> cell); survey.step(p -> cell);
			assertFalse(survey.clear(0));
			assertEquals(cell != BorerAreaPlan.Cell.UNLOADED, survey.loaded(0));
		}
	}
	@Test void bedrockSurfaceNeedsTwoMatchingObservationsWithNoStoneAbove() {
		var survey = new BorerAreaSurvey(BlockPos.ZERO, new BlockPos(0, 4, 0));
		BorerAreaPlan.World bedrock = p -> p.getY() == 1 ? BorerAreaPlan.Cell.BEDROCK : BorerAreaPlan.Cell.AIR;
		survey.step(bedrock); assertNull(survey.bedrockSurface(0));
		survey.step(bedrock); assertEquals(1, survey.bedrockSurface(0)); assertFalse(survey.clear(0));
		var changed = new BorerAreaSurvey(BlockPos.ZERO, new BlockPos(0, 4, 0));
		changed.step(bedrock);
		changed.step(p -> p.getY() == 3 ? BorerAreaPlan.Cell.SOLID : bedrock.cell(p));
		assertNull(changed.bedrockSurface(0));
	}
}
