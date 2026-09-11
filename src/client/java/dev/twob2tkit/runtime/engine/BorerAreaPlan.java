package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import java.util.HashSet;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/** Production state machine, independent of Minecraft input, aiming and other mining modes. */
final class BorerAreaPlan {
	enum Cell { AIR, SOLID, BEDROCK, PROTECTED, LIQUID, UNLOADED }
	interface World {
		Cell cell(BlockPos pos);
		default boolean opensLiquid(BlockPos pos) { return false; }
		default BlockPos sealableSideWater(BlockPos pos) { return null; }
		/** Live implementation verifies visibility and actual block interaction reach. */
		default boolean canMine(BlockPos pos) { return true; }
	}
	enum Phase { SURVEY, ENTER, TRANSFER, LOWER_TO_TOP, DIG, HORIZONTAL, RETURN, VERIFY, DONE, BLOCKED }
	enum Action { WAIT, MINE, MINE_DOWN, SEAL_WATER, X, Z, UP, DOWN, DONE, BLOCKED }
	record Pose(double x, double y, double z, double vx, double vy, double vz) {
		boolean settled() { return Math.max(Math.abs(vx), Math.abs(vz)) < 0.025 && Math.abs(vy) < 0.085; }
	}
	record Command(Action action, BlockPos block, double x, double y, double z, String reason) {
		static Command waitAt(Pose p, String reason) { return new Command(Action.WAIT, null, p.x, p.y, p.z, reason); }
	}
	static final double CENTER = 0.085;
	static final double HEIGHT = 0.10;
	private final BlockPos min, max, first;
	private final boolean horizontal;
	private BlockPos horizontalWalking;
	private int horizontalFinishWait;
	private BlockPos column, pending;
	private Phase phase = Phase.SURVEY;
	private int cursorY, clearedColumns, airSamples;
	private String failure = "";
	private BlockPos failedBlock;
	private double transferY;
	private boolean transferPlanned;
	private int pendingTopY;
	private int verifyIndex;
	private final Set<Long> visited = new HashSet<>(), skipped = new HashSet<>();
	// Rebuilt from two-pass world observations after reload, never blindly trusted from a checkpoint.
	private final Map<Long, Integer> bedrockFloors = new HashMap<>();
	private Phase recoverPhase = Phase.DIG;
	private BorerAreaSurvey survey;
	private BlockPos pendingAir;
	private int confirmedEmptyColumns;
	private boolean reachedBottom;
	private final Set<Long> waterSeals = new HashSet<>();
	boolean reserveStorageColumn(BlockPos chest) {
		if (chest == null || chest.getY() < min.getY() || chest.getY() > max.getY() + 3 || !containsColumn(key(chest))) return false;
		if (skipped.contains(key(chest))) return false;
		if (visited.contains(key(chest)) && !bedrockFloors.containsKey(key(chest))) { clearedColumns = Math.max(0, clearedColumns - 1); confirmedEmptyColumns = Math.max(0, confirmedEmptyColumns - 1); }
		bedrockFloors.remove(key(chest));
		skipped.add(key(chest)); visited.add(key(chest));
		if (pending != null && key(pending) == key(chest)) pending = nextUnvisited(pending);
		return true;
	}
	void resumeAfterStorage(Pose p) {
		BlockPos here = new BlockPos((int)Math.floor(p.x), 0, (int)Math.floor(p.z));
		if (horizontal && containsColumn(key(here)) && !skipped.contains(key(here)) && !bedrockFloors.containsKey(key(here))) {
			column = new BlockPos((int)Math.floor(p.x), 0, (int)Math.floor(p.z));
			pending = null; horizontalWalking = null; airSamples = 0; phase = Phase.HORIZONTAL; return;
		}
		if (!skipped.contains(key(column))) return;
		column = new BlockPos((int)Math.floor(p.x), 0, (int)Math.floor(p.z));
		pending = nextUnvisited(column); phase = pending == null ? Phase.RETURN : Phase.ENTER;
		transferY = Math.max(max.getY() + 1.25, p.y); cursorY = max.getY();
		transferPlanned = false;
	}
	boolean isWaterSeal(BlockPos p) { return waterSeals.contains(p.asLong()); }
	void rememberWaterSeal(BlockPos p) {
		if (!waterSeals.add(p.asLong())) return;
		if (p.getY() < min.getY() || p.getY() > max.getY() + 3 || !containsColumn(key(p))) return;
		if (visited.contains(key(p)) && !skipped.contains(key(p)) && !bedrockFloors.containsKey(key(p))) {
			clearedColumns = Math.max(0, clearedColumns - 1); confirmedEmptyColumns = Math.max(0, confirmedEmptyColumns - 1);
		}
		bedrockFloors.remove(key(p));
		skipped.add(key(p)); visited.add(key(p));
		if (pending != null && key(pending) == key(p)) pending = nextUnvisited(pending);
	}

