package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;

import java.util.Locale;

/**
 * 区域挖：两点围成矩形，按 1×1 竖井逐格挖到底。只改这一处。
 * <p>
 * 每一格 (x,z) 从上往下挖到目标 Y，再开飞行到下一格顶面继续。
 * 换格顺序可切：{@code vertical}（默认，网格一口接一口）或 {@code nearest}（飞最近一口）。
 * 两点 Y 相同则一直往下；Y 不同挖到较低那层换格。
 */
public final class BorerAreaPolicy {
	public static final int MAX_SPAN = 64;
	public static final int PICK_RANGE = 128;
	public static final String ORDER_VERTICAL = "vertical";
	public static final String ORDER_NEAREST = "nearest";

	private BorerAreaPolicy() {
	}

	/** 默认竖井网格：一口挖到底再换旁边那口。 */
	public static String normalizeOrder(String raw) {
		if (raw == null || raw.isBlank()) return ORDER_VERTICAL;
		String n = raw.trim().toLowerCase(Locale.ROOT);
		return switch (n) {
			case ORDER_NEAREST, "near", "closest", "就近", "就近飞" -> ORDER_NEAREST;
			default -> ORDER_VERTICAL;
		};
	}

	/** 是否用最近井顺序。 */
	public static boolean useNearestOrder(String order) {
		return ORDER_NEAREST.equals(normalizeOrder(order));
	}

	/** 换格顺序短标签。 */
	public static String orderLabel(String order) {
		return useNearestOrder(order) ? "就近飞" : "竖井网格";
	}

	/** 换格顺序说明。 */
	public static String orderHint(String order) {
		if (useNearestOrder(order)) return "一口 1×1 挖到底，再飞最近还没挖的一口";
		return "一口 1×1 挖到底，再按网格换旁边下一格";
	}

	/** 网格序号：先 X 再 Z。越小越先挖。 */
	public static int gridIndex(int x, int z, int minX, int minZ, int maxX) {
		int width = spanInclusive(minX, maxX);
		return (z - minZ) * width + (x - minX);
	}

	/**
	 * 竖井网格换格：优先当前格之后的下一口；后面没有了再从前面找还没挖的。
	 * {@code remaining} 为 true 的候选才参与。
	 */
	public static boolean preferGridCandidate(
		int candX, int candZ, int bestX, int bestZ,
		int fromX, int fromZ, int minX, int minZ, int maxX
	) {
		int from = gridIndex(fromX, fromZ, minX, minZ, maxX);
		int cand = gridIndex(candX, candZ, minX, minZ, maxX);
		int best = gridIndex(bestX, bestZ, minX, minZ, maxX);
		boolean candAfter = cand > from;
		boolean bestAfter = best > from;
		if (candAfter != bestAfter) return candAfter;
		return cand < best;
	}

	/** 含端点区间长度。 */
	public static int spanInclusive(int a, int b) {
		return Math.abs(a - b) + 1;
	}

	/** 区域水平跨度是否过大。 */
	public static boolean tooLarge(int ax, int az, int bx, int bz) {
		return spanInclusive(ax, bx) > MAX_SPAN || spanInclusive(az, bz) > MAX_SPAN;
	}

	/** XZ 是否在矩形内。 */
	public static boolean containsXZ(int x, int z, int minX, int minZ, int maxX, int maxZ) {
		return x >= minX && x <= maxX && z >= minZ && z <= maxZ;
	}

	/** 该威胁是否应主动靠近。 */
	public static boolean shouldApproach(int px, int pz, int minX, int minZ, int maxX, int maxZ) {
		return !containsXZ(px, pz, minX, minZ, maxX, maxZ);
	}

	/** 区域挖被水/岩浆拦住时仍要走思考，不能只停在红色封堵提示。 */
	public static boolean keepThinkingDuringHazard(boolean area) {
		return area;
	}

	/** 数值夹到区间。 */
	public static int clampToRange(int value, int min, int max) {
		if (value < min) return min;
		if (value > max) return max;
		return value;
	}

	/** 两点 Y 不同：挖到较低那层停。相同则一直往下。 */
	public static boolean boundedDown(int ay, int by) {
		return ay != by;
	}

