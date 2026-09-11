package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static dev.twob2tkit.runtime.engine.BorerWaterSealPolicy.Action.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerWaterSealPolicyTest {
	@Test void sideSealNeverReplacesTheBarrierOrPlayerColumn() {
		BlockPos barrier = new BlockPos(10, 2, 20), body = new BlockPos(10, 1, 19);
		assertTrue(BorerWaterSealPolicy.sideCell(barrier, barrier.east(), body));
		assertFalse(BorerWaterSealPolicy.sideCell(barrier, barrier, body));
		assertFalse(BorerWaterSealPolicy.sideCell(barrier, barrier.above(), body));
		assertFalse(BorerWaterSealPolicy.sideCell(barrier, barrier.north(), body));
	}
	@Test void placementWaitsForStableObservedStoneInsteadOfAssumingSuccess() {
		var p = new BorerWaterSealPolicy();
		assertEquals(PLACE, p.step(true, false, true, true));
		for (int tick = 2; tick < 12; tick++) assertEquals(WAIT, p.step(false, true, true, true));
		assertEquals(DONE, p.step(false, true, true, true));
		assertEquals(1, p.attempts());
	}
	@Test void aPredictionThatTurnsBackIntoWaterDoesNotCountAsASeal() {
		var p = new BorerWaterSealPolicy(); p.step(true, false, true, true);
		for (int tick = 0; tick < 3; tick++) assertEquals(WAIT, p.step(false, true, true, true));
		for (int tick = 5; tick <= 20; tick++) assertEquals(WAIT, p.step(true, false, true, true));
		for (int tick = 0; tick < 5; tick++) assertEquals(WAIT, p.step(false, true, true, true));
		assertEquals(DONE, p.step(false, true, true, true));
	}
	@Test void unconfirmedPlacementRetriesAreBounded() {
		var p = new BorerWaterSealPolicy(); int placements = 0;
		for (int tick = 1; tick <= 90; tick++) {
			var action = p.step(true, false, true, true);
			if (action == PLACE) placements++;
			else assertEquals(WAIT, action);
		}
		assertEquals(3, placements);
		assertEquals(FAIL, p.step(true, false, true, true));
	}
	@Test void missingBlocksOutOfReachAndUnexpectedReplacementFailSafely() {
		assertEquals(FAIL, new BorerWaterSealPolicy().step(true, false, true, false));
		assertEquals(FAIL, new BorerWaterSealPolicy().step(true, false, false, true));
		assertEquals(FAIL, new BorerWaterSealPolicy().step(false, false, true, true));
	}
}