	/** Explicit shaft mode, retained for shaft regressions; the live runner supplies the resolved-height strategy. */
	BorerAreaPlan(BlockPos min, BlockPos max, Pose start) { this(min, max, start, false); }
	BorerAreaPlan(BlockPos min, BlockPos max, Pose start, boolean preferHorizontal) {
		if (min.getX() > max.getX() || min.getY() > max.getY() || min.getZ() > max.getZ()) {
			throw new IllegalArgumentException("inverted area bounds");
		}
		this.min = min.immutable();
		this.max = max.immutable();
		horizontal = preferHorizontal && BorerAreaHorizontal.enabled(min, max);
		first = BorerAreaShaftPolicy.nearestCorner((int)Math.floor(start.x), (int)Math.floor(start.z),
			min.getX(), min.getZ(), max.getX(), max.getZ());
		column = new BlockPos((int)Math.floor(start.x), 0, (int)Math.floor(start.z));
		pending = first;
		cursorY = max.getY();
		transferY = Math.max(max.getY() + 1.25, start.y);
		survey = new BorerAreaSurvey(min, max);
	}

	Phase phase() { return phase; }
	boolean horizontal() { return horizontal; }
	BlockPos column() { return column; }
	BlockPos pending() { return pending; }
	int cursorY() { return cursorY; }
	int completed() { return clearedColumns; }
	int bottomY() { return min.getY(); }
	int skipped() { return skipped.size() + bedrockFloors.size(); }
	int bedrockColumns() { return bedrockFloors.size(); }
	int confirmedEmptyColumns() { return confirmedEmptyColumns; }
	boolean reachedBottomThisStep() { return reachedBottom; }
	int total() { return (max.getX() - min.getX() + 1) * (max.getZ() - min.getZ() + 1); }
	double transferY() { return transferY; }
	String progressStamp() { return phase + ":" + column + ":" + cursorY + ":" + verifyIndex
		+ (survey == null ? "" : ":scan=" + survey.progress())
		+ (phase == Phase.HORIZONTAL ? ":next=" + pending + ":walk=" + horizontalWalking + ":settle=" + horizontalFinishWait : ""); }
	double distanceRemaining(Pose p) {
		if (phase == Phase.HORIZONTAL) {
			BlockPos to = horizontalWalking != null ? horizontalWalking : pending != null ? pending : column;
			return Math.abs(to.getX() + 0.5 - p.x) + Math.abs(to.getZ() + 0.5 - p.z) + Math.abs(min.getY() + 0.08 - p.y);
		}
		BlockPos destination = phase == Phase.TRANSFER ? pending : column;
		double y = phase == Phase.DIG ? (cursorY >= min.getY() ? cursorY + 1.15 : min.getY() + 0.08) : transferY;
		return Math.abs(destination.getX() + 0.5 - p.x) + Math.abs(destination.getZ() + 0.5 - p.z) + Math.abs(y - p.y);
	}

	Command fail(Pose p, BlockPos block, String reason) {
		recoverPhase = phase;
		phase = Phase.BLOCKED;
		failure = reason;
		failedBlock = block;
		return new Command(Action.BLOCKED, block, p.x, p.y, p.z, reason);
	}