	/** 区域顶面 Y。 */
	public static int topY(int ay, int by) {
		return Math.max(ay, by);
	}

	/** 区域底面 Y。 */
	public static int bottomY(int ay, int by) {
		return Math.min(ay, by);
	}

	/**
	 * 条带沿玩家朝向走，不要按世界 X/Z 哪边更长就横着挖。
	 * 两点围成的矩形仍全覆盖，只是先往你面对的方向一条条推进。
	 */
	public static Direction stripAxis(int minX, int minZ, int maxX, int maxZ, Direction heading) {
		Direction h = heading == null || heading.getAxis() == Direction.Axis.Y ? Direction.EAST : heading;
		if (h.getAxis() == Direction.Axis.X || h.getAxis() == Direction.Axis.Z) return h;
		return Direction.EAST;
	}

	/** 点在主轴上的坐标。 */
	public static int along(Direction axis, int x, int z) {
		if (axis == null) return x;
		return x * axis.getStepX() + z * axis.getStepZ();
	}

	/** 点在条带行上的坐标。 */
	public static int row(Direction axis, int x, int z) {
		if (axis == null) return z;
		Direction right = axis.getClockWise();
		return x * right.getStepX() + z * right.getStepZ();
	}

	/** 条带坐标还原 X。 */
	public static int xFromStrip(Direction axis, int along, int row) {
		if (axis == null) return along;
		Direction right = axis.getClockWise();
		return along * axis.getStepX() + row * right.getStepX();
	}

	/** 条带坐标还原 Z。 */
	public static int zFromStrip(Direction axis, int along, int row) {
		if (axis == null) return row;
		Direction right = axis.getClockWise();
		return along * axis.getStepZ() + row * right.getStepZ();
	}

	/** 区域主轴最小。 */
	public static int minAlong(Direction axis, int minX, int minZ, int maxX, int maxZ) {
		return Math.min(
			Math.min(along(axis, minX, minZ), along(axis, minX, maxZ)),
			Math.min(along(axis, maxX, minZ), along(axis, maxX, maxZ)));
	}

	/** 区域主轴最大。 */
	public static int maxAlong(Direction axis, int minX, int minZ, int maxX, int maxZ) {
		return Math.max(
			Math.max(along(axis, minX, minZ), along(axis, minX, maxZ)),
			Math.max(along(axis, maxX, minZ), along(axis, maxX, maxZ)));
	}

	/** 区域行最小。 */
	public static int minRow(Direction axis, int minX, int minZ, int maxX, int maxZ) {
		return Math.min(
			Math.min(row(axis, minX, minZ), row(axis, minX, maxZ)),
			Math.min(row(axis, maxX, minZ), row(axis, maxX, maxZ)));
	}

	/** 区域行最大。 */
	public static int maxRow(Direction axis, int minX, int minZ, int maxX, int maxZ) {
		return Math.max(
			Math.max(row(axis, minX, minZ), row(axis, minX, maxZ)),
			Math.max(row(axis, maxX, minZ), row(axis, maxX, maxZ)));
	}

	/** 条带两端掉头，中间保持当前朝向，避免左右横摆。 */
	public static Direction headingAlongStrip(Direction axis, Direction current, int along, int minAlong, int maxAlong) {
		Direction pos = stripPositive(axis);
		if (along >= maxAlong) return pos.getOpposite();
		if (along <= minAlong) return pos;
		if (current != null && current.getAxis() == pos.getAxis()) return current;
		return pos;
	}

	/** 条带正向方向。 */
	public static Direction stripPositive(Direction axis) {
		if (axis == null) return Direction.EAST;
		if (axis.getAxis() == Direction.Axis.X) return axis.getStepX() >= 0 ? Direction.EAST : Direction.WEST;
		if (axis.getAxis() == Direction.Axis.Z) return axis.getStepZ() >= 0 ? Direction.SOUTH : Direction.NORTH;
		return Direction.EAST;
	}

	/** 条带内下一行坐标。 */
	public static int nextRow(int row, int minRow, int maxRow) {
		return nextBand(row, minRow, maxRow, 1);
	}

