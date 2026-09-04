package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.util.Mth;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.entity.item.FallingBlockEntity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

/** 岩浆、水、熔岩块和沙子/沙砾下落检测，供盾构机在挖矿前避险。 */
public final class BorerHazards {
	private BorerHazards() {
	}

	/** 没有 NoFall 时最多直接落下 3 格；开了 Meteor NoFall 则只要落点实心、途中无岩浆就可以跳。 */
	public static int maxSafeFallBlocks() {
		return BorerFallPolicy.maxSafeFallBlocks(BorerFlight.meteorNoFallActive());
	}

	/**
	 * 踏入 {@code feetColumn}（与当前脚同高的那一格）后会落下几格。
	 * 0 是平地，正数是落差，-1 是岩浆/虚空/太深。
	 */
	public static int safeFallDepth(Minecraft client, BlockPos feetColumn) {
		return safeFallDepthTreatingAir(client, feetColumn, null);
	}

	/** 把 {@code treatAsAir} 当成已挖掉，再算落差。用来判断挖脚下矿会不会掉进岩浆。 */
	public static int safeFallDepthTreatingAir(Minecraft client, BlockPos feetColumn, BlockPos treatAsAir) {
		if (client.level == null || feetColumn == null) return -1;
		int max = maxSafeFallBlocks();
		for (int drop = 0; drop <= max; drop++) {
			BlockPos through = drop == 0 ? feetColumn : feetColumn.below(drop);
			if (hazardForFall(client, through, treatAsAir) || !passableForFall(client, through, treatAsAir)) return -1;
			if (drop == 0 && !passableForFall(client, feetColumn.above(), treatAsAir)) return -1;
			BlockPos landing = feetColumn.below(drop + 1);
			if (hazardForFall(client, landing, treatAsAir)) return -1;
			if (solidFloorForFall(client, landing, treatAsAir)) return drop;
		}
		return -1;
	}

	/** 脚前方柱是否可走或安全落下。 */
	public static boolean canWalkOrFallInto(Minecraft client, BlockPos feetColumn) {
		return safeFallDepth(client, feetColumn) >= 0;
	}

	/** 这一列能不能站住：脚和头都是空气。回家 BFS 用这个，不要走带 48 格落差扫描的 {@link #canWalkOrFallInto}。 */
	public static boolean isOpenStandColumn(Minecraft client, BlockPos feet) {
		if (client.level == null || feet == null) return false;
		return isPassable(client, feet) && isPassable(client, feet.above());
	}

	/** 基岩、屏障等永远挖不掉的方块。 */
	public static boolean isUnbreakable(Minecraft client, BlockPos pos) {
		if (client.level == null) return false;
		BlockState state = client.level.getBlockState(pos);
		if (state.isAir() || state.canBeReplaced()) return false;
		if (state.getDestroySpeed(client.level, pos) < 0.0F) return true;
		return state.is(Blocks.BEDROCK) || state.is(Blocks.BARRIER)
			|| state.is(Blocks.END_PORTAL) || state.is(Blocks.END_PORTAL_FRAME)
			|| state.is(Blocks.NETHER_PORTAL);
	}

	/** 格是否可通过。 */
	private static boolean isPassable(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (isLavaFluid(client, pos) || isMagma(client, pos) || isWater(client, pos) || isUnbreakable(client, pos)) return false;
		return state.isAir() || state.canBeReplaced();
	}

	/** 是否当作空气处理。 */
	private static boolean treatedAsAir(BlockPos pos, BlockPos treatAsAir) {
		return pos != null && treatAsAir != null && pos.equals(treatAsAir);
	}

	/** 落差判定下是否可通过。 */
	private static boolean passableForFall(Minecraft client, BlockPos pos, BlockPos treatAsAir) {
		return treatedAsAir(pos, treatAsAir) || isPassable(client, pos);
	}

	/** 落差判定下是否危险。 */
	private static boolean hazardForFall(Minecraft client, BlockPos pos, BlockPos treatAsAir) {
		if (treatedAsAir(pos, treatAsAir)) return false;
		return isLavaFluid(client, pos) || isMagma(client, pos) || isWater(client, pos);
	}

	/** 落差判定下是否实心地面。 */
	private static boolean solidFloorForFall(Minecraft client, BlockPos pos, BlockPos treatAsAir) {
		return !treatedAsAir(pos, treatAsAir) && isSolidFloor(client, pos);
	}