	Command step(World world, Pose p) {
		reachedBottom = false;
		if (phase == Phase.BLOCKED) return new Command(Action.BLOCKED, failedBlock, p.x, p.y, p.z, failure);
		if (phase == Phase.DONE) return new Command(Action.DONE, null, p.x, p.y, p.z,
			skipped() == 0 ? "区域全部挖完" : "区域可挖部分已复核，保留基岩及其它保护列");
		if (phase == Phase.SURVEY) return survey(world, p);
		if (phase == Phase.HORIZONTAL) return horizontalStep(world, p);
		if (phase == Phase.VERIFY) {
			int width = max.getX() - min.getX() + 1, height = max.getY() - min.getY() + 1;
			int volume = total() * height;
			for (int checks = 0; checks < 512 && verifyIndex < volume; checks++) {
				int index = verifyIndex;
				BlockPos b = new BlockPos(min.getX() + index % width,
					min.getY() + index / width % height, min.getZ() + index / (width * height));
				if (skipped.contains(key(b))) { verifyIndex++; continue; }
				Integer bedrockY = bedrockFloors.get(key(b));
				if (bedrockY != null && b.getY() < bedrockY) { verifyIndex++; continue; }
				Cell cell = world.cell(b);
				if (cell == Cell.UNLOADED) return Command.waitAt(p, "最终复核等待区块加载");
				if (bedrockY != null && b.getY() == bedrockY && cell == Cell.BEDROCK) { verifyIndex++; continue; }
				if (cell == Cell.SOLID || cell == Cell.LIQUID || cell == Cell.BEDROCK || bedrockY != null && b.getY() == bedrockY) {
					survey = new BorerAreaSurvey(min, max);
					phase = Phase.SURVEY;
					verifyIndex = 0;
					return Command.waitAt(p, "复核发现剩余方块，重新选择未完成列");
				}
				if (cell != Cell.AIR) return fail(p, b, "最终复核发现保护方块，区域尚未完成");
				verifyIndex++;
			}
			if (verifyIndex == volume) phase = Phase.DONE;
			return Command.waitAt(p, "正在复核整个区域");
		}
		if (phase == Phase.ENTER || phase == Phase.RETURN) {
			if (pending != null) {
				Command check = checkPending(world, p);
				if (check != null) return check;
			}
			if (!transferPlanned) {
				BorerAreaTransfer.Surface route = transferSurface(world);
				if (!route.loaded()) return Command.waitAt(p, "等待换列路线区块加载，不盲目起飞");
				transferY = Math.max(p.y, route.y() + 1.25);
				transferPlanned = true;
				return Command.waitAt(p, pending == null ? "最后一列结束，返回区域顶部复核"
					: "下一列最高方块 Y " + pendingTopY + "，换列高度 Y " + transferY);
			}
			Command align = align(world, p, column.getX() + 0.5, column.getZ() + 0.5);
			if (align != null) return align;
			Command rise = vertical(world, p, transferY);
			if (rise != null) return rise;
			// Keep the departure column until ascent is complete, including the final shaft.
			if (phase == Phase.RETURN && pending == null) {
				phase = Phase.VERIFY;
				return step(world, p);
			}
			phase = Phase.TRANSFER;
			return Command.waitAt(p, "已到安全换列高度，准备平移");
		}
		if (phase == Phase.TRANSFER) {
			Command check = checkPending(world, p);
			if (check != null) return check;
			BorerAreaTransfer.Surface route = transferSurface(world);
			if (!route.loaded()) return Command.waitAt(p, "等待换列路线区块加载");
			if (route.y() + 1.25 > transferY + HEIGHT) {
				phase = Phase.RETURN; transferPlanned = false;
				return Command.waitAt(p, "换列路线出现更高方块，先重新调整安全高度");
			}
			// Restore height at the departure XZ before any horizontal input.
			Command height = vertical(world, p, transferY);
			if (height != null) return height;
			Command move = align(world, p, pending.getX() + 0.5, pending.getZ() + 0.5);
			if (move != null) return move;
			column = pending;
			pending = null;
			cursorY = pendingTopY;
			airSamples = 0;
			phase = Phase.LOWER_TO_TOP;
			transferY = cursorY + 1.25;
			return Command.waitAt(p, "井口已对准，从实际最高剩余层 Y " + cursorY + " 开挖");
		}
		if (phase == Phase.LOWER_TO_TOP) {
			Command align = align(world, p, column.getX() + 0.5, column.getZ() + 0.5);
			if (align != null) return align;
			Command height = vertical(world, p, transferY);
			if (height != null) return height;
			phase = Phase.DIG;
			return Command.waitAt(p, "从本列实际最高 Y 垂直开挖");
		}

		Command align = align(world, p, column.getX() + 0.5, column.getZ() + 0.5);
		if (align != null) return align;
		// Refilled/falling blocks above the cursor are not silently marked complete.
		for (int y = max.getY(); y > cursorY; y--) {
			Cell cell = world.cell(new BlockPos(column.getX(), y, column.getZ()));
			if (cell == Cell.UNLOADED) return Command.waitAt(p, "等待当前列区块加载");
			if (cell != Cell.AIR) { cursorY = y; airSamples = 0; break; }
		}
		if (cursorY >= min.getY()) {
			BlockPos block = new BlockPos(column.getX(), cursorY, column.getZ());
			Cell cell = world.cell(block);
			if (cell == Cell.UNLOADED) return Command.waitAt(p, "等待当前列区块加载");
			if (cell == Cell.AIR) {
				// Two distinct observed ticks. Crack stage / estimated insta-break is never completion.
				if (++airSamples >= 2) { cursorY--; airSamples = 0; }
				return Command.waitAt(p, "确认方块已消失");
			}
			airSamples = 0;
			if (cell == Cell.BEDROCK) return stopAtBedrock(p, block);
			if (cell == Cell.LIQUID || world.opensLiquid(block)) {
				if ((cell == Cell.SOLID || cell == Cell.LIQUID) && world.sealableSideWater(block) != null) return sealWater(p, block);
				return skipLiquid(p, block);
			}
			if (cell != Cell.SOLID) return fail(p, block, "当前列遇到保护方块，未计完成");
			// Dig from anywhere in reach above the top face. Descend while mining when there is clearance.
			double gap = p.y - (cursorY + 1.0);
			if (gap > 1.8 || gap < -0.1 || !world.canMine(block)) {
				Command position = vertical(world, p, cursorY + 1.15);
				if (position != null) return position;
			}
			boolean descend = gap > 0.25 && p.vy <= 0.04;
			return new Command(descend ? Action.MINE_DOWN : Action.MINE, block,
				p.x, cursorY + 1.10, p.z, "向下连续挖当前层");
		}
		Command bottom = vertical(world, p, min.getY() + 0.08);
		if (bottom != null) return bottom;
		clearedColumns++;
		reachedBottom = true;
		visited.add(key(column));
		pending = nextUnvisited();
		phase = horizontal ? Phase.HORIZONTAL : Phase.RETURN;
		transferPlanned = false;
		return Command.waitAt(p, horizontal ? "已开出入口，保持底部高度水平清挖" : "本列到底，检查下一列实际高度");
	}