	/** 条带宽度夹紧。 */
	public static int clampWidth(int width) {
		if (width < 1) return 1;
		if (width > MAX_SLICE) return MAX_SLICE;
		return width;
	}

	/** 这一条带宽从哪一列开始。2×2 就是两列一起挖再换。 */
	public static int bandStart(int row, int minRow, int width) {
		int w = clampWidth(width);
		int offset = row - minRow;
		if (offset < 0) return minRow;
		return minRow + (offset / w) * w;
	}

	/** 本条带结束行。 */
	public static int bandEnd(int row, int minRow, int maxRow, int width) {
		int start = bandStart(row, minRow, width);
		return Math.min(maxRow, start + clampWidth(width) - 1);
	}

	/** 下一条带起始行。 */
	public static int nextBand(int row, int minRow, int maxRow, int width) {
		int start = bandStart(row, minRow, width);
		int next = start + clampWidth(width);
		if (next <= maxRow) return next;
		return row;
	}

	/** 条带中间那一列。3 宽走正中，2 宽取两列偏起始的那格。 */
	public static int bandCenterBlock(int row, int minRow, int maxRow, int width) {
		int start = bandStart(row, minRow, width);
		int end = bandEnd(row, minRow, maxRow, width);
		return (start + end) / 2;
	}

	/**
	 * 条带世界坐标中心（格子中心）。3 宽走中间那列，2 宽走两列交界。
	 * 贴着起始列走时，另一侧掉落会超出原版拾取（大约 1.3 格）。
	 */
	public static double bandCenterX(Direction axis, int along, int row, int minRow, int maxRow, int width) {
		int start = bandStart(row, minRow, width);
		int end = bandEnd(row, minRow, maxRow, width);
		return (xFromStrip(axis, along, start) + xFromStrip(axis, along, end)) * 0.5 + 0.5;
	}

	/** 条带中心世界坐标（命名历史，含 X/Z）。 */
	public static double bandCenterZ(Direction axis, int along, int row, int minRow, int maxRow, int width) {
		int start = bandStart(row, minRow, width);
		int end = bandEnd(row, minRow, maxRow, width);
		return (zFromStrip(axis, along, start) + zFromStrip(axis, along, end)) * 0.5 + 0.5;
	}

	/** 宽巷是否走中心。 */
	public static boolean walkCenteredStrip(int width) {
		return clampWidth(width) >= 2;
	}

	/** 当前条带这一层已经挖空、又不能再往下：该换列。 */
	public static boolean shouldChangeBand(boolean stripHasBlocks, boolean moreBelow) {
		return !stripHasBlocks && !moreBelow;
	}

	/**
	 * 同一列从上到下：高处先于身体，身体先于脚下。
	 * 别的条带排最后，避免先扫光整层地板。
	 * {@code dy = blockY - feetY}。
	 */
	public static int mineOrder(int lateralAbs, int alongAbs, int dy) {
		int strip = lateralAbs == 0 ? 0 : 1_000_000 + lateralAbs * 10_000;
		return strip + alongAbs * 100 + verticalRank(dy);
	}

	/**
	 * 从上到下。头顶以上也比脚下优先，落下后再也挖不到上面的石头。
	 * 来源：2026-08-25 区域挖一直往下掉，上方石头留在头顶。
	 */
	public static int verticalRank(int dy) {
		if (dy > 0) return 20 - dy;
		if (dy == 0) return 50;
		return 80 - dy;
	}

	/** 当前切片上面还有方块：先升到区域顶，不要往下挖。 */
	public static boolean shouldAscendToTop(int feetY, int areaMaxY, boolean hasBlocksAboveSlice) {
		return hasBlocksAboveSlice && feetY < areaMaxY;
	}

	/** 这一高度还没挖完（含头顶以上）：沿条带走，不要下落。 */
	public static boolean holdThisLevel(boolean stripHasBand, boolean hasBlocksAboveSlice) {
		return stripHasBand || hasBlocksAboveSlice;
	}

	public static final int MIN_SLICE = 1;
	public static final int MAX_SLICE = 5;
	public static final int DEFAULT_SLICE = 2;

