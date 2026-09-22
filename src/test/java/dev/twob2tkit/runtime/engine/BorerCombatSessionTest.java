package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class BorerCombatSessionTest {
	private final BorerCombatSession<String> session = new BorerCombatSession<>();
	private final UUID creeper = UUID.fromString("00000000-0000-0000-0000-000000000001");
	private final UUID archer = UUID.fromString("00000000-0000-0000-0000-000000000002");
	private void see(long tick, UUID id, boolean engaged, boolean dead, boolean clearShot, float hp) {
		session.beginTick(tick);
		session.observe(id, id.toString(), engaged, dead, clearShot, hp);
	}
	@Test void liveLogCreeperStopAndStartSequenceDoesNotReleaseMining() {
		// 13:08:33 acquired; 34 not approaching; 35/36 alternates; a shot at 42 is not a kill at 43.
		for (int second = 33; second <= 45; second++) {
			see(second * 20L, creeper, second == 33 || second == 35 || second == 36, false, true, second < 43 ? 20 : 8);
			assertTrue(session.pending(), "mining must stay suspended at second " + second);
			assertTrue(session.canAttack(creeper), "remaining health must get the next attack");
		}
		see(46 * 20L, creeper, false, true, false, 0);
		assertFalse(session.pending());
	}
	@Test void idleMonstersDoNotStartCombat() {
		see(0, creeper, false, false, true, 20);
		assertFalse(session.pending());
	}
	@Test void knockbackAndBriefLostSightKeepTheFightButDisallowShootingThroughWalls() {
		see(0, creeper, true, false, true, 20);
		see(10, creeper, false, false, false, 10);
		assertTrue(session.pending()); assertFalse(session.canAttack(creeper));
		see(20, creeper, false, false, true, 10);
		assertTrue(session.canAttack(creeper));
	}
	@Test void missingEntityAndRemovedEntityAreNotADeathConfirmation() {
		see(0, creeper, true, false, true, 20);
		session.beginTick(1); // Chunk/entity absent in this snapshot.
		assertTrue(session.pending()); assertFalse(session.canAttack(creeper));
		see(2, creeper, false, false, false, 20); // Unloaded reference: isAlive false, health still positive.
		assertTrue(session.pending()); assertFalse(session.canAttack(creeper));
	}
	@Test void identitySurvivesRetrackingAndDoesNotDependOnRecycledNetworkIds() {
		see(0, creeper, true, false, true, 20);
		session.beginTick(1);
		session.observe(archer, "recycled network id", false, true, false, 0);
		assertTrue(session.contains(creeper));
		session.observe(creeper, "new client reference", false, false, true, 10);
		assertEquals(java.util.List.of("new client reference"), session.targets());
		assertTrue(session.canAttack(creeper));
	}
	@Test void killingOneOfTwoEngagedCreepersCannotResumeWork() {
		see(0, creeper, true, false, true, 20);
		session.observe(archer, "second creeper", true, false, true, 20);
		see(40, creeper, false, true, false, 0);
		assertTrue(session.pending()); assertTrue(session.contains(archer));
		see(41, archer, false, false, true, 20);
		assertTrue(session.canAttack(archer));
		see(80, archer, false, true, false, 0);
		assertFalse(session.pending());
	}
	@Test void preemptedArcherRemainsRememberedWhileACreeperIsDealtWith() {
		see(0, archer, true, false, true, 20);
		see(1, creeper, true, false, true, 20);
		see(40, creeper, false, true, false, 0);
		assertTrue(session.contains(archer));
		see(41, archer, false, false, true, 20);
		assertTrue(session.canAttack(archer));
	}
	@Test void thirtySecondsWithoutConfirmedDamageStopsRetriesButNeverReleasesMining() {
		for (int tick = 0; tick <= 600; tick++) {
			see(tick, creeper, true, false, true, 20);
			assertEquals(tick < 600, session.canAttack(creeper));
			assertTrue(session.pending());
		}
		assertTrue(session.timedOut());
		see(601, creeper, true, false, true, 20);
		assertFalse(session.canAttack(creeper), "repeated aggression cannot reset the failed-attack budget");
	}
	@Test void onlyConfirmedHealthProgressRenewsTheAttackBudget() {
		see(0, creeper, true, false, true, 20);
		see(590, creeper, false, false, true, 8);
		see(600, creeper, false, false, true, 8);
		assertTrue(session.canAttack(creeper));
		see(1190, creeper, false, false, true, 8);
		assertFalse(session.canAttack(creeper)); assertTrue(session.pending());
	}
	@Test void healingAndRepeatedSightCannotKeepAFailedAttackLoopRunning() {
		see(0, creeper, true, false, true, 10);
		see(100, creeper, true, false, true, 20);
		see(599, creeper, true, false, true, 10);
		see(600, creeper, true, false, true, 10);
		assertFalse(session.canAttack(creeper));
	}
	@Test void menusAndMealsSuspendControlAndBudgetWithoutForgettingTheThreat() {
		see(0, creeper, true, false, true, 20);
		session.pause(100);
		assertTrue(session.pending()); assertFalse(session.canAttack(creeper));
		session.pause(1000); // Repeated open-menu ticks must not overwrite the initial pause time.
		see(2000, creeper, false, false, true, 20);
		assertTrue(session.canAttack(creeper));
		see(2499, creeper, false, false, true, 20);
		assertTrue(session.canAttack(creeper));
		see(2500, creeper, false, false, true, 20);
		assertFalse(session.canAttack(creeper));
	}
	@Test void deathDuringFoodOrMenuPauseIsRecognizedWhenControlResumes() {
		see(0, creeper, true, false, true, 20);
		session.pause(1);
		see(200, creeper, false, true, false, 0);
		assertFalse(session.pending());
	}
	@Test void manualOrEmergencyCancellationReleasesEveryLatch() {
		see(0, creeper, true, false, true, 20);
		session.pause(5); session.clear();
		assertFalse(session.pending()); assertTrue(session.targets().isEmpty());
		see(10, creeper, false, false, true, 20);
		assertFalse(session.pending());
		see(11, creeper, true, false, true, 20);
		assertTrue(session.canAttack(creeper));
	}
 @Test void verifiedRepositionAllowsOnlyTwoRetriesAndNeverCompletesTheFight(){
  see(0,creeper,true,false,true,20);see(600,creeper,false,false,false,20);
  assertFalse(session.repositioned(creeper));
  see(601,creeper,false,false,true,20);assertTrue(session.repositioned(creeper));assertTrue(session.canAttack(creeper));assertTrue(session.pending());
  see(1201,creeper,false,false,true,20);assertTrue(session.repositioned(creeper));
  see(1801,creeper,false,false,true,20);assertFalse(session.repositioned(creeper));assertFalse(session.canAttack(creeper));assertTrue(session.pending());
 }

}
