package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;

/** 找矿通道：身旁矿、准星挡路、1×2 眼前可挖块。 */
final class BorerCorridor {
	private final DefaultTunnelBorerEngine engine;

	BorerCorridor(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 通道扫描得到的下一挖点。 */
	BlockPos nextOreBlock(Minecraft client, LocalPlayer player) {
		BlockPos feet = engine.navigationColumn(client, player);
		BlockPos adjacent = adjacentOreToMine(client, player);
		if (adjacent != null) return adjacent;
		BlockPos gap = engine.vertical.nextOpenableOneByTwo(client, player);
		if (gap != null) return gap;
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		if (goal != null) engine.lockHeadingToward(feet, goal);
		BlockPos looked = corridorCrosshair(client, player, feet);
		if (looked != null) {
			BlockPos climb = engine.vertical.climbTargetInsteadOfFoothold(client, player, looked);
			if (climb != null) {
				BlockPos lifted = engine.liftFallingStack(client, player, climb);
				return lifted != null ? lifted : climb;
			}
		}
		int height = engine.effectiveHeight();
		for (int dist = 0; dist <= 1; dist++) {
			for (int dy = height + 4; dy >= 0; dy--) {
				if (BorerStairPolicy.ignoreOverheadFalling(dist, dy, height)) continue;
				BlockPos pos = engine.offset(feet, dist, 0, dy);
				if (!BorerHazards.isFallingType(client, pos)) continue;
				if (!engine.canPlanMine(client, pos) || !engine.inMiningReach(player, pos)) continue;
				if (engine.canSeeBlock(client, player, pos) || engine.playerTouchesBlock(player, pos) || engine.hasCollision(client, pos)) {
					BlockPos lifted = engine.liftFallingStack(client, player, pos);
					return lifted != null ? lifted : pos.immutable();
				}
			}
			for (int dy = 0; dy < height; dy++) {
				BlockPos pos = engine.offset(feet, dist, 0, dy);
				if (engine.isWalkableOneBlockStep(client, player, pos)) continue;
				BlockPos climb = engine.vertical.climbTargetInsteadOfFoothold(client, player, pos);
				if (climb == null) continue;
				if (engine.isWalkableOneBlockStep(client, player, climb)) continue;
				if (!engine.canPlanMine(client, climb) || !engine.inMiningReach(player, climb)) continue;
				if (engine.canSeeBlock(client, player, climb) || engine.playerTouchesBlock(player, climb) || engine.hasCollision(client, climb)) {
					BlockPos lifted = engine.liftFallingStack(client, player, climb);
					return lifted != null ? lifted : climb.immutable();
				}
			}
		}
		return null;
	}

	/** 身旁、脚下、头顶的勾选矿先挖，不管当前锁的是远处哪一块。 */
	BlockPos adjacentOreToMine(Minecraft client, LocalPlayer player) {
		if (client.level == null || player == null) return null;
		BlockPos feet = engine.navigationColumn(client, player);
		BlockPos best = null;
		double bestScore = Double.MAX_VALUE;
		for (int dx = -1; dx <= 1; dx++) {
			for (int dz = -1; dz <= 1; dz++) {
				if (Math.abs(dx) + Math.abs(dz) > 1) continue;
				for (int dy = -1; dy <= 2; dy++) {
					BlockPos pos = feet.offset(dx, dy, dz);
					if (!engine.wantedBlock(client.level.getBlockState(pos))) continue;
					if (!engine.shouldMine(client, pos) || !engine.inMiningReach(player, pos)) continue;
					boolean standingSupport = engine.isStandingSupport(client, player, pos);
					boolean landingSafe = BorerFallPolicy.canMineFloorIfLandingSafe(
						engine.landingDropIfMined(client, player, pos));
					if (!BorerMiningPolicy.adjacentOreCanBeSelected(
						Math.abs(dx) + Math.abs(dz), dy, standingSupport, landingSafe)) {
						continue;
					}
					double score = BorerOrePolicy.approachScore(dx, dz, dy);
					if (score < bestScore) {
						bestScore = score;
						best = pos.immutable();
					}
				}
			}
		}
		return best;
	}

	/** 准星正对的通道挡路：1×2 里眼前那块，不依赖 clip 采样。 */
	BlockPos corridorCrosshair(Minecraft client, LocalPlayer player, BlockPos feet) {
		if (!(client.hitResult instanceof BlockHitResult hit) || hit.getType() != HitResult.Type.BLOCK) return null;
		BlockPos pos = hit.getBlockPos();
		if (!engine.canPlanMine(client, pos) || !engine.inMiningReach(player, pos)) return null;
		int along = (pos.getX() - feet.getX()) * engine.forward.getStepX() + (pos.getZ() - feet.getZ()) * engine.forward.getStepZ();
		int dy = pos.getY() - feet.getY();
		if (along < 0 || along > 2 || dy < 0 || dy > engine.effectiveHeight()) return null;
		if (!BorerCenterPolicy.inCorridorColumn(Math.abs(engine.lateralDistance(feet, pos)), engine.effectiveWidth())) return null;
		if (Math.abs(engine.lateralDistance(feet, pos)) > 0 && engine.safeDropAhead(client, player) > 0) return null;
		return pos.immutable();
	}

	/** 准星已经对着一块可挖的石头：直接挖，不要求它落在 1×2 通道正中。不挖立足点。 */
	BlockPos aimedMineable(Minecraft client, LocalPlayer player) {
		if (!(client.hitResult instanceof BlockHitResult hit) || hit.getType() != HitResult.Type.BLOCK) return null;
		BlockPos pos = hit.getBlockPos();
		if (!engine.canPlanMine(client, pos) || !BorerAim.hitInReach(player, hit)) return null;
		if (engine.isUnsafeFloorMine(client, player, pos) || engine.isBelowFeetNonOre(client, player, pos)) return null;
		if (engine.isWalkableOneBlockStep(client, player, pos)) return null;
		BlockPos feet = engine.navigationColumn(client, player);
		int along = (pos.getX() - feet.getX()) * engine.forward.getStepX() + (pos.getZ() - feet.getZ()) * engine.forward.getStepZ();
		int dy = pos.getY() - feet.getY();
		if (along < 0 || along > 2 || dy < 0 || dy > engine.effectiveHeight()) return null;
		if (!BorerCenterPolicy.inCorridorColumn(Math.abs(engine.lateralDistance(feet, pos)), engine.effectiveWidth())) return null;
		if (engine.vertical.climbingToOre(client, player) && pos.getY() < engine.navigationColumn(client, player).getY()) return null;
		return engine.vertical.climbTargetInsteadOfFoothold(client, player, pos);
	}

	/** 视线判定失败时，眼前贴脸/正前方仍可挖的挡路。 */
	BlockPos mineableInFront(Minecraft client, LocalPlayer player) {
		if (engine.currentTarget != null) {
			BlockPos realHit = mineableRealHit(client, player, engine.currentTarget);
			if (realHit != null && !realHit.equals(engine.currentTarget)) return realHit;
		}
		if (!engine.axisAim()) {
			BlockPos aimed = aimedMineable(client, player);
			if (aimed != null) return aimed;
		}
		return nextClearableCorridorBlock(client, player);
	}

	/**
	 * 勾选矿够得着时：真实射线打到的挡路，或朝矿连线上的第一块可挖方块。
	 * 轴向瞄准对角矿会打到旁边石头，这块往往不在 1×2 正中。
	 */
	BlockPos mineableRealHit(Minecraft client, LocalPlayer player, BlockPos expected) {
		if (expected == null || client.level == null) return null;
		boolean oreInReach = engine.wantedBlock(client.level.getBlockState(expected)) && BorerAim.inReach(player, expected);
		if (!oreInReach) return null;
		BlockHitResult view = BorerAim.clipView(client, player);
		if (view != null
			&& engine.canPlanMine(client, view.getBlockPos())
			&& BorerAim.hitInReach(player, view)
			&& !engine.isUnsafeFloorMine(client, player, view.getBlockPos())
			&& !engine.isBelowFeetNonOre(client, player, view.getBlockPos())
			&& BorerMiningPolicy.mineRealHitTowardInReachOre(true, view.getBlockPos().equals(expected), true)) {
			return view.getBlockPos().immutable();
		}
		BlockHitResult toward = engine.firstMineableHitToward(client, player, expected);
		if (toward != null
			&& engine.canPlanMine(client, toward.getBlockPos())
			&& BorerAim.hitInReach(player, toward)
			&& !engine.isUnsafeFloorMine(client, player, toward.getBlockPos())
			&& !engine.isBelowFeetNonOre(client, player, toward.getBlockPos())
			&& BorerMiningPolicy.mineRealHitTowardInReachOre(true, toward.getBlockPos().equals(expected), true)) {
			return toward.getBlockPos().immutable();
		}
		return null;
	}

	/** 当前朝向 1×2 里够得着的挡路，不含通道地板。贴坑沿时用身体所在格，不要用边缘立足点那列。 */
	BlockPos nextClearableCorridorBlock(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		int height = engine.effectiveHeight();
		for (int dist = 0; dist <= 1; dist++) {
			for (int dy = 0; dy < height; dy++) {
				BlockPos pos = engine.offset(feet, dist, 0, dy);
				if (canAttemptMine(client, player, pos, dist)) return pos.immutable();
			}
		}
		return null;
	}

	/** 距离与视线是否允许开挖。 */
	boolean canAttemptMine(Minecraft client, LocalPlayer player, BlockPos pos, int dist) {
		if (!engine.canPlanMine(client, pos) || !engine.inMiningReach(player, pos)) return false;
		if (engine.isUnsafeFloorMine(client, player, pos) || engine.isBelowFeetNonOre(client, player, pos)) return false;
		if (engine.isWalkableOneBlockStep(client, player, pos)) return false;
		if (engine.canSeeBlock(client, player, pos) || engine.playerTouchesBlock(player, pos)) return true;
		return dist <= 1 && engine.hasCollision(client, pos);
	}
}
