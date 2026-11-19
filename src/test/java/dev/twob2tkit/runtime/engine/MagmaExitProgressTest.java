package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MagmaExitProgressTest {
	@Test void sidewaysDriftCannotKeepAStalledSouthExitAlive() {
		var progress = new MagmaExitProgress();
		for (int t=0;t<20;t++) {
			Vec3 pos = new Vec3(.5+t*.01, 0, .45);
			progress.observe(BlockPos.ZERO,pos,t);
			progress.attempt(Direction.SOUTH,pos,t);
		}
		progress.observe(BlockPos.ZERO,new Vec3(.7,0,.45),20);
		assertTrue(progress.blocked(Direction.SOUTH,20));
		assertFalse(progress.blocked(Direction.NORTH,20));
	}
}
