package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.BooleanSupplier;

import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Action;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Cell;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Command;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Phase;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Pose;
import static org.junit.jupiter.api.Assertions.*;

/** Executes the production step against a voxel world and independent, collision-checked movement. */
final class BorerAreaPlanTest {

	@Test
	void thirtyCubeIsMinedTopToBottomAndReturnsBeforeEveryAdjacentColumnFromAllFourCorners() {
		BlockPos min = new BlockPos(-32, 20, 101);
		BlockPos max = min.offset(29, 29, 29);
		for (int startX : new int[]{min.getX(), max.getX()}) {
			for (int startZ : new int[]{min.getZ(), max.getZ()}) {
				Simulation sim = new Simulation(min, max, true,
					new Pose(startX + 0.5, max.getY() + 1.25, startZ + 0.5, 0, 0, 0));
				sim.horizontalMultiplier = startX == min.getX() ? 10 : 15;
				sim.finish();
				assertEquals(900, sim.plan.completed());
				assertEquals(900, sim.enteredColumns.size());
				assertEquals(new BlockPos(startX, 0, startZ), sim.enteredColumns.getFirst());
				assertEquals(27_000, sim.world.broken.size());
				assertEquals(27_000, new HashSet<>(sim.world.broken).size());
				for (int columnIndex = 0; columnIndex < 900; columnIndex++) {
					BlockPos column = sim.enteredColumns.get(columnIndex);
					if (columnIndex > 0) assertEquals(1, sim.enteredColumns.get(columnIndex - 1).distManhattan(column));
					for (int layer = 0; layer < 30; layer++) {
						assertEquals(new BlockPos(column.getX(), max.getY() - layer, column.getZ()),
							sim.world.broken.get(columnIndex * 30 + layer));
					}
				}
				assertEquals(900, sim.bottomVisits.size(), "Even the final shaft must physically reach the bottom");
				assertEquals(900, sim.returnedColumns.size(), "The final shaft also returns before DONE");
				assertEquals(0, sim.rejectedMoves, "No command may move the body through uncleared blocks");
				assertTrue(sim.pose.y() >= max.getY() + 1.0);
			}
		}
	}

	@Test
	void naturalCavesStillReachTheBottomButCompletelyEmptyColumnsAreSkipped() {
		BlockPos min = new BlockPos(2, -15, -3);
		BlockPos max = min.offset(2, 29, 1);
		Simulation sim = new Simulation(min, max, true);
		Set<BlockPos> expected = new HashSet<>();
		for (int x = min.getX(); x <= max.getX(); x++) {
			for (int z = min.getZ(); z <= max.getZ(); z++) {
				for (int y = min.getY(); y <= max.getY(); y++) {
					BlockPos block = new BlockPos(x, y, z);
					boolean empty = (x == min.getX() && z == min.getZ()) || y % 4 == 0 || (y > -4 && y < 5);
					if (empty) sim.world.set(block, Cell.AIR);
					else expected.add(block);
				}
			}
		}
		sim.finish();
		assertEquals(expected, new HashSet<>(sim.world.broken));
		assertEquals(5, sim.bottomVisits.size());
		assertEquals(5, sim.returnedColumns.size());
		assertFalse(sim.enteredColumns.contains(new BlockPos(min.getX(), 0, min.getZ())));
		assertEquals(0, sim.rejectedMoves);
	}

	@Test
	void delayedServerBreakIsNotAssumedCompleteFromRepeatedMiningCommands() {
		Simulation sim = new Simulation(new BlockPos(0, 7, 0), new BlockPos(0, 9, 0), true);
		sim.world.breakDelay = 7;
		sim.until(() -> sim.world.attempts.values().stream().anyMatch(n -> n >= 4));
		assertEquals(0, sim.plan.completed());
		assertEquals(9, sim.plan.cursorY());
		assertEquals(Cell.SOLID, sim.world.cell(new BlockPos(0, 9, 0)));
		sim.finish();
		assertEquals(List.of(new BlockPos(0, 9, 0), new BlockPos(0, 8, 0), new BlockPos(0, 7, 0)), sim.world.broken);
		assertTrue(sim.world.attempts.values().stream().allMatch(n -> n >= 7));
		assertEquals(1, sim.returnedColumns.size());
	}

	@Test
	void aSingleGhostAirSampleIsResetWhenTheServerRestoresTheBlock() {
		BlockPos block = new BlockPos(4, 12, -2);
		Simulation sim = new Simulation(block, block, true);
		sim.until(() -> sim.plan.phase() == Phase.DIG);
		sim.world.breakDelay = 100;
		sim.world.set(block, Cell.AIR);
		sim.tick();
		assertEquals(12, sim.plan.cursorY());
		sim.world.set(block, Cell.SOLID);
		sim.tick();
		assertEquals(12, sim.plan.cursorY());
		assertEquals(0, sim.plan.completed());
		sim.world.set(block, Cell.AIR);
		sim.tick();
		assertEquals(12, sim.plan.cursorY(), "A new pair of AIR observations is required");
		sim.tick();
		assertEquals(11, sim.plan.cursorY());
		sim.finish();
	}

	@Test
	void aRefilledPreviouslyConfirmedLayerIsRevisitedBeforeCompletion() {
		BlockPos min = new BlockPos(0, 10, 0);
		BlockPos top = new BlockPos(0, 12, 0);
		Simulation sim = new Simulation(min, top, true);
		sim.until(() -> sim.plan.phase() == Phase.DIG && sim.plan.cursorY() == 11);
		sim.world.set(top, Cell.SOLID);
		Command retry = sim.tick();
		assertEquals(12, sim.plan.cursorY());
		assertNotEquals(Action.DONE, retry.action());
		assertEquals(0, sim.plan.completed());
		sim.finish();
		assertEquals(2, sim.world.broken.stream().filter(top::equals).count());
		assertEquals(1, sim.plan.completed());
	}