	private Command horizontalStep(World world, Pose p) {
		double workY = min.getY() + 0.08;
		BlockPos here = new BlockPos((int)Math.floor(p.x), 0, (int)Math.floor(p.z));
		if (containsColumn(key(here)) && (skipped.contains(key(here)) || bedrockFloors.containsKey(key(here)))
			&& !BorerAreaHorizontal.bodyClear(world, here, min.getY())) {
			column = here; pending = nextUnvisited(here);
			return horizontalFallback(p, "当前列已保留，先安全离开，不再次下降进入液体或箱子");
		}
		if (Math.abs(p.y - workY) > HEIGHT) return movement(world, p, p.y > workY ? Action.DOWN : Action.UP, p.x, workY, p.z);
		if (Math.abs(p.vy) > 0.085) return Command.waitAt(p, "稳定水平作业高度");
		if (horizontalWalking != null) {
			if (skipped.contains(key(horizontalWalking)) && !BorerAreaHorizontal.bodyClear(world, horizontalWalking, min.getY())) {
				horizontalWalking = null; airSamples = 0;
				return Command.waitAt(p, "水平路线已被存储或挡水方块占用，重新选择通路");
			}
			Command move = align(world, p, horizontalWalking.getX() + 0.5, horizontalWalking.getZ() + 0.5);
			if (move != null) return move;
			column = horizontalWalking; horizontalWalking = null; airSamples = 0;
			return Command.waitAt(p, "水平到位，拾取掉落物并检查剩余方块");
		}
		Command center = align(world, p, column.getX() + 0.5, column.getZ() + 0.5);
		if (center != null) return center;
		if (pending != null && visited.contains(key(pending))) { pending = null; airSamples = 0; }
		if (pending == null) pending = !visited.contains(key(column)) && containsColumn(key(column)) ? column : nextUnvisited();
		if (pending == null) {
			// Stay at the work plane: a shallow room may have an unselected ceiling directly above it.
			if (++horizontalFinishWait <= 15) return Command.waitAt(p, "等待末列掉落物落地后原地复核");
			phase = Phase.VERIFY; verifyIndex = 0;
			return Command.waitAt(p, "浅层水平清挖结束，原地复核，不为返顶额外挖开屋顶");
		}
		horizontalFinishWait = 0;
		// Inspect the whole shallow column before removing any lower barrier.
		for (int y = min.getY(); y <= max.getY(); y++) {
			BlockPos block = new BlockPos(pending.getX(), y, pending.getZ()); Cell cell = world.cell(block);
			if (cell == Cell.UNLOADED) return Command.waitAt(p, "水平清挖等待目标列加载");
			if (cell == Cell.LIQUID) return skipLiquid(p, block);
			if (cell == Cell.PROTECTED) return reserveHorizontal(p, block, "保留保护方块所在列，继续清理其它位置");
			if (cell == Cell.BEDROCK) return horizontalFallback(p, "目标列有基岩，改从上方清理可挖部分");
		}
		var route = BorerAreaHorizontal.route(world, min, max, column, pending, visited);
		if (!route.found()) {
			if (route.unknown()) return Command.waitAt(p, "水平绕行路线未加载，等待确认");
			BlockPos alternative = adjacentHorizontalWork(world);
			if (alternative != null) { pending = alternative; airSamples = 0; return Command.waitAt(p, "先清理身旁可达的一格，水平绕过保护列"); }
			return horizontalFallback(p, "底部通道不连通，安全越过障碍后继续水平清挖");
		}
		if (!route.step().equals(column)) {
			horizontalWalking = route.step(); airSamples = 0;
			return Command.waitAt(p, "沿已清空的底部通道接近下一格");
		}
		// Clear eye/head level first, then the feet, then higher blocks. Never jump against a two-high wall.
		BlockPos target = null;
		for (int i = 0; i <= max.getY() - min.getY(); i++) {
			int y = min.getY() + (max.getY() > min.getY() && i < 2 ? 1 - i : i);
			BlockPos block = new BlockPos(pending.getX(), y, pending.getZ());
			if (world.cell(block) == Cell.SOLID) { target = block; break; }
		}
		if (target != null) {
			airSamples = 0; cursorY = target.getY();
			if (world.opensLiquid(target)) {
				if (world.sealableSideWater(target) != null) return sealWater(p, target);
				return skipLiquid(p, target);
			}
			if (!world.canMine(target)) return horizontalFallback(p, "当前真实触及距离或射线不足，改从上方处理这一列");
			return new Command(Action.MINE, target, p.x, workY, p.z, "浅层水平清挖：清通道和上方方块，不逐列返顶");
		}
		if (++airSamples < 2) return Command.waitAt(p, "确认整列方块已实际消失");
		if (!pending.equals(column)) {
			if (!BorerAreaHorizontal.bodyClear(world, pending, min.getY())) return horizontalFallback(p, "区域上方净空不足，改用安全换列");
			horizontalWalking = pending; airSamples = 0;
			return Command.waitAt(p, "通道已清空，水平前进拾取掉落物");
		}
		if (visited.add(key(column))) { clearedColumns++; reachedBottom = true; }
		pending = nextUnvisited(); airSamples = 0; cursorY = min.getY() - 1;
		return Command.waitAt(p, "本格已清空并到位，保持高度继续旁边一格");
	}

