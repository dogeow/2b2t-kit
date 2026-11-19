package dev.twob2tkit.runtime.engine;

import java.util.EnumMap;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.Vec3;

/** A retreat only progresses when the character actually moves toward the selected exit. */
final class MagmaExitProgress {
	private final EnumMap<Direction,Integer> retryAt = new EnumMap<>(Direction.class);
	private BlockPos cell;
	private Direction direction;
	private int lastTick, since;
	private Vec3 anchor;

	void observe(BlockPos feet, Vec3 position, int tick) {
		if (!feet.equals(cell) || tick < lastTick || tick - lastTick > 1) {
			cell = feet.immutable();
			direction = null;
			retryAt.clear();
		}
		lastTick = tick;
		if (direction == null) return;
		double distance = (position.x-anchor.x)*direction.getStepX() + (position.z-anchor.z)*direction.getStepZ();
		if (distance >= .08) {
			since = tick;
			anchor = position;
		} else if (tick-since >= 20) {
			retryAt.put(direction,tick+80);
			direction = null;
		}
	}

	boolean blocked(Direction dir, int tick) { return tick < retryAt.getOrDefault(dir,0); }

	void attempt(Direction dir, Vec3 position, int tick) {
		if (dir == direction) return;
		direction = dir;
		anchor = position;
		since = tick;
	}
}