	@Test
	void unloadedCurrentLayerWaitsWithoutCompletionAndResumesWhenLoaded() {
		BlockPos target = new BlockPos(-5, 8, 6);
		Simulation sim = new Simulation(target, target.above(2), true);
		sim.until(() -> sim.plan.phase() == Phase.DIG);
		sim.world.set(target, Cell.UNLOADED);
		sim.until(() -> sim.plan.phase() == Phase.DIG && sim.plan.cursorY() == target.getY());
		for (int tick = 0; tick < 20; tick++) {
			assertEquals(Action.WAIT, sim.tick().action());
			assertEquals(0, sim.plan.completed());
			assertEquals(target.getY(), sim.plan.cursorY());
		}
		sim.world.set(target, Cell.SOLID);
		sim.finish();
		assertTrue(sim.world.broken.contains(target));
	}

	@Test
	void unloadedPathDoesNotCauseBlindMovement() {
		BlockPos min = new BlockPos(0, 3, 0);
		BlockPos max = min.offset(1, 2, 0);
		Simulation sim = new Simulation(min, max, true,
			new Pose(-0.5, 6.25, 0.5, 0, 0, 0));
		BlockPos path = new BlockPos(0, 6, 0);
		sim.world.set(path, Cell.UNLOADED);
		sim.until(() -> sim.plan.phase() == Phase.TRANSFER);
		for (int tick = 0; tick < 6; tick++) sim.tick();
		Pose parked = sim.pose;
		for (int tick = 0; tick < 10; tick++) {
			assertEquals(Action.WAIT, sim.tick().action());
			assertEquals(parked, sim.pose);
			assertEquals(0, sim.plan.completed());
		}
		sim.world.set(path, Cell.AIR);
		sim.finish();
	}

	@Test
	void liquidsAndProtectedBlocksBlockWithoutCountingOrSkippingTheColumn() {
		for (Cell obstacle : new Cell[]{Cell.PROTECTED}) {
			BlockPos bottom = new BlockPos(3, 8, 7);
			Simulation sim = new Simulation(bottom, bottom.offset(1, 2, 0), true);
			sim.world.set(bottom, obstacle);
			sim.until(() -> sim.plan.phase() == Phase.BLOCKED);
			assertEquals(0, sim.plan.completed());
			assertEquals(1, sim.enteredColumns.size());
			assertFalse(sim.world.broken.contains(bottom));
			Pose parked = sim.pose;
			for (int tick = 0; tick < 5; tick++) assertEquals(Action.BLOCKED, sim.tick().action());
			assertEquals(parked, sim.pose);
			assertEquals(0, sim.plan.completed());
		}
	}

	@Test
	void driftIsCorrectedBeforeMiningOrDescendingAndMomentumMustSettle() {
		BlockPos min = new BlockPos(0, 8, 0);
		Simulation sim = new Simulation(min, min.above(2), true);
		sim.until(() -> sim.plan.phase() == Phase.DIG);
		sim.pose = new Pose(0.66, sim.pose.y(), 0.34, 0.12, 0, -0.12);
		assertEquals(Action.X, sim.tick().action());
		boolean correctedZ = false;
		for (int tick = 0; tick < 30 && (!sim.pose.settled()
			|| Math.abs(sim.pose.x() - 0.5) > BorerAreaPlan.CENTER
			|| Math.abs(sim.pose.z() - 0.5) > BorerAreaPlan.CENTER); tick++) {
			Command command = sim.tick();
			correctedZ |= command.action() == Action.Z;
			assertNotEquals(Action.MINE, command.action());
		}
		assertTrue(correctedZ);
		assertTrue(sim.pose.settled());
		assertTrue(Math.abs(sim.pose.x() - 0.5) <= BorerAreaPlan.CENTER);
		assertTrue(Math.abs(sim.pose.z() - 0.5) <= BorerAreaPlan.CENTER);
		assertTrue(sim.world.broken.isEmpty());
		sim.finish();
		assertEquals(3, sim.world.broken.size());
		assertEquals(0, sim.rejectedMoves);
	}

	@Test
	void heightDriftDuringTransferIsRepairedBeforeHorizontalMovement() {
		BlockPos min = new BlockPos(0, 5, 0);
		Simulation sim = new Simulation(min, min.offset(1, 2, 0), true);
		sim.until(() -> sim.plan.phase() == Phase.TRANSFER && sim.plan.completed() == 1);
		BlockPos departure = sim.plan.column();
		sim.pose = new Pose(sim.pose.x(), sim.pose.y() - 0.35, sim.pose.z(), 0, 0, 0);
		assertEquals(Action.UP, sim.tick().action());
		assertEquals(departure, sim.plan.column());
		assertEquals(departure.getX() + 0.5, sim.pose.x());
		assertEquals(departure.getZ() + 0.5, sim.pose.z());
		sim.finish();
	}

	@Test
	void theLastColumnIsNotDoneAtTheBottomButOnlyAfterReturningToTheTop() {
		BlockPos min = new BlockPos(2, -6, 9);
		Simulation sim = new Simulation(min, min.above(3), true);
		sim.until(() -> sim.plan.completed() == 1);
		assertEquals(Phase.RETURN, sim.plan.phase());
		assertTrue(sim.pose.y() < min.getY() + 1);
		assertNull(sim.plan.pending());
		Command firstReturn = sim.tick();
		assertEquals(Action.WAIT, firstReturn.action(), "First choose the return height without moving");
		firstReturn = sim.tick();
		assertEquals(Action.UP, firstReturn.action());
		sim.finish();
		assertEquals(Phase.DONE, sim.plan.phase());
		assertEquals(1, sim.returnedColumns.size());
		assertTrue(Math.abs(sim.pose.y() - sim.plan.transferY()) <= BorerAreaPlan.HEIGHT);
		assertEquals(Action.DONE, sim.tick().action(), "Completion is stable across repeated ticks");
	}

	@Test
	void negativeSingleRowAndSingleColumnAreasDoNotLoseOrRepeatShafts() {
		for (BlockPos size : List.of(new BlockPos(0, 0, 0), new BlockPos(4, 2, 0), new BlockPos(0, 2, 4))) {
			BlockPos min = new BlockPos(-8, -32, -11);
			Simulation sim = new Simulation(min, min.offset(size), true);
			sim.finish();
			int columns = (size.getX() + 1) * (size.getZ() + 1);
			assertEquals(columns, sim.plan.completed());
			assertEquals(columns * (size.getY() + 1), sim.world.broken.size());
		}
	}

