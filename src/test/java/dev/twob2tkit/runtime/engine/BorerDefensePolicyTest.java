package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
class BorerDefensePolicyTest {
	@Test void visibleIdleMobsDoNotInterruptMiningEvenAtCloseRange() {
		for (double distance : new double[]{2, 8, 24, 32})
			assertFalse(BorerDefensePolicy.engaged(true, false, false, false, false, false, false, distance, 0));
	}
	@Test void knownTargetsOfOtherPlayersAreIgnored() {
		assertFalse(BorerDefensePolicy.engaged(true, false, true, false, true, true, false, 6, 0));
	}
	@Test void approachingNearbyMobIsAThreatButDistantOrHighMobsAreNot() {
		assertTrue(BorerDefensePolicy.engaged(true, false, false, false, true, false, false, 6, 0));
		assertFalse(BorerDefensePolicy.engaged(true, false, false, false, true, false, false, 20, 0));
		assertFalse(BorerDefensePolicy.engaged(true, false, false, false, true, false, false, 8, 7));
	}
	@Test void stationaryShooterAimingOrHavingJustHitUsStillQualifies() {
		assertTrue(BorerDefensePolicy.engaged(true, false, false, false, false, true, false, 28, 5));
		assertTrue(BorerDefensePolicy.engaged(true, true, false, false, false, false, false, 28, 5));
	}
	@Test void unseenMobsDoNotQualifyMerelyByWalking() {
		assertFalse(BorerDefensePolicy.engaged(false, false, false, true, true, false, false, 6, 0));
	}
	@Test void idleCreeperCannotPreemptAnActiveArcher() {
		var candidates = new java.util.ArrayList<BorerDefensePolicy.Candidate>();
		if (BorerDefensePolicy.engaged(true, false, false, false, false, false, false, 5, 0)) candidates.add(new BorerDefensePolicy.Candidate(1, 0, 5));
		if (BorerDefensePolicy.engaged(true, true, false, false, false, false, false, 25, 0)) candidates.add(new BorerDefensePolicy.Candidate(2, 1, 25));
		assertEquals(2, BorerDefensePolicy.choose(candidates, 1));
	}
	@Test void approachingUsesMonsterMotionNotPlayerMovementOrRandomSidewaysMotion() {
		assertFalse(BorerDefensePolicy.approaching(0, 0, -3, 0), "Flying toward a stationary mob must not trigger combat");
		assertFalse(BorerDefensePolicy.approaching(.01, 0, 3, 0));
		assertFalse(BorerDefensePolicy.approaching(0, .4, 3, 0));
		assertFalse(BorerDefensePolicy.approaching(-.4, 0, 3, 0));
		assertTrue(BorerDefensePolicy.approaching(.4, 0, 3, 0));
	}
	@Test void imminentExplosionIsProtectedButFarOrIdleCreeperIsNotAnEmergency() {
		assertFalse(BorerDefensePolicy.blastThreat(false, false, 2));
		assertFalse(BorerDefensePolicy.blastThreat(true, false, 18));
		assertTrue(BorerDefensePolicy.blastThreat(true, false, 4));
		assertTrue(BorerDefensePolicy.blastThreat(true, true, 10));
		assertTrue(BorerDefensePolicy.engaged(false, false, true, false, false, false, true, 4, 0));
	}
	@Test void projectileComingAtPlayerCountsButOneFlyingAwayOrAlreadyLandedDoesNot() {
		var box = new net.minecraft.world.phys.AABB(-.3, 0, -.3, .3, 1.8, .3);
		var origin = new net.minecraft.world.phys.Vec3(6, 1, 0);
		assertTrue(BorerEngagement.incoming(box, origin, new net.minecraft.world.phys.Vec3(-1, 0, 0)));
		assertFalse(BorerEngagement.incoming(box, origin, new net.minecraft.world.phys.Vec3(1, 0, 0)));
		assertFalse(BorerEngagement.incoming(box, origin, net.minecraft.world.phys.Vec3.ZERO));
	}
	@Test void disappearingThreatDoesNotRemainEligibleJustBecauseItWasPreviouslyChosen() {
		assertTrue(BorerDefensePolicy.engaged(true, false, false, false, true, false, false, 6, 0));
		assertFalse(BorerDefensePolicy.engaged(true, false, false, false, false, false, false, 6, 0));
		assertEquals(-1, BorerDefensePolicy.choose(List.of(), 3));
	}
	@Test void creeperPreemptsAnArcherEvenWhenAnotherMobIsCloser() {
		var list = List.of(new BorerDefensePolicy.Candidate(1, 2, 2), new BorerDefensePolicy.Candidate(2, 1, 12), new BorerDefensePolicy.Candidate(3, 0, 18));
		assertEquals(3, BorerDefensePolicy.choose(list, 2));
		assertEquals(2, BorerDefensePolicy.choose(list.subList(0, 2), 1));
		assertEquals(1, BorerDefensePolicy.choose(list.subList(0, 1), 2));
	}
	@Test void similarArcherDistancesDoNotRepeatedlyCancelTheDraw() {
		assertEquals(2, BorerDefensePolicy.choose(List.of(new BorerDefensePolicy.Candidate(1, 1, 10), new BorerDefensePolicy.Candidate(2, 1, 11)), 2));
		assertEquals(-1, BorerDefensePolicy.choose(List.of(), 2));
	}
	@Test void theArcherActuallyShootingUsWinsOverAnIdleBowSkeleton() {
		assertEquals(2, BorerDefensePolicy.choose(List.of(new BorerDefensePolicy.Candidate(1, 1, 8, false), new BorerDefensePolicy.Candidate(2, 1, 25, true)), 1));
	}
	@Test void ignoresPlayersDeadTargetsAndWallsButFindsDistantShooters() {
		assertTrue(BorerDefensePolicy.eligible(true, true, true, 1, 32));
		assertFalse(BorerDefensePolicy.eligible(false, true, true, 1, 12));
		assertFalse(BorerDefensePolicy.eligible(true, false, true, 1, 12));
		assertFalse(BorerDefensePolicy.eligible(true, true, false, 1, 12));
		assertFalse(BorerDefensePolicy.eligible(true, true, true, 2, 32));
	}
	@Test void releasesOnlyAFullDrawOnTheCurrentVerifiedTarget() {
		for (int t = 0; t < 20; t++) assertFalse(BorerDefensePolicy.releaseArrow(t, true, true));
		assertTrue(BorerDefensePolicy.releaseArrow(20, true, true));
		assertFalse(BorerDefensePolicy.releaseArrow(30, false, true));
		assertFalse(BorerDefensePolicy.releaseArrow(30, true, false));
	}
}
