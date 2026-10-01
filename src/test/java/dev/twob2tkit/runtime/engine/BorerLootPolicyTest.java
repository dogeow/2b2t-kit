package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：钻石掉坑里要捡完，不要背包多几颗就收工，也不要站在坑沿放弃。
 * 来源：2026-08-21 382842 -47 311314，4→6 后坑里还剩 ×3；
 * 随后 382826.875,-49 人在 -48，按 W 80 tick 仍放弃；
 * 2026-08-25 13624 -53 9217，19→21 remaining=false，14 tick 收工，1.6 格外还掉着。
 */
final class BorerLootPolicyTest {
	@Test void highDropCannotTriggerAJumpAgainstABlockedBodyOrMissingFooting() {
		assertFalse(BorerLootPolicy.groundHop(true, false, true, true, true));
		assertFalse(BorerLootPolicy.groundHop(true, true, false, true, true));
		assertFalse(BorerLootPolicy.groundHop(true, true, true, false, true));
		assertFalse(BorerLootPolicy.groundHop(false, true, true, true, true));
		assertTrue(BorerLootPolicy.groundHop(true, true, true, true, true));
	}
	@Test void failedLootHopsAreBoundedEvenAcrossBlockEdgesAndAirborneOscillation() {
		var hops = new BorerLootPolicy.HopControl();
		assertTrue(hops.press(0, 95113.30, 68, 99601.46, true));
		assertFalse(hops.press(1, 95113.30, 69.25, 99601.46, false));
		assertFalse(hops.press(11, 95112.99, 68, 99601.46, true));
		assertTrue(hops.press(12, 95112.99, 68, 99601.46, true));
		for (int tick = 13; tick < 400; tick++) {
			boolean grounded = tick % 12 == 0;
			assertFalse(hops.press(tick, 95113.05, grounded ? 68 : 69.25, 99601.46, grounded));
		}
	}
	@Test void actualClearanceOrSuccessfulLandingAllowsTheNextLootHop() {
		var hops = new BorerLootPolicy.HopControl();
		assertTrue(hops.press(0, 0, 68, 0, true));
		assertTrue(hops.press(12, 0, 68, 0, true));
		assertFalse(hops.press(24, 0, 68, 0, true));
		hops.reset(); // a confirmed clearance, inventory pickup or route waypoint
		assertTrue(hops.press(25, 0, 68, 0, true));
		assertTrue(hops.press(26, 0, 69, 0, true)); // landed on the raised support
		assertTrue(hops.press(27, 1, 69, 0, true)); // genuinely advanced to the next step
	}
	@Test void hopFootprintSeesTheNextColumnsCeilingAndPreservesAOneBlockStep() {
		var feet = new net.minecraft.world.phys.AABB(95113.0, 68, 99601.16, 95113.6, 69.8, 99601.76);
		var hop = BorerLoot.hopBody(feet, 90);
		assertTrue(hop.intersects(new net.minecraft.world.phys.AABB(95112, 70, 99601, 95113, 71, 99602)),
			"A clear launch column cannot conceal the destination ceiling that caused the real loop");
		assertFalse(hop.intersects(new net.minecraft.world.phys.AABB(95112, 68, 99601, 95113, 69, 99602)),
			"The existing one-block step remains a foothold, not a clearance target");
	}
	@Test void realProgressKeepsACollectionAlivePastTheOldTenSecondLimit() {
		var progress = new BorerLootPolicy.Progress();
		for (int tick = 0; tick < 1200; tick++) assertFalse(progress.tick(20, false, tick % 40 == 0, false));
	}
	@Test void detourWaypointsCountAsProgressEvenWhenStraightLineDistanceIncreases() {
		var progress = new BorerLootPolicy.Progress();
		for (int tick = 0; tick < 600; tick++) assertFalse(progress.tick(5 + tick * .01, false, false, tick % 25 == 0));
	}
	@Test void jumpingWithoutApproachingDoesNotResetStallForever() {
		var progress = new BorerLootPolicy.Progress();
		assertFalse(progress.tick(2, false, false, false));
		for (int tick = 0; tick < 159; tick++) assertFalse(progress.tick(2 + tick % 2 * .3, false, false, false));
		assertTrue(progress.tick(2, false, false, false));
	}
	@Test void theoreticalPickupBoxOnlyWaitsBrieflyBeforeMovingCloser() {
		assertTrue(BorerLootPolicy.waitInsidePickupBox(19));
		assertFalse(BorerLootPolicy.waitInsidePickupBox(20));
		assertFalse(BorerLootPolicy.safeHop(true, true));
		assertTrue(BorerLootPolicy.safeHop(true, false));
	}
	@Test void silkTouchOreAndActualGemNeedDifferentInventorySpace() {
		assertFalse(BorerLootPolicy.canStackDrop(false, 12, 64));
		assertFalse(BorerLootPolicy.canStackDrop(true, 64, 64));
		assertTrue(BorerLootPolicy.canStackDrop(true, 12, 64));
	}
	@Test void targetDoesNotSwitchDueToTinyDistanceOscillation() {
		assertTrue(BorerLootPolicy.keepItemTarget(3.5, 3.0));
		assertFalse(BorerLootPolicy.keepItemTarget(8, 3));
	}
	@Test void fallingDropsStayInSearchRangeAndXpModesRemainRespected() {
		assertTrue(BorerLootPolicy.verticalSearchRadius(true) >= 48);
		assertFalse(BorerLootPolicy.trackDrop(true, false, true, false));
		assertFalse(BorerLootPolicy.trackDrop(false, true, false, true));
		assertTrue(BorerLootPolicy.trackDrop(true, true, false, false));
	}
	@Test
	void partialPickupDoesNotFinishWhileDropsRemain() {
		assertFalse(BorerLootPolicy.finishOnInventoryIncrease(true, false));
		assertFalse(BorerLootPolicy.finishOnInventoryIncrease(true, true));
		assertFalse(BorerLootPolicy.finishOnInventoryIncrease(false, false));
		assertTrue(BorerLootPolicy.finishOnInventoryIncrease(false, true));
		assertTrue(BorerLootPolicy.inventoryProgressResetsStuck(true, true));
		assertFalse(BorerLootPolicy.inventoryProgressResetsStuck(true, false));
		assertFalse(BorerLootPolicy.inventoryProgressResetsStuck(false, true));
	}