	/** 一次沿条带挖几格高。2 = 普通 1×2。 */
	public static int clampSliceHeight(int height) {
		if (height < MIN_SLICE) return DEFAULT_SLICE;
		if (height > MAX_SLICE) return MAX_SLICE;
		return height;
	}

	/** 当前切片最低 Y。 */
	public static int sliceMinY(int feetY, int areaMinY, int sliceHeight, boolean bounded) {
		int y = feetY;
		if (bounded) return Math.max(areaMinY, y);
		return y;
	}

	/** 当前切片最高 Y。 */
	public static int sliceMaxY(int feetY, int areaMaxY, int sliceHeight, boolean bounded) {
		int y = feetY + clampSliceHeight(sliceHeight) - 1;
		if (bounded) return Math.min(areaMaxY, y);
		return y;
	}

	/** Y 是否在当前切片。 */
	public static boolean inSlice(int y, int feetY, int sliceHeight) {
		int n = clampSliceHeight(sliceHeight);
		return y >= feetY && y <= feetY + n - 1;
	}

	/** 这条还剩当前高度的方块：沿条带走，不要下落去挖整层。 */
	public static boolean walkAlongStrip(boolean stripHasBand) {
		return stripHasBand;
	}

	/** 这一层高度挖通了、下面还在区域内：先挖脚底那格再落下。 */
	public static boolean shouldMineDropFloor(boolean stripHasBand, boolean moreBelow, boolean floorInArea) {
		return !stripHasBand && moreBelow && floorInArea;
	}

	/**
	 * 只有这条高度已通、下面还在区域内、人已经离地时才松键下落。
	 * 还站在实心地上时不能只低头等：身体格子是空气、立足点还在隔壁，会空等「下落再挖」。
	 * 来源：2026-08-25 382848 44 311338，standCol 在 311339，feet 在坑里，onGround 却 WAIT。
	 */
	public static boolean fallInStrip(
		boolean stripHasBand,
		boolean stripHasBelow,
		boolean atBottom,
		boolean canFall,
		boolean onGround
	) {
		return !stripHasBand && stripHasBelow && !atBottom && canFall && !onGround;
	}

	/**
	 * 这条高度已通、准星已经打到区域内更低的可挖方块：挖它。
	 * 不要对着坑底石头空等「下落再挖」。
	 * 来源：2026-08-25 382848 44，crosshair=382848 42 311338/up，status 下落再挖。
	 */
	public static boolean mineLookedBelow(
		boolean stripHasBand,
		boolean moreBelow,
		boolean atBottom,
		int hitY,
		int feetY,
		int areaMinY,
		boolean bounded
	) {
		if (stripHasBand || !moreBelow || atBottom) return false;
		if (hitY >= feetY) return false;
		if (bounded && hitY < areaMinY) return false;
		return true;
	}

	/** 这条高度已通、人还站在实心地上、前方能安全落下：走过去掉下去。 */
	public static boolean walkIntoStripDrop(
		boolean stripHasBand,
		boolean moreBelow,
		boolean atBottom,
		boolean onGround,
		boolean dropAheadSafe
	) {
		return !stripHasBand && moreBelow && !atBottom && onGround && dropAheadSafe;
	}

	/** 是否挖到区域底。 */
	public static boolean atBottom(boolean bounded, int feetY, int bottomY) {
		return bounded && feetY <= bottomY;
	}

	/**
	 * 两点 Y 不同时，最低那层是坑底。站在坑底碰撞箱会擦到再下一格，那一格不要挖。
	 */
	public static boolean belowBottom(boolean bounded, int blockY, int bottomY) {
		return bounded && blockY < bottomY;
	}

	/** 站在实心地上时不要再进入下落等待。 */
	public static boolean abortFallWait(boolean onGround) {
		return onGround;
	}

	/** 有界区域本层是否挖完。 */
	public static boolean finishedBounded(boolean bounded, int feetY, int bottomY, boolean layerCleared) {
		return bounded && layerCleared && feetY <= bottomY;
	}

	/** 巷道起点横向偏移。 */
	public static int startOffset(int size) {
		return BorerShaftPolicy.startOffset(size);
	}