	private Command horizontalFallback(Pose p, String reason) {
		horizontalWalking = null; airSamples = 0; transferPlanned = false; phase = Phase.RETURN;
		return Command.waitAt(p, reason);
	}
	private BlockPos adjacentHorizontalWork(World world) {
		for (BlockPos next : new BlockPos[]{column.east(), column.south(), column.west(), column.north()}) {
			if (!containsColumn(key(next)) || visited.contains(key(next))) continue;
			boolean usable = true;
			for (int y = min.getY(); y <= max.getY(); y++) {
				Cell c = world.cell(new BlockPos(next.getX(), y, next.getZ()));
				if (c != Cell.AIR && c != Cell.SOLID) { usable = false; break; }
			}
			if (usable) return next;
		}
		return null;
	}
	private Command reserveHorizontal(Pose p, BlockPos block, String reason) {
		if (containsColumn(key(block))) {
			if (visited.contains(key(block)) && !skipped.contains(key(block)) && !bedrockFloors.containsKey(key(block))) {
				clearedColumns = Math.max(0, clearedColumns - 1); confirmedEmptyColumns = Math.max(0, confirmedEmptyColumns - 1);
			}
			bedrockFloors.remove(key(block)); skipped.add(key(block)); visited.add(key(block));
		}
		horizontalWalking = null; pending = nextUnvisited(); airSamples = 0;
		return Command.waitAt(p, reason);
	}
	private boolean canEnterHorizontal(World world, Pose p) {
		if (!containsColumn(key(column)) || p.y < min.getY() - HEIGHT || !BorerAreaHorizontal.bodyClear(world, column, min.getY())) return false;
		for (int y = min.getY(); y <= Math.floor(p.y + 1.799); y++)
			if (world.cell(new BlockPos(column.getX(), y, column.getZ())) != Cell.AIR) return false;
		return true;
	}