	@Test
	void aHighOutsideStartTransfersAtItsSafeAltitudeAndOnlyThenLowersIntoTheFirstShaft() {
		BlockPos min = new BlockPos(0, 5, 0);
		BlockPos max = min.offset(1, 2, 1);
		Simulation sim = new Simulation(min, max, true, new Pose(-2.5, 20.5, 3.5, 0, 0, 0));
		BlockPos first = new BlockPos(0, 0, 1);
		int lowerCommands = 0;
		while (sim.plan.phase() != Phase.DIG && sim.ticks < 300) {
			Command command = sim.tick();
			if (command.action() == Action.DOWN) {
				lowerCommands++;
				assertEquals(first, sim.plan.column());
				assertTrue(Math.abs(sim.pose.x() - 0.5) <= BorerAreaPlan.CENTER);
				assertTrue(Math.abs(sim.pose.z() - 1.5) <= BorerAreaPlan.CENTER);
			}
			if (sim.plan.phase() == Phase.ENTER || sim.plan.phase() == Phase.TRANSFER) {
				assertEquals(20.5, sim.pose.y(), 1e-9, "Never descend outside the selected shaft");
			}
		}
		assertEquals(Phase.DIG, sim.plan.phase());
		assertTrue(lowerCommands > 0);
		assertEquals(first, sim.enteredColumns.getFirst());
		assertEquals(max.getY() + 1.25, sim.plan.transferY());
		sim.finish();
		assertEquals(12, sim.world.broken.size());
	}

	@Test
	void finalVerificationFindsAndMinesRefillInAnEarlierCompletedShaft() {
		BlockPos min = new BlockPos(0, 5, 0);
		Simulation sim = new Simulation(min, min.offset(1, 2, 0), true);
		sim.until(() -> sim.plan.phase() == Phase.DIG && sim.plan.completed() == 1);
		sim.world.set(min, Cell.SOLID);
		sim.finish();
		assertEquals(2, sim.world.broken.stream().filter(min::equals).count());
		assertEquals(Cell.AIR, sim.world.cell(min));
		assertTrue(sim.pose.y() >= sim.max.getY() + 1);
	}

	@Test
	void finalVerificationWaitsForUnloadedEarlierColumnsInsteadOfDeclaringDone() {
		BlockPos min = new BlockPos(0, 5, 0);
		Simulation sim = new Simulation(min, min.offset(1, 2, 0), true);
		sim.until(() -> sim.plan.completed() == 2);
		sim.world.set(min, Cell.UNLOADED);
		sim.until(() -> sim.plan.phase() == Phase.VERIFY);
		for (int tick = 0; tick < 10; tick++) {
			assertEquals(Action.WAIT, sim.tick().action());
			assertEquals(Phase.VERIFY, sim.plan.phase());
		}
		sim.world.set(min, Cell.AIR);
		sim.finish();
	}

	@Test
	void oneTickDelayedLiveInputsStillCompleteTwoVolumesWithoutCrossingUnclearedBlocks() {
		for (int multiplier : new int[]{10, 15}) {
			BlockPos min = new BlockPos(-4, -12, 7);
			BlockPos max = min.offset(3, 7, 2);
			Simulation sim = new Simulation(min, max, true,
				new Pose(max.getX() + 0.5, max.getY() + 1.25, max.getZ() + 0.5, 0, 0, 0));
			sim.horizontalMultiplier = multiplier;
			sim.delayMotionOneTick = true;
			sim.world.breakDelay = 3;
			sim.finish();
			assertEquals(96, sim.world.broken.size());
			assertEquals(96, new HashSet<>(sim.world.broken).size());
			assertEquals(12, sim.bottomVisits.size());
			assertEquals(12, sim.returnedColumns.size());
			assertEquals(0, sim.rejectedMoves);
		}
	}

	@Test
	void continuousDigDoesNotRequireExactLayerHeightAndSixtyFourBlockReturnIsFast() {
		Simulation sim = new Simulation(new BlockPos(0, 0, 0), new BlockPos(0, 64, 0), true);
		sim.world.breakDelay = 7;
		sim.until(() -> sim.plan.phase() == Phase.DIG);
		boolean minedDuringDescent = false;
		int start = sim.ticks;
		while (sim.world.broken.size() < 2) {
			Command command = sim.tick();
			minedDuringDescent |= command.action() == Action.MINE_DOWN;
			assertTrue(sim.ticks - start < 80, "Two ordinary blocks should not require 24 seconds of positioning");
		}
		assertTrue(minedDuringDescent);
		sim.until(() -> sim.plan.phase() == Phase.RETURN);
		int ascentStart = sim.ticks;
		sim.until(() -> sim.plan.phase() != Phase.RETURN);
		assertTrue(sim.ticks - ascentStart < 120, "64-block return should be continuous, with braking near the top");
		sim.finish();
	}
	@Test
	void naturalGravityDigLandsOnEachUnbrokenBlockAndOnlyFliesOnReturn() {
		Simulation sim = new Simulation(new BlockPos(0, 0, 0), new BlockPos(1, 64, 0), true);
		sim.naturalDig = true;
		sim.world.breakDelay = 7;
		sim.finish();
		assertEquals(130, sim.world.broken.size());
		assertEquals(2, sim.bottomVisits.size());
		assertEquals(2, sim.returnedColumns.size());
		assertTrue(sim.ticks < 2500, "Two 65-layer shafts should not spend 12 seconds positioning per layer");
	}

	@Test
	void waterThreatKeepsItsSolidBarrierAndSkipsWithoutFalseCompletion() {
		Simulation sim = new Simulation(new BlockPos(0, 10, 0), new BlockPos(2, 15, 0), true);
		BlockPos barrier = new BlockPos(0, 12, 0);
		sim.world.liquidThreats.add(barrier);
		sim.world.set(barrier.offset(0, 0, 1), Cell.LIQUID);
		sim.finish();
		assertEquals(1, sim.plan.skipped());
		assertEquals(2, sim.plan.completed());
		assertEquals(Cell.SOLID, sim.world.cell(barrier));
		assertFalse(sim.world.broken.contains(barrier));
		assertEquals(Cell.LIQUID, sim.world.cell(barrier.offset(0, 0, 1)));
	}