	/** 该格是否为水。 */
	public static boolean isWater(Minecraft client, BlockPos pos) {
		return client.level != null && client.level.getBlockState(pos).getFluidState().is(Fluids.WATER);
	}

	/** 是否实心地板。 */
	private static boolean isSolidFloor(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (state.is(Blocks.MAGMA_BLOCK) || isLavaFluid(client, pos)) return false;
		if (state.isAir() || state.canBeReplaced() || !state.getFluidState().isEmpty()) return false;
		return isUnbreakable(client, pos) || state.getDestroySpeed(client.level, pos) >= 0.0F;
	}

	/** 该格是否为会流动的岩浆流体。岩浆块（magma）是固体，不算岩浆。 */
	public static boolean isLavaFluid(Minecraft client, BlockPos pos) {
		if (client.level == null) return false;
		BlockState state = client.level.getBlockState(pos);
		if (state.is(Blocks.MAGMA_BLOCK)) return false;
		var fluid = state.getFluidState();
		return !fluid.isEmpty() && fluid.is(Fluids.LAVA);
	}

	/** 该格是否为熔岩块。 */
	public static boolean isMagma(Minecraft client, BlockPos pos) {
		return client.level != null && client.level.getBlockState(pos).is(Blocks.MAGMA_BLOCK);
	}

	/** 踩在岩浆块上（会被烫，潜行可免疫）。 */
	public static boolean playerOnMagma(Minecraft client, LocalPlayer player) {
		if (client.level == null || player == null) return false;
		BlockPos feet = player.blockPosition();
		if (isMagma(client, feet.below())) return true;
		AABB box = player.getBoundingBox();
		int y = Mth.floor(box.minY - 0.08);
		for (int x = Mth.floor(box.minX); x <= Mth.floor(box.maxX - 0.00001); x++) {
			for (int z = Mth.floor(box.minZ); z <= Mth.floor(box.maxZ - 0.00001); z++) {
				if (isMagma(client, new BlockPos(x, y, z))) return true;
			}
		}
		return false;
	}

	/** 玩家碰撞箱是否已经泡在岩浆流体里。旁边有岩浆湖不算，避免误报停机。 */
	public static boolean playerTouchedLava(Minecraft client, LocalPlayer player) {
		return player != null && player.isInLava();
	}

	/** 挖掉该方块后会露出的相邻岩浆，含正上方（岩浆下的承重块）。 */
	public static BlockPos lavaOpenedByMining(Minecraft client, BlockPos target) {
		return fluidNeighbor(client, target, true, false);
	}

	/** 挖这块会让岩浆留下来或流进通道：岩浆正下方、或六面贴着岩浆。 */
	public static boolean wouldOpenLava(Minecraft client, BlockPos target) {
		return lavaOpenedByMining(client, target) != null;
	}

	/** 挖掉该方块后会露出的相邻水。 */
	public static BlockPos waterOpenedByMining(Minecraft client, BlockPos target) {
		return fluidNeighbor(client, target, false, true);
	}

	/** 挖掉目标后是否会露出水。 */
	public static boolean wouldOpenWater(Minecraft client, BlockPos target) {
		return waterOpenedByMining(client, target) != null;
	}

	/** 目标邻接的岩浆或水格；没有则 null。 */
	private static BlockPos fluidNeighbor(Minecraft client, BlockPos target, boolean lava, boolean water) {
		if (client.level == null || target == null) return null;
		for (Direction direction : Direction.values()) {
			BlockPos neighbor = target.relative(direction);
			if (lava && isLavaFluid(client, neighbor)) return neighbor.immutable();
			if (water && isWater(client, neighbor)) return neighbor.immutable();
		}
		return null;
	}

	/** 从眼睛出发、按流体裁剪能否直接看到该液体格。 */
	public static boolean canSeeLiquid(Minecraft client, LocalPlayer player, BlockPos pos) {
		BlockHitResult hit = client.level.clip(new ClipContext(
			player.getEyePosition(), Vec3.atCenterOf(pos), ClipContext.Block.COLLIDER, ClipContext.Fluid.ANY, player
		));
		return hit.getBlockPos().equals(pos);
	}

	/** 沙子、沙砾、混凝土粉末等会下落的方块。 */
	public static boolean isFallingType(Minecraft client, BlockPos pos) {
		if (client.level == null) return false;
		return client.level.getBlockState(pos).getBlock() instanceof FallingBlock;
	}