	/** Position is only a starting point, never a reason to discard an area's completion record. */
	private Command survey(World world, Pose p) {
		if (!survey.step(world)) return Command.waitAt(p, "扫描实际剩余方块 " + survey.progress() + "/" + survey.totalReads());
		visited.clear();
		bedrockFloors.clear();
		clearedColumns = confirmedEmptyColumns = 0;
		BlockPos nearest = null;
		double nearestDistance = Double.POSITIVE_INFINITY;
		boolean unknown = false;
		for (int i = 0; i < survey.columns(); i++) {
			BlockPos c = survey.column(i);
			if (survey.clear(i)) {
				visited.add(key(c)); skipped.remove(key(c));
				clearedColumns++; confirmedEmptyColumns++;
			} else if (skipped.contains(key(c))) visited.add(key(c));
			else if (survey.bedrockSurface(i) != null) {
				visited.add(key(c)); bedrockFloors.put(key(c), survey.bedrockSurface(i));
			}
			else if (!survey.loaded(i)) unknown = true;
			else {
				double distance = Math.abs(c.getX() + 0.5 - p.x) + Math.abs(c.getZ() + 0.5 - p.z);
				if (distance < nearestDistance) { nearestDistance = distance; nearest = c; }
			}
		}
		if (nearest == null && unknown) {
			survey = new BorerAreaSurvey(min, max);
			return Command.waitAt(p, "剩余列尚未加载，等待区块；不会将其计为已挖空");
		}
		survey = null;
		column = new BlockPos((int)Math.floor(p.x), 0, (int)Math.floor(p.z));
		pending = nearest;
		cursorY = max.getY(); airSamples = 0;
		transferY = Math.max(max.getY() + 1.25, p.y);
		transferPlanned = false;
		if (horizontal && nearest == null && !unknown) {
			phase = Phase.VERIFY; verifyIndex = 0;
			return Command.waitAt(p, "浅层区域没有剩余可挖格，原地复核，不重复进出");
		}
		if (horizontal && nearest != null && canEnterHorizontal(world, p)) {
			phase = Phase.HORIZONTAL; pending = null; horizontalWalking = null;
			return Command.waitAt(p, "浅层工程已有入口，从当前位置接入水平清挖");
		}
		if (nearest != null && !visited.contains(key(column)) && resumeInOpenShaft(world, p)) {
			return Command.waitAt(p, "扫描完成，跳过 " + confirmedEmptyColumns + " 个空列，从当前位置继续未挖部分");
		}
		phase = nearest == null ? Phase.RETURN : Phase.ENTER;
		return Command.waitAt(p, nearest == null ? "没有剩余可挖列，不再下井；返回顶部复核"
			: "扫描完成，跳过 " + confirmedEmptyColumns + " 个空列，前往最近未完成列 " + nearest.getX() + ", " + nearest.getZ());
	}

	/** A column may be cleared manually after the initial survey; confirm before any travel or descent into it. */
	private Command checkPending(World world, Pose p) {
		if (pending == null) { phase = Phase.RETURN; transferPlanned = false; return Command.waitAt(p, "没有剩余列，准备返回复核"); }
		for (int y = max.getY(); y >= min.getY(); y--) {
			Cell cell = world.cell(new BlockPos(pending.getX(), y, pending.getZ()));
			if (cell == Cell.UNLOADED) { pendingAir = null; return Command.waitAt(p, "等待下一列区块加载"); }
			if (cell != Cell.AIR) { pendingAir = null; pendingTopY = y; return null; }
		}
		if (!pending.equals(pendingAir)) {
			pendingAir = pending;
			return Command.waitAt(p, "下一列看起来已挖空，再次确认后直接跳过");
		}
		if (visited.add(key(pending))) { clearedColumns++; confirmedEmptyColumns++; }
		BlockPos empty = pending;
		pending = nextUnvisited(pending);
		pendingAir = null;
		phase = Phase.RETURN; transferPlanned = false;
		return Command.waitAt(p, "跳过已挖空列 " + empty.getX() + ", " + empty.getZ() + "，无需下井");
	}

	private BorerAreaTransfer.Surface transferSurface(World world) {
		// Keep the existing high entry route for outside starts and the final return. Bound long scans.
		if (pending == null || !containsColumn(key(column)) || column.distManhattan(pending) > 128)
			return new BorerAreaTransfer.Surface(true, max.getY());
		return BorerAreaTransfer.routeTop(world, column, pending, min.getY(), max.getY());
	}

	private Command stopAtBedrock(Pose p, BlockPos block) {
		if (phase != Phase.DIG || block.getX() != column.getX() || block.getZ() != column.getZ()
			|| block.getY() >= p.y || block.getY() < min.getY() || block.getY() > max.getY())
			return fail(p, block, "基岩阻挡通行空间，未强行穿越");
		bedrockFloors.put(key(column), block.getY());
		visited.add(key(column)); pending = nextUnvisited(); phase = Phase.RETURN; transferPlanned = false;
		return Command.waitAt(p, "本列挖到基岩 Y " + block.getY() + "，保留基岩并继续下一列");
	}