	@Test
	void checkpointResumesInTheSameShaftWithoutReturningToTop(@org.junit.jupiter.api.io.TempDir java.nio.file.Path temp) throws Exception {
		Simulation sim = new Simulation(new BlockPos(-1, 0, 2), new BlockPos(0, 30, 2), true);
		sim.until(() -> sim.plan.phase() == Phase.DIG && sim.plan.cursorY() < 20);
		java.nio.file.Path file = temp.resolve("area-progress.json");
		BorerAreaProgress.write(file, "server-a|overworld", sim.plan.snapshot());
		assertNull(BorerAreaProgress.read(file, "server-b|overworld"));
		var saved = BorerAreaProgress.read(file, "server-a|overworld");
		assertNotNull(saved);
		assertNull(BorerAreaPlan.restore(sim.min, sim.max.above(), sim.pose, saved));
		BlockPos previousColumn = sim.plan.column();
		sim.plan = BorerAreaPlan.restore(sim.min, sim.max, sim.pose, saved);
		assertNotNull(sim.plan);
		while (sim.plan.phase() == Phase.SURVEY) assertEquals(Action.WAIT, sim.tick().action());
		assertEquals(Phase.DIG, sim.plan.phase());
		assertEquals(previousColumn, sim.plan.column());
		assertNotEquals(Action.UP, sim.tick().action());
		sim.finish();
		assertEquals(62, sim.world.broken.size());
		assertEquals(62, new HashSet<>(sim.world.broken).size());
	}

	@Test
	void absentCheckpointCanRecogniseAnAlreadyOpenShaftAtThePlayersPosition() {
		BlockPos min = new BlockPos(0, 0, 0), max = new BlockPos(2, 30, 0);
		VoxelWorld world = new VoxelWorld(min, max, true);
		for (int y = 15; y <= 30; y++) world.set(new BlockPos(1, y, 0), Cell.AIR);
		Pose p = new Pose(1.5, 15.1, 0.5, 0, 0, 0);
		BorerAreaPlan resumed = new BorerAreaPlan(min, max, p);
		assertTrue(resumed.resumeInOpenShaft(world, p));
		assertEquals(Phase.DIG, resumed.phase());
		assertEquals(14, resumed.cursorY());
		assertEquals(new BlockPos(1, 0, 0), resumed.column());
		assertEquals(Action.MINE, resumed.step(world, p).action());
	}

	@Test
	void resumesFromAnotherColumnWithoutDiscardingTheAreaAndChoosesRemainingWork() {
		Simulation sim = new Simulation(new BlockPos(0, 0, 0), new BlockPos(3, 10, 0), true);
		sim.until(() -> sim.plan.phase() == Phase.DIG && sim.plan.completed() == 1 && sim.plan.cursorY() < 7);
		var saved = sim.plan.snapshot();
		int alreadyBroken = sim.world.broken.size();
		sim.pose = new Pose(0.5, 13, 0.5, 0, 0, 0); // Fly away, then return above a different, empty column.
		sim.plan = BorerAreaPlan.restore(sim.min, sim.max, sim.pose, saved);
		assertNotNull(sim.plan, "Changing position must not invalidate an otherwise matching checkpoint");
		while (sim.plan.phase() == Phase.SURVEY) assertEquals(Action.WAIT, sim.tick().action());
		assertEquals(1, sim.plan.completed());
		assertEquals(new BlockPos(1, 0, 0), sim.plan.pending());
		assertEquals(alreadyBroken, sim.world.broken.size());
		sim.finish();
		assertEquals(44, sim.world.broken.size());
		assertEquals(44, new HashSet<>(sim.world.broken).size());
	}

