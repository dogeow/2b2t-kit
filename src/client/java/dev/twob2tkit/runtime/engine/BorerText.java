package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.Locale;

/** 盾构日志和 HUD 用的短文本，不持有引擎状态。 */
final class BorerText {
	private BorerText() {
	}

	/** 方块坐标短文本。 */
	static String block(BlockPos pos) {
		return pos.getX() + " " + pos.getY() + " " + pos.getZ();
	}

	/** 实体精确坐标短文本。 */
	static String precise(Entity entity) {
		return String.format(Locale.ROOT, "%.3f,%.3f,%.3f", entity.getX(), entity.getY(), entity.getZ());
	}

	/** 方向中文标签。 */
	static String direction(Direction dir) {
		return switch (dir) {
			case NORTH -> "北";
			case SOUTH -> "南";
			case EAST -> "东";
			case WEST -> "西";
			default -> dir.getName();
		};
	}

	/** 相对方位与距离短文本。 */
	static String compass(BlockPos from, BlockPos to) {
		int dx = to.getX() - from.getX();
		int dz = to.getZ() - from.getZ();
		int dist = (int) Math.round(Math.hypot(dx, dz));
		String dir;
		if (Math.abs(dx) > Math.abs(dz) * 2) dir = dx > 0 ? "东" : "西";
		else if (Math.abs(dz) > Math.abs(dx) * 2) dir = dz > 0 ? "南" : "北";
		else if (dx > 0 && dz > 0) dir = "东南";
		else if (dx > 0) dir = "东北";
		else if (dz > 0) dir = "西南";
		else dir = "西北";
		return dir + dist + "格";
	}

	/** 方块注册名。 */
	static String blockId(BlockState state) {
		return BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
	}
}