	/** 巷道终点横向偏移。 */
	public static int endOffset(int size) {
		return BorerShaftPolicy.endOffset(size);
	}

	/**
	 * 区域挖目标可能在条带内任意高度/侧向，不能用通道东西南北轴向锁视角。
	 * 来源：2026-08-27 382809 67 311351，heading=西但 crosshair 偏到别处 aim-miss。
	 */
	public static boolean freeAimMining() {
		return true;
	}

	/** 区域尺寸展示文案。 */
	public static String sizeLabel(int ax, int ay, int az, int bx, int by, int bz) {
		int wide = spanInclusive(ax, bx);
		int along = spanInclusive(az, bz);
		if (boundedDown(ay, by)) {
			return wide + "×" + along + "  Y " + topY(ay, by) + "→" + bottomY(ay, by);
		}
		return wide + "×" + along + "  Y " + ay + " 往下";
	}

	/**
	 * 离人最近的一口 1×1（落到区域内）。不要从最小角开跑。
	 * 来源：2026-08-30 人在 382825，却飞去 382776 最小角。
	 */
	public static BlockPos nearestShaftColumn(int px, int pz, int minX, int minZ, int maxX, int maxZ) {
		return new BlockPos(clampToRange(px, minX, maxX), 0, clampToRange(pz, minZ, maxZ));
	}

	/** 到竖井柱水平距离平方。 */
	public static int shaftDistSqr(int px, int pz, int x, int z) {
		int dx = x - px;
		int dz = z - pz;
		return dx * dx + dz * dz;
	}

	/** 第一口 1×1 竖井：人脚下最近那格。 */
	public static BlockPos firstShaftColumn(int px, int pz, int minX, int minZ, int maxX, int maxZ) {
		return nearestShaftColumn(px, pz, minX, minZ, maxX, maxZ);
	}

	/** 当前格挖完后下一格；扫完返回 null。网格顺序仅作对照。 */
	public static BlockPos nextShaftColumn(int x, int z, int minX, int minZ, int maxX, int maxZ) {
		if (x < maxX) return new BlockPos(x + 1, 0, z);
		if (z < maxZ) return new BlockPos(minX, 0, z + 1);
		return null;
	}

	/** 两口候选里离人更近的那口。平局留着 a。 */
	public static boolean closerShaft(int px, int pz, int ax, int az, int bx, int bz) {
		return shaftDistSqr(px, pz, ax, az) <= shaftDistSqr(px, pz, bx, bz);
	}

	/** 是否同一竖井柱。 */
	public static boolean sameShaftColumn(int px, int pz, int cx, int cz) {
		return px == cx && pz == cz;
	}

	/** 竖井扫描下界：有目标 Y 用 areaMinY，否则一直往下扫。 */
	public static int shaftBottomY(boolean bounded, int areaMinY) {
		if (bounded) return areaMinY;
		return -64;
	}

	/** 竖井内从上往下挖：Y 越大越优先。 */
	public static int shaftMineRank(int blockY) {
		return -blockY;
	}

	/** 脚是否在竖井顶。 */
	public static boolean atShaftTop(int feetY, int topY) {
		return feetY >= topY && feetY <= topY + 1;
	}

	/** 人还在区域顶上面的地表：先下去，不要当已经到了。 */
	public static boolean aboveMarkedTop(int feetY, int topY) {
		return feetY > topY + 1;
	}

	/** 是否应飞到下一井顶。 */
	public static boolean shouldFlyToShaftTop(boolean relocating, boolean columnDone, int feetY, int topY) {
		return relocating || columnDone || feetY > topY + 1;
	}

	/**
	 * 飞换井只有贴脸（≤1.75 格）挡路才挖。
	 * 远处只飞/悬停，不要沿准星水平开路。
	 * 来源：2026-08-31 飞往 382776 时沿 X 挖穿 Y66–69。
	 */
	public static boolean mineFlightObstruction(boolean relocating, boolean inReach) {
		// 未知距离当作远处：两参数重载不得放行挖路。
		return mineFlightObstruction(relocating, inReach, Double.POSITIVE_INFINITY);
	}

