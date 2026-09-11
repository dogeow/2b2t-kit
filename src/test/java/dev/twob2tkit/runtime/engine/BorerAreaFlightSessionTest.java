package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

final class BorerAreaFlightSessionTest {
	@org.junit.jupiter.api.io.TempDir java.nio.file.Path temp;

	@Test void repairsLegacyPersistedHoverWithoutEnablingFlight() {
		Fixture f = new Fixture();
		f.flight.mode.set(Mode.Velocity); f.flight.noSneak.set(true); f.flight.speed.set(0.0);
		BorerAreaFlightSession session = f.session();
		assertNotNull(session.prepare(temp.resolve("speed.bak")));
		assertEquals(0.1, f.flight.speed.get());
		assertFalse(f.flight.active);
		assertNull(session.acquire()); session.hover(); session.close();
		assertEquals(0.1, f.flight.speed.get());
	}

	@Test void idlePreparationDoesNotTouchManualNonzeroSpeedOrKeys() {
		Fixture f = new Fixture();
		f.flight.speed.set(0.37); f.flight.active = true;
		assertNull(f.session().prepare(temp.resolve("speed.bak")));
		assertEquals(0.37, f.flight.speed.get());
		assertEquals(0, f.flight.toggles);
		assertTrue(f.flight.active);
	}

	@Test void recoversOriginalSpeedAfterLosingTheSessionWithoutClose() {
		Fixture f = new Fixture();
		var path = temp.resolve("speed.bak");
		BorerAreaFlightSession old = f.session();
		old.prepare(path); assertNull(old.acquire()); old.speed(0.02); old.hover();
		assertEquals(0.0, f.flight.speed.get());
		assertNotNull(f.session().prepare(path));
		assertEquals(0.12, f.flight.speed.get());
	}

	@Test void normalCloseRetainsReceiptForMeteorSnapshotSavedBeforeClose() throws Exception {
		Fixture f = new Fixture();
		var path = temp.resolve("speed.bak");
		BorerAreaFlightSession old = f.session();
		old.prepare(path); assertNull(old.acquire()); old.speed(0.02); old.close();
		assertEquals(0.12, f.flight.speed.get());
		assertTrue(java.nio.file.Files.exists(path));
		f.flight.speed.set(0.02); // Simulate Minecraft restart loading Meteor's earlier snapshot.
		assertNotNull(f.session().prepare(path));
		assertEquals(0.12, f.flight.speed.get());
	}

	@Test void recoveryPreservesManualSpeedChangedAfterTheLastAutomatedWrite() {
		Fixture f = new Fixture();
		var path = temp.resolve("speed.bak");
		BorerAreaFlightSession old = f.session();
		old.prepare(path); assertNull(old.acquire()); old.speed(0.02);
		f.flight.speed.set(0.37);
		assertNull(f.session().prepare(path));
		assertEquals(0.37, f.flight.speed.get());
	}

	@Test void backupFailurePreventsBorrowingFlight() throws Exception {
		Fixture f = new Fixture();
		var path = temp.resolve("speed.bak");
		BorerAreaFlightSession session = f.session();
		session.prepare(path);
		java.nio.file.Files.createDirectory(path);
		java.nio.file.Files.writeString(path.resolve("block"), "unrelated");
		assertNotNull(session.acquire());
		f.assertOriginalSettings();
		assertFalse(f.flight.active);
	}

	@Test void preparationDuringAnOwnedSessionCannotUndoHover() {
		Fixture f = new Fixture();
		var path = temp.resolve("speed.bak");
		BorerAreaFlightSession session = f.session();
		session.prepare(path); assertNull(session.acquire());
		assertNull(session.prepare(path));
		assertEquals(0.0, f.flight.speed.get());
		session.close();
		f.assertOriginalSettings();
	}

