package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.*;
import java.util.function.BooleanSupplier;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;
import static org.junit.jupiter.api.Assertions.*;

/** Run the real shallow planner through real motion commands, voxel ray checks and independent swept-body collision tests. */
class BorerAreaHorizontalTest {
    @Test void selectsOnlyOneThroughSixActualLayersIncludingBothEndpoints() {
        for (int h = 1; h <= 6; h++) assertTrue(BorerAreaHorizontal.enabled(new BlockPos(0, -20, 0), new BlockPos(3, -21 + h, 3)));
        assertFalse(BorerAreaHorizontal.enabled(BlockPos.ZERO, new BlockPos(3, 6, 3)));
        assertFalse(BorerAreaHorizontal.enabled(new BlockPos(0, -64, 0), new BlockPos(3, 64, 3)), "Same-Y UI selection resolves down to the world's floor first");
        assertFalse(BorerAreaHorizontal.enabled(new BlockPos(0, 3, 0), BlockPos.ZERO));
    }
    @Test void threeAndSixLayerRoomsAreClearedHorizontallyFromAllFourCorners() {
        for (int height : new int[]{3, 6}) for (int x : new int[]{-4, -1}) for (int z : new int[]{5, 7}) {
            var min = new BlockPos(-4, -20, 5); var max = new BlockPos(-1, -21 + height, 7);
            var sim = new Sim(min, max, true, new Pose(x + .5, max.getY() + 1.25, z + .5, 0, 0, 0));
            sim.finish(); assertEquals(12 * height, sim.world.broken.size());
            assertEquals(12 * height, new HashSet<>(sim.world.broken).size());
            assertEquals(12, sim.bottomVisits.size(), "Enter cleared cells to pick up drops and trigger lighting checks");
            assertEquals(12, sim.plan.completed()); assertEquals(0, sim.plan.skipped());
            assertTrue(sim.traces.stream().anyMatch(t -> t.phase == Phase.HORIZONTAL && t.command.action() == Action.MINE));
            for (Trace t : sim.traces) if (t.phase == Phase.HORIZONTAL) {
                assertFalse(t.command.action() == Action.UP || t.command.action() == Action.DOWN, t.toString());
                assertEquals(min.getY() + .08, t.before.y(), .11);
            }
        }
    }
    @Test void shallowStrategyEliminatesRepeatedAscentAndHasFewerMotionTicks() {
        var min = BlockPos.ZERO; var max = new BlockPos(5, 2, 3);
        var shallow = new Sim(min, max, true); var vertical = new Sim(min, max, false);
        shallow.finish(); vertical.finish();
        assertEquals(new HashSet<>(vertical.world.broken), new HashSet<>(shallow.world.broken));
        assertTrue(shallow.verticalMoves() < vertical.verticalMoves() / 3);
        assertTrue(shallow.ticks < vertical.ticks, "Shallow=" + shallow.ticks + ", vertical=" + vertical.ticks);
        System.out.println("3-layer 24-column motion simulation: horizontal ticks=" + shallow.ticks + ", shaft ticks=" + vertical.ticks
            + ", horizontal vertical-moves=" + shallow.verticalMoves() + ", shaft vertical-moves=" + vertical.verticalMoves());
    }
    @Test void sevenLayersRemainVerticalEvenIfShallowWasRequested() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 6, 1), true); sim.finish();
        assertFalse(sim.plan.horizontal());
        assertTrue(sim.traces.stream().noneMatch(t -> t.phase == Phase.HORIZONTAL));
        assertEquals(42, sim.world.broken.size());
    }
    @Test void thirtyByThirtyThreeLayerProjectDoesNotMissOrReenterColumns() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(29, 2, 29), true); sim.finish();
        assertEquals(2700, sim.world.broken.size()); assertEquals(2700, new HashSet<>(sim.world.broken).size());
        assertEquals(900, sim.bottomVisits.size()); assertEquals(900, new HashSet<>(sim.bottomVisits).size());
        assertEquals(900, sim.plan.completed()); assertTrue(sim.verticalMoves() < 40);
    }
    @Test void existingEntranceAtTheBottomStartsWithoutFlyingToTheTop() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 2, 0), true, new Pose(.5, .08, .5, 0, 0, 0));
        sim.world.clearColumn(0, 0);
        sim.until(() -> sim.plan.completed() == 3);
        assertEquals(0, sim.verticalMoves()); assertEquals(6, sim.world.broken.size()); sim.finish();
    }
    @Test void finishingAnEnclosedShallowRoomDoesNotBreakItsUnselectedCeiling() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 2, 0), true, new Pose(.5, .08, .5, 0, 0, 0));
        sim.world.clearColumn(0, 0);
        for (int x = 0; x <= 2; x++) sim.world.cells.put(new BlockPos(x, 3, 0), Cell.SOLID);
        sim.finish(); assertEquals(0, sim.verticalMoves()); assertEquals(6, sim.world.broken.size());
        assertEquals(.08, sim.pose.y(), .11);
        for (int x = 0; x <= 2; x++) assertEquals(Cell.SOLID, sim.world.cell(new BlockPos(x, 3, 0)));
    }
    @Test void reachFallbackCannotPunchThroughAnUnselectedRoofToGetAboveTheRoom() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(1, 5, 0), true, new Pose(.5, .08, .5, 0, 0, 0));
        sim.world.clearColumn(0, 0); sim.world.reach = 2.6;
        sim.world.cells.put(new BlockPos(0, 6, 0), Cell.SOLID);
        sim.until(() -> sim.plan.phase() == Phase.BLOCKED);
        assertEquals(Cell.SOLID, sim.world.cell(new BlockPos(0, 6, 0)));
        assertTrue(sim.world.broken.stream().allMatch(sim.world::inside));
    }
    @Test void twoHighWallIsMinedBeforeAnyForwardMotionAndNeverTriggersJump() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(1, 2, 0), true, new Pose(.5, .08, .5, 0, 0, 0));
        sim.world.clearColumn(0, 0); sim.finish();
        assertEquals(List.of(new BlockPos(1, 1, 0), new BlockPos(1, 0, 0), new BlockPos(1, 2, 0)), sim.world.broken);
        for (Trace t : sim.traces) if (t.phase == Phase.HORIZONTAL && t.command.action() == Action.MINE)
            assertFalse(BorerAreaMotion.of(t.command, t.before, 0).up());
    }
    @Test void insufficientRealReachFallsBackWithoutPretendingTheUpperBlocksWereMined() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 5, 0), true);
        sim.world.reach = 2.6; sim.finish();
        assertEquals(18, sim.world.broken.size());
        assertTrue(sim.traces.stream().anyMatch(t -> t.command.reason().contains("真实触及距离")));
    }
    @Test void protectedAndWetColumnsArePreservedAndOrdinaryWorkCanGoAroundThem() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(3, 2, 2), true);
        var chest = new BlockPos(1, 1, 0); var water = new BlockPos(2, 1, 1);
        sim.world.cells.put(chest, Cell.PROTECTED); sim.world.cells.put(water, Cell.LIQUID);
        sim.finish(); assertEquals(Cell.PROTECTED, sim.world.cell(chest)); assertEquals(Cell.LIQUID, sim.world.cell(water));
        assertEquals(2, sim.plan.skipped()); assertEquals(10, sim.plan.completed());
        assertEquals(30, sim.world.broken.size());
        assertTrue(sim.traces.stream().anyMatch(t -> t.command.reason().contains("水平绕过保护列")));
    }
    @Test void bedrockUsesSafeTopDownAccessForItsColumnWithoutDestroyingIt() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 2, 0), true);
        sim.world.cells.put(new BlockPos(1, 0, 0), Cell.BEDROCK); sim.finish();
        assertEquals(1, sim.plan.bedrockColumns()); assertEquals(2, sim.plan.completed()); assertEquals(8, sim.world.broken.size());
    }
    @Test void delayedBreakAndServerRefillAreNeverCountedFromAttackAnimation() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(1, 2, 0), true);
        sim.world.delay = 8;
        sim.until(() -> sim.plan.phase() == Phase.HORIZONTAL && !sim.world.waiting.isEmpty());
        assertEquals(1, sim.plan.completed());
        BlockPos first = new BlockPos(1, 1, 0);
        sim.until(() -> sim.world.broken.contains(first)); sim.world.cells.put(first, Cell.SOLID);
        sim.finish(); assertTrue(sim.world.broken.stream().filter(first::equals).count() >= 2);
        assertEquals(2, sim.plan.completed());
    }
    @Test void unloadedTargetWaitsWithoutMovingOrCountingIt() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(1, 2, 0), true);
        sim.until(() -> sim.plan.phase() == Phase.HORIZONTAL);
        var target = new BlockPos(1, 2, 0); sim.world.cells.put(target, Cell.UNLOADED);
        Pose parked = sim.pose;
        for (int i = 0; i < 10; i++) { assertEquals(Action.WAIT, sim.tick().action()); assertEquals(1, sim.plan.completed()); }
        assertEquals(parked.x(), sim.pose.x()); assertEquals(parked.y(), sim.pose.y());
        sim.world.cells.put(target, Cell.SOLID); sim.finish();
    }
    @Test void restartUsesWorldSurveyAndKeepsTheShallowStrategy(@TempDir Path temp) throws Exception {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(3, 2, 1), true);
        sim.until(() -> sim.plan.completed() == 3);
        var file = temp.resolve("progress.json"); BorerAreaProgress.write(file, "world", sim.plan.snapshot());
        sim.plan = BorerAreaPlan.restore(sim.min, sim.max, sim.pose, BorerAreaProgress.read(file, "world"), true);
        assertNotNull(sim.plan); assertTrue(sim.plan.horizontal()); sim.finish();
        assertEquals(24, sim.world.broken.size()); assertEquals(24, new HashSet<>(sim.world.broken).size());
    }
    @Test void finalVerificationReturnsForARefilledPreviouslyCompletedCell() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 2, 0), true);
        sim.until(() -> sim.plan.completed() == 3);
        sim.world.cells.put(new BlockPos(0, 2, 0), Cell.SOLID); sim.finish();
        assertEquals(10, sim.world.broken.size());
    }
    @Test void reachableSideWaterIsSealedBeforeTheBarrierIsMined() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(1, 2, 0), true);
        sim.world.barrier = new BlockPos(1, 1, 0); sim.world.water = new BlockPos(1, 1, -1); sim.world.sealable = true;
        sim.world.cells.put(sim.world.water, Cell.LIQUID);
        sim.until(() -> !sim.traces.isEmpty() && sim.traces.getLast().command.action() == Action.SEAL_WATER);
        assertEquals(Cell.SOLID, sim.world.cell(sim.world.barrier)); assertEquals(1, sim.plan.completed());
        sim.world.cells.put(sim.world.water, Cell.PROTECTED); sim.plan.rememberWaterSeal(sim.world.water);
        sim.finish(); assertEquals(6, sim.world.broken.size()); assertFalse(sim.world.broken.contains(sim.world.water));
    }
    @Test void unsealableSideLiquidKeepsTheBarrierAndSelectsAnotherColumn() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 2, 0), true);
        sim.world.barrier = new BlockPos(1, 1, 0); sim.world.water = new BlockPos(1, 1, -1);
        sim.world.cells.put(sim.world.water, Cell.LIQUID); sim.finish();
        assertEquals(1, sim.plan.skipped()); assertEquals(6, sim.world.broken.size());
        assertEquals(Cell.SOLID, sim.world.cell(sim.world.barrier));
    }
    @Test void cargoReservationAndReturnDoNotResumeMiningThroughTheNewChest() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(2, 2, 1), true);
        sim.until(() -> sim.plan.phase() == Phase.HORIZONTAL);
        var chest = new BlockPos(1, 0, 0); sim.world.cells.put(chest, Cell.PROTECTED);
        assertTrue(sim.plan.reserveStorageColumn(chest)); sim.plan.resumeAfterStorage(sim.pose);
        sim.finish(); assertEquals(1, sim.plan.skipped()); assertEquals(5, sim.plan.completed());
        assertEquals(Cell.PROTECTED, sim.world.cell(chest));
    }
    @Test void liquidRescueDoesNotImmediatelyDescendBackIntoTheReservedWaterColumn() {
        var sim = new Sim(BlockPos.ZERO, new BlockPos(1, 2, 0), true);
        sim.until(() -> sim.plan.phase() == Phase.HORIZONTAL);
        var water = new BlockPos(0, 0, 0); sim.world.cells.put(water, Cell.LIQUID);
        sim.plan.skipLiquid(sim.pose, water);
        assertEquals(0, sim.plan.completed()); assertEquals(1, sim.plan.skipped());
        sim.pose = new Pose(.5, 3.25, .5, 0, 0, 0); // Rescue has surfaced; the planner must not dive back down.
        assertEquals(Action.WAIT, sim.tick().action()); assertEquals(Phase.RETURN, sim.plan.phase());
        assertNotEquals(Action.DOWN, sim.tick().action());
    }

    private record Trace(Phase phase, Pose before, Command command) {}
    private static final class World implements BorerAreaPlan.World {
        final BlockPos min, max; final Map<BlockPos, Cell> cells = new HashMap<>();
        final List<BlockPos> broken = new ArrayList<>(); final Map<BlockPos, Integer> waiting = new HashMap<>();
        Pose pose; int delay; double reach = 4.32;
        BlockPos barrier, water; boolean sealable;
        World(BlockPos min, BlockPos max) { this.min = min; this.max = max; }
        boolean inside(BlockPos p) { return p.getX() >= min.getX() && p.getX() <= max.getX() && p.getY() >= min.getY() && p.getY() <= max.getY() && p.getZ() >= min.getZ() && p.getZ() <= max.getZ(); }
        public Cell cell(BlockPos p) { return cells.getOrDefault(p, p.getY() < min.getY() ? Cell.PROTECTED : inside(p) ? Cell.SOLID : Cell.AIR); }
        void clearColumn(int x, int z) { for (int y = min.getY(); y <= max.getY(); y++) cells.put(new BlockPos(x, y, z), Cell.AIR); }
        public boolean opensLiquid(BlockPos p) { return p.equals(barrier) && water != null && cell(water) == Cell.LIQUID; }
        public BlockPos sealableSideWater(BlockPos p) { return sealable && opensLiquid(p) ? water : null; }
        public boolean canMine(BlockPos target) {
            double ex = pose.x(), ey = pose.y() + 1.62, ez = pose.z();
            for (double sx : new double[]{.08, .5, .92}) for (double sy : new double[]{.08, .5, .92}) for (double sz : new double[]{.08, .5, .92}) {
                double dx = target.getX() + sx - ex, dy = target.getY() + sy - ey, dz = target.getZ() + sz - ez;
                double length = Math.sqrt(dx * dx + dy * dy + dz * dz);
                int steps = Math.max(1, (int)Math.ceil(length / .025));
                for (int i = 1; i <= steps && length * i / steps <= reach; i++) {
                    double t = i / (double)steps;
                    var hit = new BlockPos((int)Math.floor(ex + dx * t), (int)Math.floor(ey + dy * t), (int)Math.floor(ez + dz * t));
                    if (cell(hit) != Cell.AIR) { if (hit.equals(target)) return true; break; }
                }
            }
            return false;
        }
        void serverTick() {
            waiting.replaceAll((p, ticks) -> ticks - 1);
            for (BlockPos p : new ArrayList<>(waiting.keySet())) if (waiting.get(p) <= 0) { waiting.remove(p); if (cell(p) == Cell.SOLID) remove(p); }
        }
        void mine(BlockPos p) {
            assertTrue(inside(p), "Never excavate below the floor or outside the selected volume: " + p);
            assertEquals(Cell.SOLID, cell(p)); assertTrue(canMine(p), "Real ray/reach failed for " + p + " from " + pose);
            if (delay == 0) remove(p); else waiting.putIfAbsent(p, delay);
        }
        void remove(BlockPos p) { cells.put(p.immutable(), Cell.AIR); broken.add(p.immutable()); }
    }
    private static final class Sim {
        final BlockPos min, max; final World world; BorerAreaPlan plan; Pose pose; float yaw; int ticks;
        final List<Trace> traces = new ArrayList<>(); final List<BlockPos> bottomVisits = new ArrayList<>();
        Sim(BlockPos min, BlockPos max, boolean horizontal) { this(min, max, horizontal, new Pose(min.getX() + .5, max.getY() + 1.25, min.getZ() + .5, 0, 0, 0)); }
        Sim(BlockPos min, BlockPos max, boolean horizontal, Pose pose) { this.min = min; this.max = max; this.pose = pose; world = new World(min, max); plan = new BorerAreaPlan(min, max, pose, horizontal); }
        long verticalMoves() { return traces.stream().filter(t -> t.command.action() == Action.UP || t.command.action() == Action.DOWN).count(); }
        void finish() { until(() -> plan.phase() == Phase.DONE || plan.phase() == Phase.BLOCKED); assertEquals(Phase.DONE, plan.phase(), () -> traces.getLast().toString()); assertEquals(plan.total(), plan.completed() + plan.skipped()); }
        void until(BooleanSupplier condition) { int end = ticks + 200_000; while (!condition.getAsBoolean() && ticks < end) tick(); assertTrue(condition.getAsBoolean(), () -> "No convergence: " + traces.getLast()); }
        Command tick() {
            world.serverTick(); world.pose = pose; Command command = plan.step(world, pose); ticks++;
            traces.add(new Trace(plan.phase(), pose, command));
            if (plan.reachedBottomThisStep()) { assertEquals(min.getY(), (int)Math.floor(pose.y())); bottomVisits.add(plan.column()); }
            if (command.action() == Action.MINE || command.action() == Action.MINE_DOWN) world.mine(command.block());
            var input = BorerAreaMotion.of(command, pose, yaw); yaw = input.yaw();
            double radians = Math.toRadians(yaw), f = input.forward() ? input.speed() * 10 : 0;
            double dx = -Math.sin(radians) * f, dz = Math.cos(radians) * f, dy = (input.up() ? 1 : input.down() ? -1 : 0) * input.speed() * 5;
            int steps = Math.max(1, (int)Math.ceil(Math.max(Math.abs(dy), Math.max(Math.abs(dx), Math.abs(dz))) / .025));
            for (int i = 1; i <= steps; i++) {
                double t = i / (double)steps, x = pose.x() + dx * t, y = pose.y() + dy * t, z = pose.z() + dz * t;
                for (int bx = (int)Math.floor(x - .299); bx <= (int)Math.floor(x + .299); bx++)
                    for (int by = (int)Math.floor(y + .001); by <= (int)Math.floor(y + 1.799); by++)
                        for (int bz = (int)Math.floor(z - .299); bz <= (int)Math.floor(z + .299); bz++)
                            assertEquals(Cell.AIR, world.cell(new BlockPos(bx, by, bz)), "Body collision: " + traces.getLast());
            }
            pose = new Pose(pose.x() + dx, pose.y() + dy, pose.z() + dz, dx, dy, dz); return command;
        }
    }
}