	/** 换井路上挡飞方块是否该挖。 */
	public static boolean mineFlightObstruction(boolean relocating, boolean inReach, double horiz) {
		return relocating && inReach && horiz <= 1.75;
	}

	/** 目标已在可挖距离：松方向键悬停挖，不要边挖边挪。 */
	public static boolean hoverWhileMining(boolean inReach) {
		return inReach;
	}

	/**
	 * 区域挖准星没命中计划目标时：不要前进换角度，也不要改挖旁边那格。
	 * 来源：2026-08-31 aim-miss 后 walkForward + 改挖准星挡路，水平晃着掏。
	 */
	public static boolean allowAimMissRetarget(boolean sameShaftColumn) {
		return sameShaftColumn;
	}

	/** 区域挖瞄准打偏后是否按 W（应为否）。 */
	public static boolean walkAfterAimMissInArea() {
		return false;
	}

	/** 1×1 竖井不走条带居中横移。 */
	public static boolean areaShaftUsesBandNudge() {
		return false;
	}

	/**
	 * 换下一口竖井：就近优先。
	 * {@code nearestOrder} 或默认都按离人距离；竖井网格额外偏好与上一口相邻的格子。
	 */
	public static boolean preferNextShaft(
		boolean nearestOrder,
		int px, int pz,
		int candX, int candZ, int bestX, int bestZ,
		int fromX, int fromZ
	) {
		if (!nearestOrder) {
			int candAdj = Math.abs(candX - fromX) + Math.abs(candZ - fromZ);
			int bestAdj = Math.abs(bestX - fromX) + Math.abs(bestZ - fromZ);
			boolean candBeside = candAdj == 1;
			boolean bestBeside = bestAdj == 1;
			if (candBeside != bestBeside) return candBeside;
		}
		int candDist = shaftDistSqr(px, pz, candX, candZ);
		int bestDist = shaftDistSqr(px, pz, bestX, bestZ);
		if (candDist != bestDist) return candDist < bestDist;
		return closerShaft(px, pz, candX, candZ, bestX, bestZ);
	}

	/**
	 * 已经在飞、前方堵住、头顶是空的：升高飞过去，不要把整座山挖穿。
	 * 没在飞或头顶实心时还是挖挡路。
	 */
	public static boolean flyOverInsteadOfMine(boolean flying, boolean frontBlocked, boolean ceilingSolid) {
		return flyOverInsteadOfMine(flying, frontBlocked, ceilingSolid, false);
	}

	/**
	 * 已经在飞、前方堵住、头顶是空的：升高飞过去。
	 * 目标在地下时不要破顶飞到地表。
	 */
	public static boolean flyOverInsteadOfMine(
		boolean flying, boolean frontBlocked, boolean ceilingSolid, boolean destBelow
	) {
		if (destBelow) return false;
		return flying && frontBlocked && !ceilingSolid;
	}

	/**
	 * 飞换井按跳：要升高或前方堵住时往上飞；头顶实心不要跳进方块。
	 * 目标在地下时不要跳。
	 */
	public static boolean flyJump(boolean needClimb, boolean frontBlocked, boolean ceilingSolid) {
		return flyJump(needClimb, frontBlocked, ceilingSolid, false);
	}

	/** 含「目标在地下」时禁止跳的完整判定。 */
	public static boolean flyJump(
		boolean needClimb, boolean frontBlocked, boolean ceilingSolid, boolean destBelow
	) {
		if (destBelow) return false;
		return (needClimb || frontBlocked) && !ceilingSolid;
	}

	/**
	 * 目标明显在地下（差 1 格以上）。人站在竖井顶 Y67、脚底 67.87 不算地下，
	 * 否则会跳过挖挡路、按 W 飞进隔壁石头。
	 */
	public static boolean destBelow(double dy) {
		return dy < -1.5;
	}

	/** 隔壁竖井已在触手可及：挖那一口，不要开飞行钻进去。 */
	public static boolean mineAdjacentShaftInsteadOfFly(double horiz) {
		return horiz <= 1.75;
	}