	@Test
	void digUsesGravityAndReturnOrEmergencyEnablesFlightAgain() {
		Fixture f = new Fixture();
		BorerAreaFlightSession session = f.session();
		assertNull(session.acquire());
		session.digOnFoot();
		assertFalse(f.flight.active);
		assertNull(session.acquire());
		session.speed(0);
		assertFalse(f.flight.active);
		session.fly();
		assertTrue(f.flight.active);
		session.digOnFoot();
		session.hover();
		assertTrue(f.flight.active);
		session.close();
		assertFalse(f.flight.active);
	}
	@Test
	void stoppingGroundDigRestoresOriginallyEnabledFlight() {
		Fixture f = new Fixture();
		f.flight.active = true;
		BorerAreaFlightSession session = f.session();
		assertNull(session.acquire());
		session.digOnFoot();
		assertFalse(f.flight.active);
		session.close();
		assertTrue(f.flight.active);
		f.assertOriginalSettings();
	}
	@Test
	void borrowsExistingFlightAndRestoresEveryOriginalSetting() {
		Fixture fixture = new Fixture();
		fixture.flight.active = true;
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		assertEquals(Mode.Velocity, fixture.flight.mode.get());
		assertEquals(0.0, fixture.flight.speed.get());
		assertFalse(fixture.flight.verticalSpeedMatch.get());
		assertTrue(fixture.flight.noSneak.get());
		session.speed(0.03);
		assertNull(session.acquire());
		assertEquals(0.03, fixture.flight.speed.get());
		session.close();
		session.close();
		fixture.assertOriginalSettings();
		assertTrue(fixture.flight.active);
		assertEquals(0, fixture.flight.toggles);
	}

