package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerMineAheadTest {
	private final BlockPos upper = new BlockPos(1,11,0), lower = new BlockPos(1,10,0);
	@Test void refusedBlockIsReportedForAnotherDigWhileTheOtherConfirms() {
		var ahead = new BorerMineAhead();
		assertTrue(ahead.observe(Set.of(upper,lower),p->true,0).isEmpty());
		assertEquals(List.of(lower),ahead.observe(Set.of(),p->p.equals(upper),8));
		assertNull(ahead.exhausted());
	}
	@Test void repeatedRefusalGivesUpButAConfirmedBreakForgivesEarlierOnes() {
		var ahead = new BorerMineAhead();
		for (int n=0;n<2;n++) { ahead.observe(Set.of(lower),p->true,n*10); ahead.observe(Set.of(),p->false,n*10+5); }
		assertNull(ahead.exhausted());
		ahead.observe(Set.of(lower),p->true,20); ahead.observe(Set.of(),p->true,25);
		for (int n=3;n<6;n++) { ahead.observe(Set.of(lower),p->true,n*10); ahead.observe(Set.of(),p->false,n*10+5); }
		assertEquals(lower,ahead.exhausted());
	}
	@Test void timeoutIsPerBlockSoContinuousDiggingNeverLooksStuck() {
		var ahead = new BorerMineAhead();
		for (int tick=0;tick<400;tick++) {
			ahead.observe(Set.of(new BlockPos(tick/10,10,0)),p->true,tick);
			assertFalse(ahead.expired(tick));
		}
		ahead.clear();
		ahead.observe(Set.of(upper),p->true,0); ahead.observe(Set.of(upper),p->true,100);
		assertTrue(ahead.expired(100));
	}
	@Test void foreignOrTooManyPendingBreaksFallBackToWaiting() {
		assertTrue(BorerMineAhead.allowed(Set.of(upper),Set.of(upper,lower)));
		assertFalse(BorerMineAhead.allowed(Set.of(upper),Set.of(lower)));
		var many = new HashSet<BlockPos>();
		for (int i=0;i<BorerMineAhead.LIMIT;i++) many.add(upper.east(i));
		assertFalse(BorerMineAhead.allowed(many,many));
	}
}
