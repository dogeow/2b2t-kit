package dev.twob2tkit.planter;

import net.minecraft.core.BlockPos;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Block;

import java.util.Comparator;
import java.util.List;

/**
 * 种田哪些土能锄、什么时候能按左键收。只改这一处。
 * <p>
 * 9×9 围墙是田边那圈土：一边耕地、两边连着土、一边空地。锄了就像把围墙打掉。
 * 收成必须准星打到作物，侧着瞄会挖到土墙。
 */
public final class PlanterPolicy {
	private PlanterPolicy() {
	}

	/** 蛇形播种行：沿 lockedYaw 走，偶数行前进、奇数行后退，视角不来回转。 */
	public static final class RowPlan {
		public final boolean walkAlongX;
		public final boolean forwardPositive;
		public final float lockedYaw;

		/** 蛇形一行：轴向、正负方向与锁定 yaw。 */
		public RowPlan(boolean walkAlongX, boolean forwardPositive, float lockedYaw) {
			this.walkAlongX = walkAlongX;
			this.forwardPositive = forwardPositive;
			this.lockedYaw = lockedYaw;
		}

		/** 垂直于行走方向的行键（X 或 Z）。 */
		public int rowKey(BlockPos pos) {
			return walkAlongX ? pos.getZ() : pos.getX();
		}

		/** 沿行走方向的坐标键。 */
		public int alongKey(BlockPos pos) {
			return walkAlongX ? pos.getX() : pos.getZ();
		}

		/** 两格是否同一行。 */
		public boolean sameRow(BlockPos a, BlockPos b) {
			return rowKey(a) == rowKey(b);
		}
	}

	/** 开局按玩家朝向定行方向，整趟尽量保持同一 yaw。 */
	public static RowPlan rowPlanFromYaw(float yawDeg) {
		float rad = (float)Math.toRadians(yawDeg);
		float forwardX = -((float)Math.sin(rad));
		float forwardZ = (float)Math.cos(rad);
		boolean walkAlongX = Math.abs(forwardX) >= Math.abs(forwardZ);
		boolean forwardPositive = walkAlongX ? forwardX > 0.0F : forwardZ > 0.0F;
		float lockedYaw = walkAlongX
			? (forwardPositive ? 270.0F : 90.0F)
			: (forwardPositive ? 0.0F : 180.0F);
		return new RowPlan(walkAlongX, forwardPositive, lockedYaw);
	}

	/** 蛇形播种比较器：近行优先，奇数行反向。 */
	public static Comparator<BlockPos> serpentineOrder(BlockPos origin, RowPlan plan) {
		int originRow = plan.rowKey(origin);
		return (a, b) -> {
			int rowA = plan.rowKey(a);
			int rowB = plan.rowKey(b);
			if (rowA != rowB) {
				int distA = Math.abs(rowA - originRow);
				int distB = Math.abs(rowB - originRow);
				if (distA != distB) return Integer.compare(distA, distB);
				return Integer.compare(rowA, rowB);
			}
			int alongA = plan.alongKey(a);
			int alongB = plan.alongKey(b);
			boolean reverseRow = (Math.abs(rowA - originRow) & 1) == 1;
			int cmp = Integer.compare(alongA, alongB);
			if (reverseRow) cmp = -cmp;
			if (!plan.forwardPositive) cmp = -cmp;
			return cmp;
		};
	}

	/** 在列表里挑蛇形顺序最前的那一格下标。 */
	public static int pickSerpentineIndex(List<BlockPos> positions, BlockPos origin, RowPlan plan) {
		if (positions.isEmpty()) return -1;
		Comparator<BlockPos> order = serpentineOrder(origin, plan);
		int best = 0;
		for (int i = 1; i < positions.size(); i++) {
			if (order.compare(positions.get(i), positions.get(best)) < 0) {
				best = i;
			}
		}
		return best;
	}

	/** 准星打到要收的那格才按左键。 */
	public static boolean harvestIfRayHitsCrop(boolean rayHitsTarget) {
		return rayHitsTarget;
	}

	/** 种田时不要跳：跳会把耕地踩回土。 */
	public static boolean shouldJumpWhileFarming() {
		return false;
	}

	/** 收成用破坏方块，不要按住攻击键空挥。 */
	public static boolean harvestWithAttackKey() {
		return false;
	}

	/** 准星方向有村民等实体挡着：先别收，避免误伤。 */
	public static boolean skipHarvestWhenEntityInWay(boolean entityInWay) {
		return entityInWay;
	}

	/** 只捡当前作物相关的种子和收成，不要顺走别的模组掉落物。 */
	public static boolean isFarmLoot(ItemStack stack, Item cropItem, Block plantBlock) {
		if (stack.isEmpty() || cropItem == null) return false;
		if (stack.is(cropItem)) return true;
		if (plantBlock != null) {
			Item plantItem = plantBlock.asItem();
			if (plantItem != Items.AIR && stack.is(plantItem)) return true;
		}
		return false;
	}

	/**
	 * 背包没种子时，成熟作物打掉就会掉种子。开了自动收成就按田里的作物先收，不要报手里没有。
	 * 来源：2026-08-23 田里小麦已熟，提示「手里或背包没有可种的农作物」。
	 */
	public static boolean harvestWhenInventoryHasNoSeeds(boolean harvestEnabled, boolean matureNearby) {
		return harvestEnabled && matureNearby;
	}

	/** 关了自动收成、又没种子：才停。开着收成就继续去田里收。 */
	public static boolean stopBecauseNoSeeds(boolean harvestEnabled, boolean hasSeeds) {
		return !hasSeeds && !harvestEnabled;
	}

	/** 开了先锄地但没有锄：不要选待锄格子，否则会空转。 */
	public static boolean skipTillWithoutHoe(boolean tillEnabled, boolean hasHoe) {
		return tillEnabled && !hasHoe;
	}

	/**
	 * 开了自动收成时，手里作物与田里不一致：优先收田里的。
	 * @param sameCrop 手里作物与田里成熟作物是否同一种
	 * @param handHasMatureNearby 附近是否有手里这种成熟作物
	 */
	public static boolean preferFieldCropForHarvest(boolean sameCrop, boolean handHasMatureNearby) {
		if (sameCrop) return false;
		return !handHasMatureNearby;
	}

	/**
	 * 没锄、没种位、也没成熟作物可收时停止。
	 * @param hasSeeds 背包是否还有种子
	 * @param hasPlantOrHarvestSpot 范围内是否有可种或可收格（不含待锄土）
	 * @param needsFarm 当前作物是否需要耕地
	 * @param tillEnabled 是否勾了先锄地
	 * @param hasHoe 背包是否有锄
	 */
	public static boolean shouldStopNoHoeNoWork(
		boolean hasSeeds,
		boolean hasPlantOrHarvestSpot,
		boolean needsFarm,
		boolean tillEnabled,
		boolean hasHoe
	) {
		if (hasPlantOrHarvestSpot) return false;
		if (!hasSeeds && !tillEnabled) return true;
		if (needsFarm && tillEnabled && !hasHoe) return true;
		return !hasSeeds;
	}

	/**
	 * 田边土墙，不要锄成耕地。
	 * @param farmlandNeighbors 四向已是耕地
	 * @param dirtNeighbors 四向仍是土/草且顶上可种
	 * @param openNeighbors 四向空气或可替换
	 */
	public static boolean isEnclosureWallSoil(int farmlandNeighbors, int dirtNeighbors, int openNeighbors) {
		return farmlandNeighbors >= 1 && dirtNeighbors >= 2 && openNeighbors >= 1;
	}
}