	private Command align(World w, Pose p, double x, double z) {
		if (Math.abs(x - p.x) > CENTER) return movement(w, p, Action.X, x, p.y, p.z);
		if (Math.abs(z - p.z) > CENTER) return movement(w, p, Action.Z, p.x, p.y, z);
		// Horizontal alignment must not brake an ongoing vertical flight on every other tick.
		return Math.max(Math.abs(p.vx), Math.abs(p.vz)) < 0.025 ? null : Command.waitAt(p, "水平刹停后继续");
	}
	private Command sealWater(Pose p, BlockPos barrier) {
		return new Command(Action.SEAL_WATER, barrier, p.x, p.y, p.z, "先用石料堵住侧面进水口，再继续开路");
	}

	private Command vertical(World w, Pose p, double y) {
		if (Math.abs(y - p.y) <= HEIGHT) return p.settled() ? null : Command.waitAt(p, "稳定高度");
		return movement(w, p, y > p.y ? Action.UP : Action.DOWN, p.x, y, p.z);
	}

	private Command movement(World w, Pose p, Action action, double x, double y, double z) {
		// Sweep the player's body through the next small input step, not just the feet block.
		double nx = p.x + Math.copySign(Math.min(0.25, Math.abs(x - p.x)), x - p.x);
		double ny = p.y + Math.copySign(Math.min(1.20, Math.abs(y - p.y)), y - p.y);
		double nz = p.z + Math.copySign(Math.min(0.25, Math.abs(z - p.z)), z - p.z);
		for (int by = (int)Math.floor(Math.min(p.y, ny) + 0.001); by <= (int)Math.floor(Math.max(p.y, ny) + 1.799); by++) {
			for (int bx = (int)Math.floor(Math.min(p.x, nx) - 0.299); bx <= (int)Math.floor(Math.max(p.x, nx) + 0.299); bx++) {
				for (int bz = (int)Math.floor(Math.min(p.z, nz) - 0.299); bz <= (int)Math.floor(Math.max(p.z, nz) + 0.299); bz++) {
					BlockPos block = new BlockPos(bx, by, bz);
					Cell cell = w.cell(block);
					if (cell == Cell.UNLOADED) return Command.waitAt(p, "等待路径区块加载");
					if (cell == Cell.AIR) continue;
					if (cell == Cell.BEDROCK && phase == Phase.DIG && action == Action.DOWN) return stopAtBedrock(p, block);
					if ((cell == Cell.SOLID || cell == Cell.LIQUID) && w.sealableSideWater(block) != null) return sealWater(p, block);
					if ((phase == Phase.DIG || phase == Phase.HORIZONTAL) && (cell == Cell.LIQUID || w.opensLiquid(block))) return skipLiquid(p, block);
					if (cell != Cell.SOLID || !canClearPath(block, p, action)) {
						return fail(p, block, "路径受阻：" + cell + "，保持未完成进度");
					}
					return new Command(Action.MINE, block, p.x, p.y, p.z, "清理当前路径挡块");
				}
			}
		}
		return new Command(action, null, x, y, z, action == Action.UP ? "原列垂直上升" : action == Action.DOWN ? "原列垂直下降" : "水平对准下一列");
	}

	Command skipLiquid(Pose p, BlockPos barrier) {
		if (phase == Phase.HORIZONTAL) return reserveHorizontal(p, barrier, "保留隔水方块和液体列，改走其它水平通道");
		if (phase != Phase.DIG) return fail(p, barrier, "通行路线遇水，保留挡水块");
		skipped.add(key(column));
		visited.add(key(column));
		pending = nextUnvisited();
		phase = Phase.RETURN;
		transferPlanned = false;
		return Command.waitAt(p, "保留隔水方块，跳过本列并检查换列高度");
	}

	private BlockPos nextUnvisited() {
		return nextUnvisited(column);
	}
	private BlockPos nextUnvisited(BlockPos from) {
		BlockPos next = from;
		for (int n = 0; n < total(); n++) {
			next = BorerAreaShaftPolicy.nextSnakeColumn(next.getX(), next.getZ(), min.getX(), min.getZ(),
				max.getX(), max.getZ(), first.getX(), first.getZ());
			if (next == null) next = first;
			if (!visited.contains(key(next))) return next;
		}
		return null;
	}
	private static long key(BlockPos p) { return ((long)p.getX() << 32) ^ (p.getZ() & 0xffffffffL); }

