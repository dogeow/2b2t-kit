package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.planter.PlanterPolicy;

final class PlanterPolicyTest {
	@Test
	void farmingNeverJumpsOrFarmlandTurnsToDirt() {
		assertFalse(PlanterPolicy.shouldJumpWhileFarming());
	}

	@Test
	void harvestBreaksCropWithoutAttackKeyAndSkipsVillagers() {
		assertFalse(PlanterPolicy.harvestWithAttackKey());
		assertTrue(PlanterPolicy.skipHarvestWhenEntityInWay(true));
		assertFalse(PlanterPolicy.skipHarvestWhenEntityInWay(false));
		assertTrue(PlanterPolicy.harvestIfRayHitsCrop(true));
		assertFalse(PlanterPolicy.harvestIfRayHitsCrop(false));
	}
}
