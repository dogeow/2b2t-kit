package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import java.util.Random;

import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Action;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Command;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Pose;
import static org.junit.jupiter.api.Assertions.*;

final class BorerAreaMotionTest {
	private static final Pose POSE = new Pose(-12.3, 50.25, 19.8, 0, 0, 0);

	@Test
	void fourHorizontalDirectionsDecodeCorrectlyRegardlessOfPreviousYaw() {
		Random random = new Random(0x2b2f);
		for (int sample = 0; sample < 200; sample++) {
			float previousYaw = random.nextFloat() * 1440 - 720;
			for (int direction : new int[]{-1, 1}) {
				for (double distance : new double[]{0.1, 3.0}) {
					BorerAreaMotion.Input x = BorerAreaMotion.of(command(Action.X, direction * distance, 0, 0), POSE, previousYaw);
					assertTrue(x.forward());
					assertFalse(x.up());
					assertFalse(x.down());
					assertEquals(direction, -Math.sin(Math.toRadians(x.yaw())), 1e-12);
					assertEquals(0, Math.cos(Math.toRadians(x.yaw())), 1e-12);
					BorerAreaMotion.Input z = BorerAreaMotion.of(command(Action.Z, 0, 0, direction * distance), POSE, previousYaw);
					assertTrue(z.forward());
					assertFalse(z.up());
					assertFalse(z.down());
					assertEquals(0, -Math.sin(Math.toRadians(z.yaw())), 1e-12);
					assertEquals(direction, Math.cos(Math.toRadians(z.yaw())), 1e-12);
				}
			}
		}
	}

	@Test
	void verticalMotionRetainsYawAndNeverEnablesForwardOrBothVerticalKeys() {
		for (float yaw : new float[]{-719, -90, 0, 127.5F, 360}) {
			BorerAreaMotion.Input up = BorerAreaMotion.of(command(Action.UP, 0, 3, 0), POSE, yaw);
			assertEquals(yaw, up.yaw());
			assertTrue(up.up());
			assertFalse(up.down());
			assertFalse(up.forward());
			BorerAreaMotion.Input down = BorerAreaMotion.of(command(Action.DOWN, 0, -3, 0), POSE, yaw);
			assertEquals(yaw, down.yaw());
			assertTrue(down.down());
			assertFalse(down.up());
			assertFalse(down.forward());
		}
	}

	@Test
	void nonMovementActionsReleaseAllMovementAndSetZeroSpeed() {
		for (Action action : new Action[]{Action.WAIT, Action.MINE, Action.BLOCKED, Action.DONE}) {
			BorerAreaMotion.Input input = BorerAreaMotion.of(command(action, 2, 2, 2), POSE, 46F);
			assertFalse(input.forward());
			assertFalse(input.up());
			assertFalse(input.down());
			assertEquals(0, input.speed());
			assertEquals(46F, input.yaw());
		}
	}

	@Test
	void precisionAndTravelSpeedsStayWithinThePlannersCollisionSweepAtBothFlightScales() {
		for (int direction : new int[]{-1, 1}) {
			for (double distance : new double[]{0.086, 0.79, 0.81, 29}) {
				for (Action action : new Action[]{Action.X, Action.Z, Action.UP, Action.DOWN}) {
					Command command = command(action, direction * distance, direction * distance, direction * distance);
					BorerAreaMotion.Input input = BorerAreaMotion.of(command, POSE, 83F);
					int keys = (input.forward() ? 1 : 0) + (input.up() ? 1 : 0) + (input.down() ? 1 : 0);
					assertEquals(1, keys);
					assertTrue(input.speed() > 0);
					boolean horizontal = action == Action.X || action == Action.Z;
					if (horizontal) {
						assertTrue(input.speed() * 10 <= 0.25);
						assertTrue(input.speed() * 15 <= 0.25);
					} else assertTrue(input.speed() * 5 <= 1.20);
				}
			}
		}
	}
	@Test
	void fastAscentBrakesNearTopAndContinuousMiningOnlyDescends() {
		var far = BorerAreaMotion.of(command(Action.UP, 0, 50, 0), POSE, 42);
		var near = BorerAreaMotion.of(command(Action.UP, 0, 0.3, 0), POSE, 42);
		assertEquals(1.0, far.speed() * 5, 1e-9);
		assertTrue(near.speed() < far.speed());
		var mine = BorerAreaMotion.of(command(Action.MINE_DOWN, 0, -0.5, 0), POSE, 42);
		assertTrue(mine.down());
		assertFalse(mine.forward());
		assertFalse(mine.up());
		assertTrue(mine.speed() * 5 < 0.5);
	}

	private static Command command(Action action, double dx, double dy, double dz) {
		return new Command(action, null, POSE.x() + dx, POSE.y() + dy, POSE.z() + dz, "test");
	}
}