	@Test
	void stoppedDuringReturnCanResumeFromFarAwayWithoutRevisitingTheFinishedShaft() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(2, 10, 0), true);
		sim.until(() -> sim.plan.phase() == Phase.RETURN && sim.plan.completed() == 1);
		var saved = sim.plan.snapshot();
		sim.pose = new Pose(3.5, 15, 0.5, 0, 0, 0);
		sim.plan = BorerAreaPlan.restore(sim.min, sim.max, sim.pose, saved);
		assertNotNull(sim.plan);
		while (sim.plan.phase() == Phase.SURVEY) assertEquals(Action.WAIT, sim.tick().action());
		assertEquals(1, sim.plan.completed());
		assertEquals(new BlockPos(2, 0, 0), sim.plan.pending());
		sim.finish();
		assertEquals(33, sim.world.broken.size());
		assertEquals(1, sim.enteredColumns.stream().filter(BlockPos.ZERO::equals).count());
	}

	@Test
	void lostCheckpointSkipsDozensOfClearedColumnsAndGoesDirectlyToNearestRemainingColumn() {
		Simulation sim = new Simulation(new BlockPos(0, 0, 0), new BlockPos(7, 30, 7), false,
			new Pose(2.5, 31.25, 2.5, 0, 0, 0));
		for (int y = 0; y <= 30; y++) {
			sim.world.set(new BlockPos(3, y, 2), Cell.SOLID);
			sim.world.set(new BlockPos(7, y, 7), Cell.SOLID);
		}
		sim.until(() -> sim.plan.phase() == Phase.DIG);
		assertEquals(62, sim.plan.completed());
		assertEquals(List.of(new BlockPos(3, 0, 2)), sim.enteredColumns);
		assertTrue(sim.bottomVisits.isEmpty(), "No exploratory descent into an empty column");
		sim.finish();
		assertEquals(2, sim.bottomVisits.size());
		assertEquals(64, sim.plan.completed());
		assertEquals(62, sim.world.broken.size());
	}

	@Test
	void anAlreadyEmptyAreaNeverDescendsOrRequestsBottomLighting() {
		Simulation sim = new Simulation(new BlockPos(0, 0, 0), new BlockPos(29, 29, 29), false,
			new Pose(15.5, 35, 12.5, 0, 0, 0));
		while (sim.plan.phase() != Phase.DONE && sim.ticks < 100) {
			Command c = sim.tick();
			assertEquals(Action.WAIT, c.action());
			assertFalse(sim.plan.reachedBottomThisStep());
			assertEquals(35, sim.pose.y());
		}
		assertEquals(Phase.DONE, sim.plan.phase());
		assertEquals(900, sim.plan.completed());
		assertTrue(sim.bottomVisits.isEmpty());
		assertTrue(sim.world.broken.isEmpty());
	}

	@Test
	void returningInsideAnEmptyShaftOnlyAscendsThenMinesRemainingColumns() {
		Simulation sim = new Simulation(new BlockPos(0, 0, 0), new BlockPos(1, 15, 0), true,
			new Pose(0.5, 3, 0.5, 0, 0, 0));
		for (int y = 0; y <= 15; y++) sim.world.set(new BlockPos(0, y, 0), Cell.AIR);
		while (sim.plan.phase() != Phase.DIG && sim.ticks < 300) {
			Command c = sim.tick();
			assertNotEquals(Action.DOWN, c.action());
			assertTrue(sim.bottomVisits.isEmpty());
		}
		assertEquals(new BlockPos(1, 0, 0), sim.plan.column());
		sim.finish();
		assertEquals(List.of(new BlockPos(1, 0, 0)), sim.bottomVisits);
	}

	@Test
	void aSingleRemainingBlockAtMinimumYPreventsAColumnBeingSkipped() {
		Simulation sim = new Simulation(new BlockPos(0, 0, 0), new BlockPos(0, 30, 0), false);
		sim.world.set(sim.min, Cell.SOLID);
		sim.until(() -> sim.plan.phase() == Phase.DIG);
		assertEquals(0, sim.plan.completed());
		sim.finish();
		assertEquals(List.of(sim.min), sim.world.broken);
		assertEquals(1, sim.bottomVisits.size());
	}

	@Test
	void fullColumnWithOnlyOneGhostAirObservationIsNotMarkedEmpty() {
		BlockPos min = BlockPos.ZERO, max = min.above(4);
		Simulation sim = new Simulation(min, max, false);
		sim.tick(); // First survey pass sees air.
		sim.world.set(min, Cell.SOLID);
		sim.tick(); // Second pass sees the server-restored block.
		assertEquals(0, sim.plan.completed());
		sim.finish();
		assertEquals(List.of(min), sim.world.broken);
	}

	@Test
	void unloadedSurveyColumnsAreNeitherCompleteNorMovementTargets() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 4, 0), false);
		BlockPos missing = new BlockPos(1, 0, 0);
		sim.world.set(missing, Cell.UNLOADED);
		for (int tick = 0; tick < 20; tick++) {
			assertEquals(Action.WAIT, sim.tick().action());
			assertFalse(sim.plan.reachedBottomThisStep());
			assertNotEquals(Phase.DONE, sim.plan.phase());
		}
		assertEquals(1, sim.plan.completed());
		assertTrue(sim.enteredColumns.isEmpty());
		sim.world.set(missing, Cell.SOLID);
		sim.finish();
		assertEquals(List.of(missing), sim.world.broken);
	}

	@Test
	void aNextColumnClearedManuallyAfterSurveyIsNotEnteredOrLit() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(2, 4, 0), true);
		sim.until(() -> sim.plan.phase() == Phase.RETURN && sim.plan.completed() == 1);
		for (int y = 0; y <= 4; y++) sim.world.set(new BlockPos(1, y, 0), Cell.AIR);
		sim.finish();
		assertEquals(List.of(BlockPos.ZERO, new BlockPos(2, 0, 0)), sim.enteredColumns);
		assertEquals(2, sim.bottomVisits.size());
		assertEquals(3, sim.plan.completed());
	}

	@Test
	void evenADoneCheckpointIsReconciledWithActualRefilledWorld() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 3, 0), true);
		sim.finish();
		var saved = sim.plan.snapshot();
		BlockPos refill = new BlockPos(0, 2, 0);
		sim.world.set(refill, Cell.SOLID);
		sim.plan = BorerAreaPlan.restore(sim.min, sim.max, sim.pose, saved);
		assertNotNull(sim.plan);
		sim.finish();
		assertEquals(2, sim.world.broken.stream().filter(refill::equals).count());
	}

	@Test
	void lowerAdjacentSurfaceDoesNotCauseSixtyFourBlockRoundTrip() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 64, 0), true);
		for (int y = 4; y <= 64; y++) sim.world.set(new BlockPos(1, y, 0), Cell.AIR);
		sim.until(() -> sim.plan.phase() == Phase.RETURN && sim.plan.completed() == 1);
		double highest = sim.pose.y();
		while (sim.plan.phase() != Phase.DIG) { sim.tick(); highest = Math.max(highest, sim.pose.y()); }
		assertEquals(new BlockPos(1, 0, 0), sim.plan.column());
		assertEquals(3, sim.plan.cursorY());
		assertTrue(highest <= 4.35, "Only rise to the next remaining surface, not the configured Y 64");
		sim.finish();
		assertEquals(69, sim.world.broken.size());
	}

	@Test
	void eachNewColumnRecomputesHeightIncludingATallerColumnAfterALowOne() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(2, 40, 0), true);
		for (int y = 4; y <= 40; y++) sim.world.set(new BlockPos(1, y, 0), Cell.AIR);
		sim.until(() -> sim.plan.phase() == Phase.DIG && sim.plan.completed() == 1);
		assertEquals(4.25, sim.plan.transferY());
		sim.until(() -> sim.plan.phase() == Phase.TRANSFER && sim.plan.completed() == 2);
		assertEquals(41.25, sim.plan.transferY());
		sim.finish();
	}

	@Test
	void crossingAReservedHigherColumnUsesItsHeightAndNeverCutsThroughIt() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(2, 64, 0), true);
		for (int y = 0; y <= 64; y++) {
			sim.world.set(new BlockPos(1, y, 0), y <= 35 ? Cell.SOLID : Cell.AIR);
			if (y > 3) sim.world.set(new BlockPos(2, y, 0), Cell.AIR);
		}
		BlockPos chest = new BlockPos(1, 35, 0); sim.world.set(chest, Cell.PROTECTED);
		sim.plan.reserveStorageColumn(chest);
		sim.until(() -> sim.plan.phase() == Phase.TRANSFER && sim.plan.completed() == 1);
		assertEquals(new BlockPos(2, 0, 0), sim.plan.pending());
		assertEquals(36.25, sim.plan.transferY());
		sim.finish();
		assertEquals(Cell.PROTECTED, sim.world.cell(chest));
		assertTrue(sim.world.broken.stream().noneMatch(b -> b.getX() == 1));
	}

	@Test
	void manuallyEmptiedNextColumnIsSkippedBeforeStartingTheAscent() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(2, 64, 0), true);
		for (int y = 5; y <= 64; y++) sim.world.set(new BlockPos(2, y, 0), Cell.AIR);
		sim.until(() -> sim.plan.phase() == Phase.RETURN && sim.plan.completed() == 1);
		for (int y = 0; y <= 64; y++) sim.world.set(new BlockPos(1, y, 0), Cell.AIR);
		double highest = sim.pose.y();
		while (sim.plan.phase() != Phase.DIG) { sim.tick(); highest = Math.max(highest, sim.pose.y()); }
		assertEquals(new BlockPos(2, 0, 0), sim.plan.column());
		assertTrue(highest <= 5.35);
		sim.finish();
		assertFalse(sim.enteredColumns.contains(new BlockPos(1, 0, 0)));
	}

	@Test
	void unknownNextSurfaceWaitsAtTheBottomInsteadOfBlindlyTakingOff() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 20, 0), true);
		sim.until(() -> sim.plan.phase() == Phase.RETURN && sim.plan.completed() == 1);
		BlockPos unknown = new BlockPos(1, 20, 0); sim.world.set(unknown, Cell.UNLOADED);
		Pose before = sim.pose;
		for (int tick = 0; tick < 12; tick++) assertEquals(Action.WAIT, sim.tick().action());
		assertEquals(before.y(), sim.pose.y()); assertEquals(1, sim.plan.completed());
		sim.world.set(unknown, Cell.SOLID); sim.finish();
	}

	@Test
	void aHigherServerRefillDuringLowTransferRaisesTheRouteBeforeCrossing() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 20, 0), true);
		for (int y = 4; y <= 20; y++) sim.world.set(new BlockPos(1, y, 0), Cell.AIR);
		sim.until(() -> sim.plan.phase() == Phase.TRANSFER && sim.plan.completed() == 1);
		assertEquals(4.25, sim.plan.transferY());
		BlockPos refill = new BlockPos(1, 15, 0); sim.world.set(refill, Cell.SOLID);
		assertEquals(Action.WAIT, sim.tick().action()); assertEquals(Phase.RETURN, sim.plan.phase());
		sim.until(() -> sim.plan.phase() == Phase.TRANSFER);
		assertEquals(16.25, sim.plan.transferY());
		sim.finish(); assertTrue(sim.world.broken.contains(refill));
	}

	@Test
	void bedrockStopsOnlyItsOwnColumnAndLeavesBlocksBelowItUntouched() {
		Simulation sim = new Simulation(new BlockPos(0, -4, 0), new BlockPos(2, 5, 0), true);
		BlockPos bedrock = BlockPos.ZERO; sim.world.set(bedrock, Cell.BEDROCK);
		sim.until(() -> sim.plan.bedrockColumns() == 1);
		assertEquals(Phase.RETURN, sim.plan.phase()); assertEquals(0, sim.plan.completed());
		sim.finish();
		assertEquals(2, sim.plan.completed()); assertEquals(1, sim.plan.skipped());
		assertEquals(Cell.BEDROCK, sim.world.cell(bedrock));
		assertTrue(sim.world.broken.stream().noneMatch(b -> b.getX() == 0 && b.getY() <= 0));
		assertEquals(25, sim.world.broken.size());
	}

	@Test
	void unevenBedrockInEveryColumnFinishesWithoutMiningAnyBedrock() {
		Simulation sim = new Simulation(new BlockPos(0, -64, 0), new BlockPos(2, -54, 0), true);
		sim.naturalDig = true;
		for (int x = 0; x < 3; x++) sim.world.set(new BlockPos(x, -64 + x, 0), Cell.BEDROCK);
		sim.finish();
		assertEquals(3, sim.plan.bedrockColumns()); assertEquals(0, sim.plan.completed());
		assertEquals(27, sim.world.broken.size());
		assertTrue(sim.pose.y() > -54);
	}

	@Test
	void alreadyExposedBedrockIsRecognisedWithoutReenteringFinishedShafts() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(2, 20, 0), false);
		for (int x = 0; x < 3; x++) sim.world.set(new BlockPos(x, x, 0), Cell.BEDROCK);
		while (sim.plan.phase() != Phase.DONE) {
			Command c = sim.tick(); assertEquals(Action.WAIT, c.action());
		}
		assertEquals(3, sim.plan.bedrockColumns()); assertTrue(sim.enteredColumns.isEmpty());
		assertTrue(sim.world.broken.isEmpty());
	}

	@Test
	void restartRechecksBedrockAndDoesNotRepeatTheCompletedBedrockColumn() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 10, 0), true);
		sim.world.set(BlockPos.ZERO, Cell.BEDROCK);
		sim.until(() -> sim.plan.bedrockColumns() == 1);
		var saved = sim.plan.snapshot();
		sim.plan = BorerAreaPlan.restore(sim.min, sim.max, sim.pose, saved);
		assertNotNull(sim.plan); sim.finish();
		assertEquals(1, sim.plan.bedrockColumns()); assertEquals(1, sim.plan.completed());
		assertEquals(1, sim.enteredColumns.stream().filter(BlockPos.ZERO::equals).count());
	}

	@Test
	void finalVerificationStillFindsRefilledStoneAboveRecordedBedrock() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 10, 0), true);
		sim.world.set(BlockPos.ZERO, Cell.BEDROCK);
		sim.until(() -> sim.plan.bedrockColumns() == 1 && sim.plan.phase() == Phase.DIG);
		BlockPos refill = new BlockPos(0, 5, 0); sim.world.set(refill, Cell.SOLID);
		sim.finish();
		assertEquals(2, sim.world.broken.stream().filter(refill::equals).count());
		assertEquals(1, sim.plan.bedrockColumns()); assertEquals(1, sim.plan.completed());
	}

	@Test
	void unevenSurfacesAndBedrockWithDelayedInputsOrGravityKeepTheSameSafeCoverage() {
		for (int sample = 0; sample < 8; sample++) {
			var random = new java.util.Random(71314 + sample);
			BlockPos min = new BlockPos(-3, -64, -2), max = min.offset(3, 12, 2);
			Simulation sim = new Simulation(min, max, false, new Pose(
				(sample % 2 == 0 ? min.getX() : max.getX()) + .5, max.getY() + 1.25,
				(sample % 3 == 0 ? min.getZ() : max.getZ()) + .5, 0, 0, 0));
			sim.naturalDig = sample % 2 == 0; sim.delayMotionOneTick = !sim.naturalDig;
			sim.world.breakDelay = 2; sim.horizontalMultiplier = sample % 2 == 0 ? 10 : 15;
			Set<BlockPos> expected = new HashSet<>();
			for (int x = min.getX(); x <= max.getX(); x++) for (int z = min.getZ(); z <= max.getZ(); z++) {
				int top = min.getY() + random.nextInt(13);
				int floor = random.nextBoolean() ? min.getY() + random.nextInt(3) : min.getY() - 1;
				for (int y = min.getY(); y <= top; y++) {
					BlockPos b = new BlockPos(x, y, z); sim.world.set(b, Cell.SOLID);
					if (y > floor) expected.add(b);
				}
				if (floor >= min.getY()) sim.world.set(new BlockPos(x, floor, z), Cell.BEDROCK);
			}
			sim.finish();
			assertEquals(expected, new HashSet<>(sim.world.broken));
			assertEquals(expected.size(), sim.world.broken.size());
		}
	}

	@Test
	void bedrockInAnExitCeilingDoesNotAuthorizeMiningOrFlyingThroughIt() {
		Simulation sim = new Simulation(BlockPos.ZERO, new BlockPos(1, 10, 0), false,
			new Pose(.5, 2, .5, 0, 0, 0));
		BlockPos roof = new BlockPos(0, 8, 0); sim.world.set(roof, Cell.BEDROCK);
		sim.world.set(new BlockPos(1, 10, 0), Cell.SOLID);
		sim.until(() -> sim.plan.phase() == Phase.BLOCKED);
		assertFalse(sim.world.broken.contains(roof)); assertTrue(sim.pose.y() < 8);
	}

	private static final class VoxelWorld implements BorerAreaPlan.World {
		final BlockPos min, max;
		final boolean solidVolume;
		final Map<BlockPos, Cell> overrides = new HashMap<>();
		final Map<BlockPos, Integer> pendingBreaks = new HashMap<>();
		final Map<BlockPos, Integer> attempts = new HashMap<>();
		final List<BlockPos> broken = new ArrayList<>();
		int breakDelay;
		final Set<BlockPos> liquidThreats = new HashSet<>();
		@Override public boolean opensLiquid(BlockPos p) { return liquidThreats.contains(p); }

		VoxelWorld(BlockPos min, BlockPos max, boolean solidVolume) {
			this.min = min;
			this.max = max;
			this.solidVolume = solidVolume;
		}

		@Override
		public Cell cell(BlockPos p) {
			Cell override = overrides.get(p);
			if (override != null) return override;
			if (p.getY() < min.getY()) return Cell.PROTECTED;
			return solidVolume && inside(p) ? Cell.SOLID : Cell.AIR;
		}

		boolean inside(BlockPos p) {
			return p.getX() >= min.getX() && p.getX() <= max.getX()
				&& p.getY() >= min.getY() && p.getY() <= max.getY()
				&& p.getZ() >= min.getZ() && p.getZ() <= max.getZ();
		}

		void set(BlockPos p, Cell cell) { overrides.put(p.immutable(), cell); }

		void requestMine(BlockPos p) {
			assertEquals(Cell.SOLID, cell(p), "The executor never destroys liquid/protected/unloaded cells");
			attempts.merge(p, 1, Integer::sum);
			if (breakDelay == 0) breakNow(p);
			else pendingBreaks.putIfAbsent(p, breakDelay);
		}

		void serverTick() {
			List<BlockPos> acknowledged = new ArrayList<>();
			pendingBreaks.replaceAll((p, ticks) -> ticks - 1);
			pendingBreaks.forEach((p, ticks) -> { if (ticks <= 0) acknowledged.add(p); });
			for (BlockPos p : acknowledged) {
				pendingBreaks.remove(p);
				if (cell(p) == Cell.SOLID) breakNow(p);
			}
		}

		private void breakNow(BlockPos p) {
			set(p, Cell.AIR);
			broken.add(p.immutable());
		}
	}

	/** This executor knows commands and voxel collisions, never how to advance the production phase. */
	private static final class Simulation {
		final BlockPos min, max;
		final VoxelWorld world;
		BorerAreaPlan plan;
		final List<BlockPos> enteredColumns = new ArrayList<>();
		final List<BlockPos> bottomVisits = new ArrayList<>();
		final List<BlockPos> returnedColumns = new ArrayList<>();
		Pose pose;
		int ticks, rejectedMoves;
		boolean naturalDig;
		int horizontalMultiplier = 10;
		float yaw = 127.5F;
		boolean delayMotionOneTick;
		BorerAreaMotion.Input pendingInput = new BorerAreaMotion.Input(yaw, false, false, false, 0);

		Simulation(BlockPos min, BlockPos max, boolean solid) {
			this(min, max, solid, new Pose(min.getX() + 0.5, max.getY() + 1.25, min.getZ() + 0.5, 0, 0, 0));
		}

		Simulation(BlockPos min, BlockPos max, boolean solid, Pose start) {
			this.min = min;
			this.max = max;
			world = new VoxelWorld(min, max, solid);
			pose = start;
			plan = new BorerAreaPlan(min, max, start);
		}

		void finish() {
			until(() -> plan.phase() == Phase.DONE || plan.phase() == Phase.BLOCKED);
			assertEquals(Phase.DONE, plan.phase(), () -> "Stopped at " + pose + ", next=" + plan.step(world, pose));
			assertEquals(plan.total(), plan.completed() + plan.skipped());
			assertEquals(0, rejectedMoves);
		}

		void until(BooleanSupplier condition) {
			int deadline = ticks + 1_500_000;
			while (!condition.getAsBoolean() && ticks < deadline) tick();
			assertTrue(condition.getAsBoolean(), () -> "No convergence: " + plan.phase() + " " + pose
				+ " cursor=" + plan.cursorY() + " completed=" + plan.completed());
		}

		Command tick() {
			world.serverTick();
			Phase previous = plan.phase();
			int completed = plan.completed();
			BlockPos departure = plan.column();
			Command command = plan.step(world, pose);
			ticks++;
			if (plan.reachedBottomThisStep()) {
				assertEquals(completed + 1, plan.completed());
				assertEquals(Phase.RETURN, plan.phase());
				assertEquals(min.getY(), (int)Math.floor(pose.y()), "Physical feet must reach the bottom layer");
				for (int y = min.getY(); y <= max.getY(); y++) {
					assertEquals(Cell.AIR, world.cell(new BlockPos(departure.getX(), y, departure.getZ())));
				}
				bottomVisits.add(departure);
			}
			if (previous == Phase.RETURN && plan.phase() != Phase.RETURN) {
				assertTrue(Math.abs(pose.y() - plan.transferY()) <= BorerAreaPlan.HEIGHT);
				assertEquals(departure, plan.column(), "Do not replace the column during ascent");
				returnedColumns.add(departure);
			}
			if (previous != Phase.DIG && plan.phase() == Phase.DIG) {
				if (previous != Phase.SURVEY) assertTrue(Math.abs(pose.y() - plan.transferY()) <= BorerAreaPlan.HEIGHT);
				assertTrue(java.util.stream.IntStream.rangeClosed(min.getY(), max.getY()).anyMatch(y ->
					world.cell(new BlockPos(plan.column().getX(), y, plan.column().getZ())) != Cell.AIR), "Never enter an empty shaft to mine");
				enteredColumns.add(plan.column());
			}
			if (previous == Phase.RETURN && command.action() != Action.DONE) {
				assertEquals(departure, plan.column());
			}
			if ((command.action() == Action.MINE || command.action() == Action.MINE_DOWN) && plan.phase() == Phase.DIG) {
				assertEquals(plan.column().getX(), command.block().getX());
				assertEquals(plan.column().getZ(), command.block().getZ());
				assertTrue(world.inside(command.block()));
			}
			if ((command.action() == Action.X || command.action() == Action.Z) && plan.phase() == Phase.TRANSFER) {
				assertTrue(Math.abs(pose.y() - plan.transferY()) <= BorerAreaPlan.HEIGHT,
					"Never cross to another shaft below the transfer height");
			}
			if (command.action() == Action.MINE || command.action() == Action.MINE_DOWN) world.requestMine(command.block());
			if (naturalDig && plan.phase() == Phase.DIG && command.action() != Action.UP
				&& command.action() != Action.X && command.action() != Action.Z) {
				applyGravity();
				return command;
			}
			// Use the same yaw/key/speed mapping as the live Runner. No command-axis shortcut or target snapping.
			BorerAreaMotion.Input requested = BorerAreaMotion.of(command, pose, yaw);
			BorerAreaMotion.Input applied = delayMotionOneTick ? pendingInput : requested;
			pendingInput = requested;
			applyInput(applied);
			return command;
		}

		private void stopMomentum() { pose = new Pose(pose.x(), pose.y(), pose.z(), 0, 0, 0); }
		private void applyGravity() {
			double dy = (pose.vy() - 0.08) * 0.98;
			int count = Math.max(1, (int)Math.ceil(Math.abs(dy) / 0.01));
			double lastY = pose.y();
			for (int i = 1; i <= count; i++) {
				double nextY = pose.y() + dy * i / count;
				if (!bodyFits(pose.x(), nextY, pose.z())) {
					pose = new Pose(pose.x(), lastY, pose.z(), 0, 0, 0);
					return;
				}
				lastY = nextY;
			}
			pose = new Pose(pose.x(), lastY, pose.z(), 0, dy, 0);
		}

		private void applyInput(BorerAreaMotion.Input input) {
			yaw = input.yaw();
			double radians = Math.toRadians(yaw);
			double forward = input.forward() ? input.speed() * horizontalMultiplier : 0;
			double dx = -Math.sin(radians) * forward;
			double dz = Math.cos(radians) * forward;
			double dy = (input.up() ? 1 : input.down() ? -1 : 0) * input.speed() * 5;
			assertTrue(Math.max(Math.abs(dx), Math.abs(dz)) <= 0.25);
			assertTrue(Math.abs(dy) <= 1.20);
			if (dx == 0 && dy == 0 && dz == 0) { stopMomentum(); return; }
			// Independent physical execution: sample the swept body at 0.025-block intervals.
			int samples = Math.max(1, (int)Math.ceil(Math.max(Math.max(Math.abs(dx), Math.abs(dy)), Math.abs(dz)) / 0.025));
			for (int i = 1; i <= samples; i++) {
				double fraction = i / (double)samples;
				if (!bodyFits(pose.x() + dx * fraction, pose.y() + dy * fraction, pose.z() + dz * fraction)) {
					rejectedMoves++;
					stopMomentum();
					return;
				}
			}
			pose = new Pose(pose.x() + dx, pose.y() + dy, pose.z() + dz, dx, dy, dz);
		}

		private boolean bodyFits(double x, double y, double z) {
			for (int bx = (int)Math.floor(x - 0.3 + 1e-7); bx <= (int)Math.floor(x + 0.3 - 1e-7); bx++) {
				for (int by = (int)Math.floor(y + 1e-7); by <= (int)Math.floor(y + 1.8 - 1e-7); by++) {
					for (int bz = (int)Math.floor(z - 0.3 + 1e-7); bz <= (int)Math.floor(z + 0.3 - 1e-7); bz++) {
						if (world.cell(new BlockPos(bx, by, bz)) != Cell.AIR) return false;
					}
				}
			}
			return true;
		}
	}
}