	/** 正在下落的沙子/沙砾实体会砸到玩家。 */
	public static boolean fallingEntityThreat(Minecraft client, LocalPlayer player) {
		if (client.level == null) return false;
		AABB search = player.getBoundingBox().inflate(0.7, 3.2, 0.7);
		return !client.level.getEntitiesOfClass(FallingBlockEntity.class, search, entity ->
			entity.isAlive() && entity.getY() + 0.1 >= player.getY()).isEmpty();
	}

	/** 挖掉 target 后，上方沙子/沙砾会掉进玩家所在列。 */
	public static boolean wouldCrushPlayer(Minecraft client, LocalPlayer player, BlockPos target) {
		if (client.level == null || player == null || target == null) return false;
		BlockPos feet = player.blockPosition();
		int px = feet.getX();
		int pz = feet.getZ();
		if (Math.abs(target.getX() - px) > 1 || Math.abs(target.getZ() - pz) > 1) return false;
		BlockPos above = target.above();
		return isFallingType(client, above);
	}

	/** 从 pos 往上走到沙子/沙砾柱的最高一块。 */
	public static BlockPos topFallingBlock(Minecraft client, BlockPos pos, int maxUp) {
		if (client.level == null || pos == null) return null;
		BlockPos top = isFallingType(client, pos) ? pos.immutable() : null;
		BlockPos cursor = pos;
		for (int i = 0; i < maxUp; i++) {
			cursor = cursor.above();
			if (!isFallingType(client, cursor)) break;
			top = cursor.immutable();
		}
		return top;
	}

	/** 玩家头顶即将失去支撑的沙子/沙砾。 */
	public static BlockPos unsupportedFallingAbove(Minecraft client, LocalPlayer player, BlockPos miningTarget) {
		if (client.level == null) return null;
		BlockPos feet = player.blockPosition();
		for (int dy = 1; dy <= 5; dy++) {
			for (int dx = -1; dx <= 1; dx++) {
				for (int dz = -1; dz <= 1; dz++) {
					BlockPos pos = feet.offset(dx, dy, dz);
					if (!isFallingType(client, pos)) continue;
					BlockPos below = pos.below();
					BlockState under = client.level.getBlockState(below);
					boolean open = under.isAir() || under.canBeReplaced() || under.liquid()
						|| miningTarget != null && below.equals(miningTarget);
					if (open) return pos.immutable();
				}
			}
		}
		return null;
	}

	/** 附近能飞上去、周围没有岩浆的空气天井。镐坏了不能挖，只能走已有空洞。 */
	public static BlockPos nearestSafeAscent(Minecraft client, LocalPlayer player, int radius, int up) {
		if (client.level == null || player == null) return null;
		BlockPos feet = player.blockPosition();
		BlockPos best = null;
		double bestScore = Double.MAX_VALUE;
		for (int dx = -radius; dx <= radius; dx++) {
			for (int dz = -radius; dz <= radius; dz++) {
				if (dx * dx + dz * dz > radius * radius) continue;
				BlockPos column = feet.offset(dx, 0, dz);
				int headroom = openHeadroom(client, column, up);
				if (headroom < 3) continue;
				if (lavaNearColumn(client, column, headroom)) continue;
				double dist = Math.hypot(dx, dz);
				double score = dist - headroom * 0.35;
				if (score < bestScore) {
					bestScore = score;
					best = column.above().immutable();
				}
			}
		}
		return best;
	}

	/** 这一列从脚上一格起有多少格空气（不含岩浆）。 */
	public static int openHeadroom(Minecraft client, BlockPos feet, int maxUp) {
		if (client.level == null) return 0;
		int run = 0;
		for (int dy = 1; dy <= maxUp; dy++) {
			BlockPos pos = feet.above(dy);
			if (!client.level.hasChunkAt(pos)) break;
			if (isLavaFluid(client, pos)) break;
			if (!client.level.getBlockState(pos).getCollisionShape(client.level, pos).isEmpty()) break;
			run++;
		}
		return run;
	}

	/** 立足柱及邻柱头顶净空内是否有岩浆。 */
	private static boolean lavaNearColumn(Minecraft client, BlockPos feet, int headroom) {
		for (int dy = 1; dy <= headroom + 1; dy++) {
			for (int ox = -1; ox <= 1; ox++) {
				for (int oz = -1; oz <= 1; oz++) {
					if (isLavaFluid(client, feet.offset(ox, dy, oz))) return true;
				}
			}
		}
		return false;
	}
}