	@Test
	void onlyTurnsOffFlightThatThisSessionEnabled() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		assertTrue(fixture.flight.active);
		session.close();
		assertFalse(fixture.flight.active);
		assertEquals(2, fixture.flight.toggles);
		fixture.assertOriginalSettings();
	}

	@Test
	void airborneReleaseRestoresSettingsButKeepsItsFlightThroughLaterClose() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		session.speed(0.02);
		assertTrue(session.closeKeepingFlight());
		fixture.assertOriginalSettings();
		assertTrue(fixture.flight.active);
		assertEquals(1, fixture.flight.toggles);
		session.close();
		assertFalse(session.closeKeepingFlight());
		assertTrue(fixture.flight.active);
		assertEquals(1, fixture.flight.toggles);
	}

	@Test
	void airborneReleaseDoesNotClaimOwnershipOfPreviouslyEnabledFlight() {
		Fixture fixture = new Fixture();
		fixture.flight.active = true;
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		assertFalse(session.closeKeepingFlight());
		fixture.assertOriginalSettings();
		assertTrue(fixture.flight.active);
		assertEquals(0, fixture.flight.toggles);
	}

	@Test
	void airborneReleaseDoesNotReenableManuallyDisabledFlightOrOverwriteUserSpeed() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		fixture.flight.active = false;
		fixture.flight.speed.set(0.21);
		assertFalse(session.closeKeepingFlight());
		assertFalse(fixture.flight.active);
		assertEquals(1, fixture.flight.toggles);
		assertEquals(0.21, fixture.flight.speed.get());
		assertEquals(Mode.Abilities, fixture.flight.mode.get());
		assertTrue(fixture.flight.verticalSpeedMatch.get());
		assertFalse(fixture.flight.noSneak.get());
	}

	@Test
	void preservesEachSettingTheUserChangedAfterAcquisition() {
		Fixture fixture = new Fixture();
		fixture.flight.active = true;
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		session.speed(0.03);
		fixture.flight.speed.set(0.17);
		fixture.flight.mode.set(Mode.Other);
		session.close();
		assertEquals(0.17, fixture.flight.speed.get());
		assertEquals(Mode.Other, fixture.flight.mode.get());
		assertTrue(fixture.flight.verticalSpeedMatch.get());
		assertFalse(fixture.flight.noSneak.get());
		assertTrue(fixture.flight.active);
	}

	@Test
	void rejectsScaffoldWithoutWritingAnySettingsOrTogglingModules() {
		Fixture fixture = new Fixture();
		fixture.scaffold.active = true;
		assertTrue(fixture.session().acquire().contains("Scaffold"));
		fixture.assertOriginalSettings();
		assertEquals(0, fixture.flight.toggles);
		assertTrue(fixture.scaffold.active);
	}

	@Test
	void rejectsEveryAntiAfkMovementOrRotationAction() {
		for (int action = 0; action < 4; action++) {
			Fixture fixture = new Fixture();
			fixture.antiAfk.active = true;
			fixture.antiAfk.actions().get(action).set(true);
			assertTrue(fixture.session().acquire().contains("AntiAFK"));
			fixture.assertOriginalSettings();
			assertTrue(fixture.antiAfk.active);
			assertEquals(0, fixture.flight.toggles);
		}
	}

	@Test
	void permitsActiveAntiAfkWithoutInputActions() {
		Fixture fixture = new Fixture();
		fixture.antiAfk.active = true;
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		session.close();
		assertTrue(fixture.antiAfk.active);
	}

	@Test
	void rejectedSettingRollsBackEarlierWritesBeforeEnablingFlight() {
		Fixture fixture = new Fixture();
		fixture.flight.verticalSpeedMatch.reject = false;
		assertNotNull(fixture.session().acquire());
		fixture.assertOriginalSettings();
		assertFalse(fixture.flight.active);
		assertEquals(0, fixture.flight.toggles);
	}

	@Test
	void throwingSettingCallbackRollsBackTheValueItAlreadyChanged() {
		Fixture fixture = new Fixture();
		fixture.flight.verticalSpeedMatch.throwAfterSet = false;
		assertNotNull(fixture.session().acquire());
		fixture.assertOriginalSettings();
		assertEquals(0, fixture.flight.toggles);
	}

	@Test
	void failingActivationRollsBackSettingsAndItsPartialToggle() {
		Fixture fixture = new Fixture();
		fixture.flight.throwNextToggle = true;
		assertNotNull(fixture.session().acquire());
		fixture.assertOriginalSettings();
		assertFalse(fixture.flight.active);
		assertEquals(2, fixture.flight.toggles);
	}

	@Test
	void rejectedLaterSpeedRestoresSettingsButKeepsFlight() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		session.speed(0.03);
		fixture.flight.speed.reject = 0.02;
		assertThrows(IllegalStateException.class, () -> session.speed(0.02));
		fixture.assertOriginalSettings();
		assertTrue(fixture.flight.active);
		session.close();
		assertTrue(fixture.flight.active);
		assertEquals(1, fixture.flight.toggles);
	}

	@Test
	void reacquisitionDetectsNewConflictsAndRollsBackOnlyOwnedValues() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		fixture.antiAfk.active = true;
		fixture.antiAfk.spin.set(true);
		assertTrue(session.acquire().contains("AntiAFK"));
		fixture.assertOriginalSettings();
		assertTrue(fixture.flight.active);
		assertEquals(1, fixture.flight.toggles);
		assertTrue(fixture.antiAfk.spin.get());
	}

	@Test
	void speedCannotOverrideAUsersMidSessionSettingChange() {
		Fixture fixture = new Fixture();
		fixture.flight.active = true;
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		fixture.flight.speed.set(0.24);
		assertThrows(IllegalStateException.class, () -> session.speed(0.02));
		assertEquals(0.24, fixture.flight.speed.get());
		assertEquals(Mode.Abilities, fixture.flight.mode.get());
		assertTrue(fixture.flight.active);
	}

	@Test
	void manuallyDisabledFlightIsNotToggledBackOnDuringCleanup() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		fixture.flight.active = false;
		assertNotNull(session.acquire());
		assertFalse(fixture.flight.active);
		assertEquals(1, fixture.flight.toggles);
		fixture.assertOriginalSettings();
	}

	@Test
	void missingMeteorIsAnExplicitFailureWithoutKeyboardFallback() {
		BorerAreaFlightSession session = new BorerAreaFlightSession(name -> null);
		assertTrue(session.acquire().contains("需要 Meteor Flight"));
		session.close();
	}

	@Test
	void hoverIsInertBeforeAcquisitionAndAfterClose() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		session.hover();
		fixture.assertOriginalSettings();
		assertEquals(0, fixture.flight.toggles);
		assertNull(session.acquire());
		session.close();
		session.hover();
		fixture.assertOriginalSettings();
		assertFalse(fixture.flight.active);
		assertEquals(2, fixture.flight.toggles);
	}

	@Test
	void hoverZerosSpeedAndStillRestoresTheOriginalOnClose() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		session.speed(0.02);
		session.hover();
		assertEquals(0.0, fixture.flight.speed.get());
		assertTrue(fixture.flight.active);
		session.close();
		fixture.assertOriginalSettings();
	}

	@Test
	void hoverFailureRestoresSettingsButKeepsFlightAndEndsTheLease() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		session.speed(0.02);
		fixture.flight.speed.reject = 0.0;
		assertThrows(IllegalStateException.class, session::hover);
		fixture.assertOriginalSettings();
		assertTrue(fixture.flight.active);
		session.hover();
		session.close();
		assertTrue(fixture.flight.active);
		assertEquals(1, fixture.flight.toggles);
	}

	@Test
	void restorationContinuesEvenIfOneSettingRejectsItsOriginalValue() {
		Fixture fixture = new Fixture();
		BorerAreaFlightSession session = fixture.session();
		assertNull(session.acquire());
		fixture.flight.noSneak.reject = false;
		session.close();
		assertEquals(Mode.Abilities, fixture.flight.mode.get());
		assertEquals(0.12, fixture.flight.speed.get());
		assertTrue(fixture.flight.verticalSpeedMatch.get());
		assertFalse(fixture.flight.active);
	}

	public enum Mode { Abilities, Velocity, Other }

	/** Public methods mirror Meteor's generic Setting API, including its boolean set result. */
	public static final class FakeSetting<T> {
		private T value;
		Object reject;
		Object throwAfterSet;

		FakeSetting(T value) { this.value = value; }
		public T get() { return value; }
		public boolean set(T next) {
			if (java.util.Objects.equals(next, reject)) return false;
			value = next;
			if (java.util.Objects.equals(next, throwAfterSet)) throw new IllegalStateException("callback failed");
			return true;
		}
	}

	public static class FakeModule {
		boolean active;
		int toggles;
		boolean throwNextToggle;
		public boolean isActive() { return active; }
		public void toggle() {
			active = !active;
			toggles++;
			if (throwNextToggle) {
				throwNextToggle = false;
				throw new IllegalStateException("activation failed");
			}
		}
	}

	public static final class FakeFlight extends FakeModule {
		private final FakeSetting<Mode> mode = new FakeSetting<>(Mode.Abilities);
		private final FakeSetting<Double> speed = new FakeSetting<>(0.12);
		private final FakeSetting<Boolean> verticalSpeedMatch = new FakeSetting<>(true);
		private final FakeSetting<Boolean> noSneak = new FakeSetting<>(false);
	}

	public static final class FakeAntiAfk extends FakeModule {
		private final FakeSetting<Boolean> jump = new FakeSetting<>(false);
		private final FakeSetting<Boolean> sneak = new FakeSetting<>(false);
		private final FakeSetting<Boolean> strafe = new FakeSetting<>(false);
		private final FakeSetting<Boolean> spin = new FakeSetting<>(false);
		java.util.List<FakeSetting<Boolean>> actions() { return java.util.List.of(jump, sneak, strafe, spin); }
	}

	private static final class Fixture {
		final FakeFlight flight = new FakeFlight();
		final FakeAntiAfk antiAfk = new FakeAntiAfk();
		final FakeModule scaffold = new FakeModule();
		BorerAreaFlightSession session() {
			return new BorerAreaFlightSession(name -> {
				if (name.endsWith(".Flight")) return flight;
				if (name.endsWith(".AntiAFK")) return antiAfk;
				if (name.endsWith(".Scaffold")) return scaffold;
				return null;
			});
		}
		void assertOriginalSettings() {
			assertEquals(Mode.Abilities, flight.mode.get());
			assertEquals(0.12, flight.speed.get());
			assertTrue(flight.verticalSpeedMatch.get());
			assertFalse(flight.noSneak.get());
		}
	}
}