	@Test
	void fortuneExtrasWaitForSpawnWindow() {
		assertFalse(BorerLootPolicy.finishWhenMissing(false, 0, false));
		assertFalse(BorerLootPolicy.finishWhenMissing(true, 4, false));
		assertFalse(BorerLootPolicy.finishWhenMissing(true, 3, true));
		assertTrue(BorerLootPolicy.finishWhenMissing(false, 0, true));
		assertTrue(BorerLootPolicy.finishWhenMissing(true, 4, true));
	}

	@Test
	void alreadyPickedDoesNotWaitTheFullFirstSpawnWindow() {
		assertFalse(BorerLootPolicy.spawnWaitElapsed(true, 7));
		assertTrue(BorerLootPolicy.spawnWaitElapsed(true, 8));
		assertFalse(BorerLootPolicy.spawnWaitElapsed(false, 39));
		assertTrue(BorerLootPolicy.spawnWaitElapsed(false, 40));
		assertFalse(BorerLootPolicy.overlayWaitForMore(true, false, true));
		assertTrue(BorerLootPolicy.overlayWaitForMore(true, false, false));
		assertFalse(BorerLootPolicy.overlayWaitForMore(true, true, false));
	}

	@Test
	void visibleDropsAreCollectedBeforeAdjacentOre() {
		assertTrue(BorerLootPolicy.collectVisibleBeforeAdjacent(true));
		assertFalse(BorerLootPolicy.collectVisibleBeforeAdjacent(false));
	}

	@Test
	void oneBlockPitIsOutsideVanillaPickup() {
		assertFalse(BorerLootPolicy.inVanillaPickupRange(0.002, -1.0, -0.89));
		assertFalse(BorerLootPolicy.inVanillaPickupRange(0.0, -1.0, 0.0));
		assertFalse(BorerLootPolicy.inVanillaPickupRange(1.485, 0.247, 0.227));
		assertTrue(BorerLootPolicy.inVanillaPickupRange(1.2, 0.2, 0.2));
		assertTrue(BorerLootPolicy.inVanillaPickupRange(0.4, 0.0, 0.4));
		assertTrue(BorerLootPolicy.inVanillaPickupRange(0.2, 0.2, 0.2));
	}

	@Test
	void safePitIsWalkedInto() {
		assertTrue(BorerLootPolicy.shouldWalkIntoLootDrop(-1.0, true));
		assertTrue(BorerLootPolicy.shouldWalkIntoLootDrop(-0.3, true));
		assertFalse(BorerLootPolicy.shouldWalkIntoLootDrop(-1.0, false));
		assertFalse(BorerLootPolicy.shouldWalkIntoLootDrop(0.2, true));
		assertFalse(BorerLootPolicy.shouldWalkIntoLootDrop(-0.1, true));
	}

	@Test
	void rimOfSafePitHopsOff() {
		assertTrue(BorerLootPolicy.shouldHopOffRim(true, true, 0.89, false));
		assertTrue(BorerLootPolicy.shouldHopOffRim(true, true, 1.25, false));
		assertFalse(BorerLootPolicy.shouldHopOffRim(false, true, 0.89, false));
		assertFalse(BorerLootPolicy.shouldHopOffRim(true, false, 0.89, false));
		assertFalse(BorerLootPolicy.shouldHopOffRim(true, true, 0.2, true));
		assertFalse(BorerLootPolicy.shouldHopOffRim(true, true, 3.0, false));
	}

	@Test
	void oneByOnePitMinesHeadToOpenOneByTwo() {
		assertTrue(BorerLootPolicy.shouldMineHeadToEnterLootDrop(-1.0, true, true));
		assertFalse(BorerLootPolicy.shouldMineHeadToEnterLootDrop(-1.0, true, false));
		assertFalse(BorerLootPolicy.shouldMineHeadToEnterLootDrop(-1.0, false, true));
		assertFalse(BorerLootPolicy.shouldMineHeadToEnterLootDrop(0.0, true, true));
	}

	@Test
	void safeDropIsPreferredOverMiningObstruction() {
		assertTrue(BorerLootPolicy.preferDropOverMining(true, false, -1.0));
		assertFalse(BorerLootPolicy.preferDropOverMining(true, true, -1.0));
		assertFalse(BorerLootPolicy.preferDropOverMining(false, false, -1.0));
		assertFalse(BorerLootPolicy.preferDropOverMining(true, false, 0.25));
		assertFalse(BorerLootPolicy.preferDropOverMining(true, false, 1.0));
	}
}