	record Snapshot(int[] bounds, int firstX, int firstZ, int x, int z, Integer nextX, Integer nextZ,
		Phase phase, Phase recover, int cursor, int completed, double travelY, long[] visited, long[] skipped, long[] waterSeals) {}
	Snapshot snapshot() {
		return new Snapshot(new int[]{min.getX(), min.getY(), min.getZ(), max.getX(), max.getY(), max.getZ()},
			first.getX(), first.getZ(), column.getX(), column.getZ(), pending == null ? null : pending.getX(),
			pending == null ? null : pending.getZ(), phase, recoverPhase, cursorY, clearedColumns, transferY,
			visited.stream().mapToLong(Long::longValue).toArray(), skipped.stream().mapToLong(Long::longValue).toArray(),
			waterSeals.stream().mapToLong(Long::longValue).toArray());
	}

	static BorerAreaPlan restore(BlockPos min, BlockPos max, Pose p, Snapshot s) {
		return restore(min, max, p, s, false);
	}
	static BorerAreaPlan restore(BlockPos min, BlockPos max, Pose p, Snapshot s, boolean horizontal) {
		if (s == null || s.phase == null || s.bounds == null
			|| !java.util.Arrays.equals(s.bounds, new int[]{min.getX(), min.getY(), min.getZ(), max.getX(), max.getY(), max.getZ()})) return null;
		if (s.firstX != min.getX() && s.firstX != max.getX() || s.firstZ != min.getZ() && s.firstZ != max.getZ()) return null;
		if (s.visited == null || s.skipped == null || !Double.isFinite(s.travelY) || s.completed < 0) return null;
		BorerAreaPlan plan = new BorerAreaPlan(min, max, new Pose(s.firstX + 0.5, p.y, s.firstZ + 0.5, 0, 0, 0), horizontal);
		plan.column = new BlockPos((int)Math.floor(p.x), 0, (int)Math.floor(p.z));
		plan.cursorY = Math.max(min.getY() - 1, Math.min(max.getY(), s.cursor));
		plan.clearedColumns = Math.min(plan.total(), s.completed);
		plan.transferY = Math.max(max.getY() + 1.25, p.y);
		for (long k : s.visited) if (plan.containsColumn(k)) plan.visited.add(k);
		for (long k : s.skipped) if (plan.containsColumn(k)) plan.skipped.add(k);
		if (s.waterSeals != null) for (long k : s.waterSeals) plan.waterSeals.add(k);
		return plan;
	}

	private boolean containsColumn(long k) {
		int x = (int)(k >> 32), z = (int)k;
		return x >= min.getX() && x <= max.getX() && z >= min.getZ() && z <= max.getZ();
	}

	/** Continue in place only when there is a clear shaft above and remaining work below the feet. */
	boolean resumeInOpenShaft(World w, Pose p) {
		int x = (int)Math.floor(p.x), z = (int)Math.floor(p.z);
		if (x < min.getX() || x > max.getX() || z < min.getZ() || z > max.getZ()
			|| p.y < min.getY() || p.y >= max.getY() + 1) return false;
		for (int y = max.getY(); y >= (int)Math.ceil(p.y); y--) if (w.cell(new BlockPos(x, y, z)) != Cell.AIR) return false;
		int top = max.getY();
		while (top >= min.getY() && w.cell(new BlockPos(x, top, z)) == Cell.AIR) top--;
		if (top < min.getY() || w.cell(new BlockPos(x, top, z)) == Cell.UNLOADED) return false;
		column = new BlockPos(x, 0, z);
		pending = null;
		phase = Phase.DIG;
		transferY = max.getY() + 1.25;
		cursorY = top;
		return true;
	}

	private boolean canClearPath(BlockPos b, Pose p, Action action) {
		// Even a fallback/entry for a shallow room must not punch through its unselected ceiling or floor.
		if (horizontal && (!containsColumn(key(b)) || b.getY() < min.getY() || b.getY() > max.getY())) return false;
		if (phase == Phase.HORIZONTAL) return containsColumn(key(b)) && b.getY() >= min.getY() && b.getY() <= max.getY()
			&& !skipped.contains(key(b)) && !bedrockFloors.containsKey(key(b));
		if (phase == Phase.DIG) {
			return b.getX() == column.getX() && b.getZ() == column.getZ()
				&& b.getY() >= min.getY() && b.getY() <= max.getY();
		}
		if (phase == Phase.ENTER || phase == Phase.RETURN) {
			return b.getX() == column.getX() && b.getZ() == column.getZ()
				&& b.getY() >= Math.floor(p.y) && action == Action.UP;
		}
		if (phase == Phase.LOWER_TO_TOP) return b.getX() == column.getX() && b.getZ() == column.getZ() && b.getY() > max.getY();
		return phase == Phase.TRANSFER && b.getY() > max.getY();
	}
}