	/**
	 * 前方实心且已经贴脸：不要按前进。
	 * 竖井还在几十格外时，那一列当前高度是实心不算挡路，继续飞过去。
	 * 来源：2026-08-30 382825 45 飞向 382776 67，提示「先挖开」却不挖、也不飞。
	 */
	public static boolean holdForwardWhileFlying(double horiz, boolean pathBlocked) {
		if (horiz > 1.75) return horiz > 0.45;
		return horiz > 0.45 && !pathBlocked;
	}

	/** 已经对准竖井、人还在地表：挖脚下打通道下去。不要潜行撞草地。 */
	public static boolean mineDownToShaftTop(boolean sameColumn, int feetY, int topY) {
		return sameColumn && aboveMarkedTop(feetY, topY);
	}

	/** 正上方到区域顶之间已经是空气：才潜行/下落。脚下实心就挖。 */
	public static boolean sneakDiveToShaft(boolean destBelow, boolean overburdenInReach) {
		return destBelow && !overburdenInReach;
	}

	/**
	 * 飞换井必须对准竖井再按前进。W 跟着准星，不锁视角就会跟着鼠标乱飞。
	 * 来源：2026-08-30 开飞行到竖井 382776 67 311306，准星一动人往准星方向飞。
	 */
	public static boolean lockLookWhileFlyingToShaft(boolean relocating) {
		return relocating;
	}

	/**
	 * 这口 1×1 没有可挖方块，而且人物已经真的下降到目标 Y，才允许返顶换列。
	 * 天然洞穴也要沿原列下降到底，不能人在 Y56、目标 Y54 时提前切换。
	 */
	public static boolean shaftColumnDone(boolean bounded, int feetY, int bottomY, boolean hasBlocks) {
		return !hasBlocks && feetY <= (bounded ? bottomY : bottomY + 1);
	}

	/**
	 * 扫「还有没有下一口井」时不要走当前竖井锁。
	 * 来源：2026-09-01 挖完一口就报「区域 1×1 竖井已全部挖完」，其实矩形还很大。
	 */
	public static boolean surveyRemainingShaftsWithoutColumnLock() {
		return true;
	}

	/**
	 * 这口井下面还有方块、脚下是空的：下去挖，不要报没有视线空等。
	 * 来源：2026-08-30 382776 67 311306，准星已打到 382776 64，飞行停在原地 WAIT_OCCLUDED。
	 */
	public static boolean descendShaftInsteadOfWait(
		boolean sameColumn, boolean remainingBelow, boolean openBelow
	) {
		return sameColumn && remainingBelow && openBelow;
	}

	/**
	 * 已经在这口 1×1 里、还能往下挖或往下掉：不要想想、不要飞去区域顶、不要卡格心。
	 * 来源：2026-09-02 区域挖 想想往下挖（先回到格心），人在井上晃。
	 */
	public static boolean skipThinkForSimpleDown(
		boolean sameColumn, boolean aboveSurface, boolean remainingBelow, boolean openBelow, boolean mineInReach
	) {
		return sameColumn && !aboveSurface && (remainingBelow || openBelow || mineInReach);
	}

	/** 准星已经打到这口竖井里的可挖方块：挖它。必须在本模组可挖距离内。 */
	public static boolean mineLookedShaftBlock(boolean inThisShaft, boolean mineable) {
		return inThisShaft && mineable;
	}

	/**
	 * 竖井目标只用本模组可挖距离。原版 4.5 会选中井底，人停在井口飞近却永远差 0.4 格。
	 * 来源：382823 Y53 盯 Y49，距离 4.3 / 可挖 3.9。
	 */
	public static boolean acceptShaftMineTarget(boolean inMiningReach) {
		return inMiningReach;
	}

	/** 正在这口井往下挖时，不要按区域顶判断「目标在上面」。 */
	public static double thinkDestDy(boolean relocating, int areaTopY, int feetY, Integer targetY) {
		if (!relocating) {
			if (targetY == null) return 0.0;
			return targetY - feetY;
		}
		return areaTopY - feetY;
	}

	/** 竖井顶站立格。 */
	public static BlockPos shaftStandPos(int x, int z, int topY) {
		return new BlockPos(x, topY, z);
	}
}
